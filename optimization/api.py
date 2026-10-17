"""Logique des endpoints HTTP de l'Optimization Lab (appelée par web_api_server ; retourne (status, payload)).

Le processus web ne calcule jamais rien : il valide, crée le job en base (statut `queued`) et lit son état.
Le worker (service Railway séparé) exécute les simulations.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple

import strategy_lab as sl

from . import engine, store
from .space import SpaceError, get_optimizable_parameters, MAX_CONFIGS_HARD, MAX_PARAMS, WARN_CONFIGS

MAX_ACTIVE_JOBS_USER = int(os.getenv("OPT_MAX_ACTIVE_JOBS_USER", "3") or 3)
MAX_ACTIVE_JOBS_ADMIN = int(os.getenv("OPT_MAX_ACTIVE_JOBS_ADMIN", "10") or 10)

_schema_lock = threading.Lock()
_schema_ready = False


def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if not _schema_ready:
            store.ensure_schema()
            _schema_ready = True


def _owned(job: Optional[Dict[str, Any]], user_id: int, is_admin: bool) -> bool:
    return bool(job) and (is_admin or int(job["user_id"]) == int(user_id))


def overview(user_id: int, is_admin: bool, style: str = "day", light: bool = False) -> Tuple[int, Dict[str, Any]]:
    _ensure_schema()
    style = style if style in engine.VALID_STYLES else "day"
    jobs = store.list_jobs(None if is_admin else user_id, limit=30)
    if light:  # suivi de progression : uniquement la liste des jobs (réponse légère)
        return 200, {"ok": True, "jobs": jobs}
    return 200, {
        "ok": True,
        "parameters": get_optimizable_parameters(style),
        "limits": {"max_configs": MAX_CONFIGS_HARD, "warn_configs": WARN_CONFIGS, "max_params": MAX_PARAMS,
                   "default_min_trades": engine.DEFAULT_MIN_TRADES, "default_top_k": engine.DEFAULT_TOP_K},
        "jobs": jobs,
    }


def plan(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    try:
        request, space = engine.plan_request(body)
    except SpaceError as exc:
        return 400, {"ok": False, "error": str(exc)}
    return 200, {"ok": True, "plan": engine.public_plan(space, request), "request": request}


def create(user_id: int, is_admin: bool, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    _ensure_schema()
    try:
        request, space = engine.plan_request(body)
    except SpaceError as exc:
        return 400, {"ok": False, "error": str(exc)}
    cap = MAX_ACTIVE_JOBS_ADMIN if is_admin else MAX_ACTIVE_JOBS_USER
    if store.count_active_jobs(user_id) >= cap:
        return 429, {"ok": False, "error": f"Maximum {cap} optimisations simultanées (en attente ou en cours) : attendez la fin d'une optimisation ou annulez-en une."}
    total_steps = engine.estimate_total_steps(space["n_configs"], request["top_k"])
    job_id = store.create_job(user_id, request, space, total_steps)
    return 200, {"ok": True, "job_id": job_id, "status": "queued", "plan": engine.public_plan(space, request),
                 "message": "Optimisation mise en file d'attente : elle continue même si vous fermez cette page."}


def get_job(user_id: int, is_admin: bool, job_id: str) -> Tuple[int, Dict[str, Any]]:
    _ensure_schema()
    job = store.get_job(job_id, include_plan=False)
    if not _owned(job, user_id, is_admin):
        return 404, {"ok": False, "error": "Optimisation introuvable."}
    return 200, {"ok": True, "job": job}


def get_report(user_id: int, is_admin: bool, job_id: str) -> Tuple[int, Dict[str, Any]]:
    _ensure_schema()
    job = store.get_job(job_id, include_report=True, include_plan=False)
    if not _owned(job, user_id, is_admin):
        return 404, {"ok": False, "error": "Optimisation introuvable."}
    if job["status"] != "completed" or not job.get("report_html"):
        return 409, {"ok": False, "error": "Le rapport n'est disponible qu'une fois l'optimisation terminée."}
    return 200, {"ok": True, "html": job["report_html"], "filename": f"{job_id}.html"}


def cancel(user_id: int, is_admin: bool, job_id: str) -> Tuple[int, Dict[str, Any]]:
    _ensure_schema()
    job = store.get_job(job_id, include_plan=False)
    if not _owned(job, user_id, is_admin):
        return 404, {"ok": False, "error": "Optimisation introuvable."}
    if job["status"] not in store.ACTIVE_STATUSES:
        return 409, {"ok": False, "error": f"Optimisation déjà {job['status']}."}
    status = store.request_cancel(job_id)
    return 200, {"ok": True, "job_id": job_id, "status": status,
                 "message": "Annulation effectuée." if status == "cancelled" else "Annulation demandée : le worker s'arrête dans quelques secondes."}
