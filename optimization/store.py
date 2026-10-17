"""Persistance PostgreSQL des jobs d'optimisation (jobs, résultats, compteur d'identifiants)."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

STATUSES = ("queued", "running", "completed", "failed", "cancelled")
ACTIVE_STATUSES = ("queued", "running")
STALE_HEARTBEAT_SECONDS = 120
MAX_ATTEMPTS = 5

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS optimization_counters (
        year INTEGER PRIMARY KEY,
        last_seq INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS optimization_jobs (
        job_id TEXT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        stage TEXT DEFAULT 'queued',
        created_at DOUBLE PRECISION NOT NULL,
        started_at DOUBLE PRECISION,
        finished_at DOUBLE PRECISION,
        heartbeat_at DOUBLE PRECISION,
        worker_id TEXT,
        attempts INTEGER DEFAULT 0,
        cancel_requested INTEGER DEFAULT 0,
        symbol TEXT,
        timeframe TEXT,
        market_type TEXT,
        trading_style TEXT,
        start_date TEXT,
        end_date TEXT,
        method TEXT,
        total_configs INTEGER DEFAULT 0,
        done_configs INTEGER DEFAULT 0,
        total_steps INTEGER DEFAULT 0,
        done_steps INTEGER DEFAULT 0,
        progress_pct DOUBLE PRECISION DEFAULT 0,
        request_json TEXT NOT NULL,
        plan_json TEXT NOT NULL,
        summary_json TEXT,
        report_html TEXT,
        error TEXT,
        last_notified_at DOUBLE PRECISION DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS optimization_results (
        job_id TEXT NOT NULL,
        config_idx INTEGER NOT NULL,
        stage TEXT NOT NULL,
        params_json TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        created_at DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (job_id, config_idx, stage)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_optimization_jobs_user ON optimization_jobs(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_optimization_jobs_status ON optimization_jobs(status, heartbeat_at)",
)

_LIST_COLUMNS = (
    "job_id, user_id, status, stage, created_at, started_at, finished_at, heartbeat_at, attempts, cancel_requested, "
    "symbol, timeframe, market_type, trading_style, start_date, end_date, method, total_configs, done_configs, "
    "total_steps, done_steps, progress_pct, error"
)


def _get_db(db=None):
    if db is not None:
        return db
    import database as _database
    return _database.get_db()


def _sanitize(obj: Any) -> Any:
    """JSON strict : NaN/inf -> None."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def dumps(obj: Any) -> str:
    return json.dumps(_sanitize(obj), ensure_ascii=False, allow_nan=False)


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    try:
        return {k: row[k] for k in row.keys()}
    except Exception:
        return dict(row)


def ensure_schema(db=None) -> None:
    db = _get_db(db)
    for stmt in _SCHEMA:
        db.execute(stmt)
    commit = getattr(db, "commit", None)
    if callable(commit):
        commit()


def next_job_id(db=None, now: Optional[float] = None) -> str:
    """Identifiant unique et croissant par année : OPT-2026-00142 (compteur atomique)."""
    db = _get_db(db)
    year = datetime.fromtimestamp(now or time.time(), tz=timezone.utc).year
    row = db.execute(
        "INSERT INTO optimization_counters (year, last_seq) VALUES (%s, 1) "
        "ON CONFLICT (year) DO UPDATE SET last_seq = optimization_counters.last_seq + 1 RETURNING last_seq",
        (year,),
    ).fetchone()
    return f"OPT-{year}-{int(row[0]):05d}"


def create_job(user_id: int, request: Dict[str, Any], plan: Dict[str, Any], total_steps: int, db=None) -> str:
    db = _get_db(db)
    now = time.time()
    job_id = next_job_id(db, now)
    db.execute(
        """
        INSERT INTO optimization_jobs
        (job_id, user_id, status, stage, created_at, symbol, timeframe, market_type, trading_style,
         start_date, end_date, method, total_configs, total_steps, request_json, plan_json)
        VALUES (%s, %s, 'queued', 'queued', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            job_id, int(user_id), now, request.get("symbol"), request.get("timeframe"), request.get("market_type"),
            request.get("trading_style"), request.get("start_date") or "", request.get("end_date") or "",
            plan.get("method"), int(plan.get("n_configs", 0)), int(total_steps), dumps(request), dumps(plan),
        ),
    )
    return job_id


def get_job(job_id: str, include_report: bool = False, include_plan: bool = True, db=None) -> Optional[Dict[str, Any]]:
    db = _get_db(db)
    cols = _LIST_COLUMNS + ", request_json, summary_json"
    if include_plan:
        cols += ", plan_json"
    if include_report:
        cols += ", report_html"
    row = db.execute(f"SELECT {cols} FROM optimization_jobs WHERE job_id = %s", (job_id,)).fetchone()
    if not row:
        return None
    d = _row_to_dict(row)
    for src, dst in (("request_json", "request"), ("summary_json", "summary"), ("plan_json", "plan")):
        if src in d:
            raw = d.pop(src)
            try:
                d[dst] = json.loads(raw) if raw else None
            except Exception:
                d[dst] = None
    return d


def list_jobs(user_id: Optional[int] = None, limit: int = 30, db=None) -> List[Dict[str, Any]]:
    db = _get_db(db)
    if user_id is None:
        rows = db.execute(f"SELECT {_LIST_COLUMNS} FROM optimization_jobs ORDER BY created_at DESC LIMIT %s", (int(limit),)).fetchall()
    else:
        rows = db.execute(
            f"SELECT {_LIST_COLUMNS} FROM optimization_jobs WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (int(user_id), int(limit)),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_active_jobs(user_id: int, db=None) -> int:
    db = _get_db(db)
    row = db.execute(
        "SELECT COUNT(*) FROM optimization_jobs WHERE user_id = %s AND status IN ('queued', 'running')", (int(user_id),)
    ).fetchone()
    return int(row[0]) if row else 0


def claim_next_job(worker_id: str, stale_seconds: int = STALE_HEARTBEAT_SECONDS, db=None) -> Optional[str]:
    """Réserve (atomiquement) un job en attente OU un job 'running' dont le worker ne donne plus signe de vie."""
    db = _get_db(db)
    now = time.time()
    stale_before = now - stale_seconds
    # Jobs interrompus trop de fois : échec définitif (évite une boucle infinie sur un job qui plante le worker).
    db.execute(
        "UPDATE optimization_jobs SET status = 'failed', finished_at = %s, "
        "error = 'Interrompu trop de fois (tentatives épuisées).' "
        "WHERE status = 'running' AND heartbeat_at < %s AND attempts >= %s",
        (now, stale_before, MAX_ATTEMPTS),
    )
    # Jobs dont l'annulation a été demandée alors que plus aucun worker ne les traite.
    db.execute(
        "UPDATE optimization_jobs SET status = 'cancelled', finished_at = %s "
        "WHERE cancel_requested = 1 AND status = 'running' AND heartbeat_at < %s",
        (now, stale_before),
    )
    row = db.execute(
        "SELECT job_id FROM optimization_jobs WHERE cancel_requested = 0 AND "
        "(status = 'queued' OR (status = 'running' AND heartbeat_at < %s)) ORDER BY created_at ASC LIMIT 1",
        (stale_before,),
    ).fetchone()
    if not row:
        return None
    job_id = row[0]
    cur = db.execute(
        "UPDATE optimization_jobs SET status = 'running', worker_id = %s, heartbeat_at = %s, "
        "started_at = COALESCE(started_at, %s), attempts = attempts + 1 "
        "WHERE job_id = %s AND cancel_requested = 0 AND (status = 'queued' OR (status = 'running' AND heartbeat_at < %s))",
        (worker_id, now, now, job_id, stale_before),
    )
    return job_id if getattr(cur, "rowcount", 0) == 1 else None


def heartbeat(job_id: str, worker_id: str, fields: Optional[Dict[str, Any]] = None, db=None) -> Tuple[bool, bool]:
    """Met à jour battement + progression. Retourne (propriétaire_ok, annulation_demandée)."""
    db = _get_db(db)
    sets = ["heartbeat_at = %s"]
    params: List[Any] = [time.time()]
    allowed = {"stage", "done_configs", "done_steps", "total_steps", "progress_pct", "total_configs"}
    for k, v in (fields or {}).items():
        if k in allowed:
            sets.append(f"{k} = %s")
            params.append(v)
    params.extend([job_id, worker_id])
    cur = db.execute(
        f"UPDATE optimization_jobs SET {', '.join(sets)} WHERE job_id = %s AND worker_id = %s AND status = 'running'",
        tuple(params),
    )
    if getattr(cur, "rowcount", 0) != 1:
        return False, False
    row = db.execute("SELECT cancel_requested FROM optimization_jobs WHERE job_id = %s", (job_id,)).fetchone()
    return True, bool(row and int(row[0] or 0) == 1)


def save_results(job_id: str, rows: Iterable[Tuple[int, str, Dict[str, Any], Dict[str, Any]]], db=None) -> None:
    db = _get_db(db)
    now = time.time()
    for idx, stage, params, metrics in rows:
        db.execute(
            "INSERT INTO optimization_results (job_id, config_idx, stage, params_json, metrics_json, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (job_id, config_idx, stage) DO NOTHING",
            (job_id, int(idx), stage, dumps(params), dumps(metrics), now),
        )


def load_results(job_id: str, stage: str, db=None) -> Dict[int, Dict[str, Any]]:
    db = _get_db(db)
    rows = db.execute(
        "SELECT config_idx, params_json, metrics_json FROM optimization_results WHERE job_id = %s AND stage = %s",
        (job_id, stage),
    ).fetchall()
    out: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        out[int(r[0])] = {"params": json.loads(r[1]), "metrics": json.loads(r[2])}
    return out


def mark_completed(job_id: str, worker_id: str, summary: Dict[str, Any], report_html: str, db=None) -> bool:
    db = _get_db(db)
    cur = db.execute(
        "UPDATE optimization_jobs SET status = 'completed', stage = 'completed', finished_at = %s, progress_pct = 100, "
        "summary_json = %s, report_html = %s, error = NULL WHERE job_id = %s AND worker_id = %s AND status = 'running'",
        (time.time(), dumps(summary), report_html, job_id, worker_id),
    )
    return getattr(cur, "rowcount", 0) == 1


def mark_failed(job_id: str, error: str, worker_id: Optional[str] = None, db=None) -> None:
    db = _get_db(db)
    if worker_id:
        db.execute(
            "UPDATE optimization_jobs SET status = 'failed', finished_at = %s, error = %s WHERE job_id = %s AND worker_id = %s",
            (time.time(), str(error)[:2000], job_id, worker_id),
        )
    else:
        db.execute(
            "UPDATE optimization_jobs SET status = 'failed', finished_at = %s, error = %s WHERE job_id = %s",
            (time.time(), str(error)[:2000], job_id),
        )


def mark_cancelled(job_id: str, db=None) -> None:
    db = _get_db(db)
    db.execute(
        "UPDATE optimization_jobs SET status = 'cancelled', finished_at = %s WHERE job_id = %s AND status IN ('queued', 'running')",
        (time.time(), job_id),
    )


def request_cancel(job_id: str, db=None) -> str:
    """Annulation : immédiate si en attente, coopérative si en cours. Retourne le statut résultant."""
    db = _get_db(db)
    now = time.time()
    cur = db.execute(
        "UPDATE optimization_jobs SET status = 'cancelled', finished_at = %s, cancel_requested = 1 "
        "WHERE job_id = %s AND status = 'queued'",
        (now, job_id),
    )
    if getattr(cur, "rowcount", 0) == 1:
        return "cancelled"
    db.execute("UPDATE optimization_jobs SET cancel_requested = 1 WHERE job_id = %s AND status = 'running'", (job_id,))
    job = get_job(job_id, include_plan=False, db=db)
    return (job or {}).get("status", "unknown")


def touch_notified(job_id: str, db=None) -> None:
    db = _get_db(db)
    db.execute("UPDATE optimization_jobs SET last_notified_at = %s WHERE job_id = %s", (time.time(), job_id))


def release_job(job_id: str, worker_id: str, db=None) -> None:
    """Arrêt propre du worker : le job repasse en attente et sera repris (les résultats déjà calculés sont conservés)."""
    db = _get_db(db)
    db.execute(
        "UPDATE optimization_jobs SET status = 'queued', worker_id = NULL WHERE job_id = %s AND worker_id = %s AND status = 'running'",
        (job_id, worker_id),
    )
