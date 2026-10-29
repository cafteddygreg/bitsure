"""Moteur de l'Optimization Lab : validation de la demande, exécution d'un job, résultats et analyses.

Toutes les simulations passent par `strategy_lab.run_backtest_experiment` (le moteur RÉEL de Strategy Lab) avec :
- `raw_params` : injection d'une configuration candidate sans toucher à la configuration de production ;
- `preloaded_df` : les chandeliers sont chargés UNE fois (aucun accès réseau pendant les simulations) ;
- `opt_cache` : nettoyage OHLCV et indicateurs réutilisés entre configurations partageant les mêmes périodes.

Protocole (sans fuite d'information) :
  1. Training (60 %) : toutes les configurations ;
  2. Validation (20 %) : les meilleures (top K) — sert à la sélection ;
  3. Out-of-Sample (20 %) : les mêmes finalistes — jamais utilisé pour choisir, seulement pour détecter le surapprentissage.
"""
from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import strategy_lab as sl

from . import OPTIMIZATION_VERSION
from . import scoring, store
from .space import SpaceError, build_search_space, SUPPORTED_METHODS

logger = logging.getLogger("optimization.engine")

DEFAULT_MIN_TRADES = scoring.MIN_TRADES_DEFAULT
DEFAULT_TOP_K = 20
MAX_TOP_K = 40
VALID_STYLES = ("scalp", "day", "swing")
DISCLAIMER = (
    "Résultats purement historiques et statistiques, obtenus par simulation sur des données passées. "
    "Ils ne garantissent aucune rentabilité future. Le meilleur résultat parmi de nombreuses configurations testées "
    "est biaisé à la hausse (risque de surapprentissage)."
)


class JobCancelled(Exception):
    pass


class JobLost(Exception):
    """Le job a été repris par un autre worker (heartbeat perdu) : ce worker doit s'arrêter sans rien écrire."""


class WorkerShutdown(Exception):
    """Arrêt demandé du worker (SIGTERM) : le job est relâché et sera repris."""


# --------------------------------------------------------------------------------------
# Validation de la demande
# --------------------------------------------------------------------------------------
def estimate_total_steps(n_configs: int, top_k: int) -> int:
    k = min(int(top_k), int(n_configs))
    return 1 + (n_configs + 1) + 2 * (k + 1) + 5


def plan_request(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Valide et normalise la demande. Retourne (request normalisée, plan). Lève SpaceError."""
    if not isinstance(raw, dict):
        raise SpaceError("Requête invalide.")
    symbol = sl._normalize_lab_symbol(raw.get("symbol") or "BTCUSDT")
    if symbol not in sl.SUPPORTED_LAB_SYMBOLS:
        raise SpaceError(f"Symbole non supporté : {symbol}.")
    timeframe = str(raw.get("timeframe") or "15m")
    if timeframe not in sl.SUPPORTED_LAB_TIMEFRAMES:
        raise SpaceError(f"Timeframe non supporté : {timeframe}.")
    market_type = "spot" if str(raw.get("market_type") or "futures").lower() == "spot" else "futures"
    style = str(raw.get("trading_style") or "day").lower()
    if style not in VALID_STYLES:
        raise SpaceError(f"Style inconnu : {style}.")

    base_in = raw.get("params") if isinstance(raw.get("params"), dict) else {}
    for key, val in base_in.items():
        ok, _v, err = sl._coerce_strict_param_value(key, val)
        if not ok:
            raise SpaceError(f"Configuration de base — {err}")

    start_date = str(raw.get("start_date") or "").strip()
    end_date = str(raw.get("end_date") or "").strip()
    s_ms = sl._parse_date_to_ms(start_date, 0) if start_date else 0
    e_ms = sl._parse_date_to_ms(end_date, 0) if end_date else 0
    if start_date and not s_ms:
        raise SpaceError("Date de début invalide.")
    if end_date and not e_ms:
        raise SpaceError("Date de fin invalide.")
    if s_ms and e_ms and e_ms <= s_ms:
        raise SpaceError("La date de fin doit être postérieure à la date de début.")

    try:
        max_candles = int(raw.get("max_candles") or 4000)
        min_trades = int(raw.get("min_trades") or DEFAULT_MIN_TRADES)
        top_k = int(raw.get("top_k") or DEFAULT_TOP_K)
        seed = int(raw.get("seed") if raw.get("seed") is not None else 42)
        max_configs = int(raw["max_configs"]) if raw.get("max_configs") not in (None, "") else None
    except (TypeError, ValueError):
        raise SpaceError("Valeurs numériques invalides (max_candles, min_trades, top_k, seed, max_configs).")
    if not 500 <= max_candles <= sl.OPT_MAX_PERIOD_CANDLES:
        raise SpaceError(f"max_candles doit être entre 500 et {sl.OPT_MAX_PERIOD_CANDLES}.")
    if not 5 <= min_trades <= 500:
        raise SpaceError("min_trades doit être entre 5 et 500.")
    top_k = max(3, min(MAX_TOP_K, top_k))

    method = str(raw.get("method") or "grid").lower()
    if method not in SUPPORTED_METHODS:
        raise SpaceError("Méthode inconnue (grid ou random).")

    space = build_search_space(
        raw.get("parameters") or [], base_params=base_in, trading_style=style,
        method=method, max_configs=max_configs, seed=seed,
    )
    request = {
        "symbol": symbol, "timeframe": timeframe, "market_type": market_type, "trading_style": style,
        "start_date": start_date, "end_date": end_date, "max_candles": max_candles, "method": method,
        "max_configs": max_configs, "seed": seed, "min_trades": min_trades, "top_k": top_k,
        "params": base_in, "parameters": [{"key": p["key"], "values": p["values"]} for p in space["parameters"]],
    }
    return request, space


def public_plan(space: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    """Version légère du plan (sans la liste complète des configurations) pour l'API/l'UI."""
    n_backtests = space["n_configs"] + 1 + 2 * (min(request["top_k"], space["n_configs"]) + 1) + 3 * 4
    # Estimation INDICATIVE (≈ 0,2 ms par bougie simulée mesuré en local ; dépend du CPU du worker)
    per_backtest = 0.0002 * 0.6 * int(request.get("max_candles") or 4000)
    return {
        "method": space["method"],
        "parameters": space["parameters"],
        "total_grid": space["total_grid"],
        "n_configs": space["n_configs"],
        "invalid_skipped": space["invalid_skipped"],
        "warnings": space["warnings"],
        "sample_configs": space["configs"][:5],
        "estimated_backtests": n_backtests,
        "estimated_seconds": round(n_backtests * per_backtest, 0),
        "total_steps": estimate_total_steps(space["n_configs"], request["top_k"]),
    }


# --------------------------------------------------------------------------------------
# Exécution d'un job
# --------------------------------------------------------------------------------------
class _Progress:
    """Heartbeat, progression, annulation et notifications espacées."""

    def __init__(self, job_id: str, worker_id: str, total_steps: int, notifier, db, stop_flag: Optional[Callable[[], bool]],
                 notify_interval: float, user_id: int):
        self.job_id, self.worker_id, self.total_steps = job_id, worker_id, max(1, total_steps)
        self.done_steps = 0
        self.done_configs = 0
        self.stage = "loading_data"
        self.db, self.notifier, self.stop_flag = db, notifier, stop_flag
        self.last_beat = 0.0
        self.last_notify = time.time()
        self.notify_interval = notify_interval
        self.user_id = user_id
        self.job_started = time.time()

    def step(self, n: int = 1, config_done: bool = False, force: bool = False) -> None:
        self.done_steps += n
        if config_done:
            self.done_configs += n
        now = time.time()
        if force or now - self.last_beat >= 3.0:
            self.beat()
        if self.notifier and now - self.last_notify >= self.notify_interval:
            self.last_notify = now
            try:
                self.notifier.progress(self.user_id, self.job_id, self.stage, self.pct(), self.done_configs)
            except Exception:
                logger.debug("notify progress failed", exc_info=True)

    def pct(self) -> float:
        return round(min(99.0, 100.0 * self.done_steps / self.total_steps), 1)

    def beat(self) -> None:
        self.last_beat = time.time()
        owner_ok, cancel = store.heartbeat(
            self.job_id, self.worker_id,
            {"stage": self.stage, "done_configs": self.done_configs, "done_steps": self.done_steps,
             "total_steps": self.total_steps, "progress_pct": self.pct()},
            db=self.db,
        )
        if not owner_ok:
            raise JobLost(self.job_id)
        if cancel:
            raise JobCancelled(self.job_id)
        if self.stop_flag and self.stop_flag():
            raise WorkerShutdown(self.job_id)


def _isoformat(ts: Any) -> str:
    return ts.isoformat() if hasattr(ts, "isoformat") else str(ts)


def _override_subset(params: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    return {k: params.get(k) for k in keys}


def run_job(
    job_id: str,
    worker_id: str,
    db=None,
    notifier=None,
    loader: Optional[Callable[..., Tuple[Any, str, Dict[str, Any]]]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
) -> str:
    """Exécute (ou reprend) un job déjà réservé par `worker_id`. Retourne le statut final."""
    t_start = time.time()
    job = store.get_job(job_id, db=db)
    if not job:
        raise ValueError(f"Job introuvable : {job_id}")
    req, plan = job["request"], job["plan"]
    configs: List[Dict[str, Any]] = plan["configs"]
    base: Dict[str, Any] = plan["base_params"]
    n = len(configs)
    parameters = plan["parameters"]
    param_keys = [p["key"] for p in parameters]
    min_trades = int(req.get("min_trades") or DEFAULT_MIN_TRADES)
    top_k = max(3, min(MAX_TOP_K, int(req.get("top_k") or DEFAULT_TOP_K)))
    symbol, tf, market, style = req["symbol"], req["timeframe"], req["market_type"], req["trading_style"]
    loader = loader or sl.load_historical_candles
    interval = max(60.0, float(os.getenv("OPT_NOTIFY_INTERVAL_SECONDS", "900")))
    resumed = int(job.get("attempts") or 1) > 1 or int(job.get("done_steps") or 0) > 0

    prog = _Progress(job_id, worker_id, estimate_total_steps(n, top_k), notifier, db, stop_flag, interval, int(job["user_id"]))
    prog.done_steps = 0
    try:
        if notifier:
            notifier.started(prog.user_id, job_id, req, n, resumed)

        # ---------------- Données (une seule fois) ----------------
        prog.stage = "loading_data"
        prog.beat()
        slow_candidates = [int(base["sma_slow"]), int(base.get("sr_lookback", 50)), 26]
        for p in parameters:
            if p["key"] in ("sma_slow", "sr_lookback"):
                slow_candidates.extend(int(v) for v in p["values"])
        warmup = max(60, 3 * max(slow_candidates))
        loader_kwargs = dict(
            symbol=symbol, timeframe=tf, market_type=market,
            start_date=req.get("start_date") or None, end_date=req.get("end_date") or None,
            max_candles=int(req.get("max_candles") or 4000), warmup_candles=warmup,
        )
        # Plafond propre à l'optimiseur (OPT_MAX_PERIOD_CANDLES) : sans lui le chargeur retombe sur le plafond
        # du Strategy Lab et tronquait silencieusement les fenêtres 1m/5m/15m.
        import inspect
        _params = inspect.signature(loader).parameters
        if "max_period_candles" in _params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in _params.values()):
            loader_kwargs["max_period_candles"] = sl.OPT_MAX_PERIOD_CANDLES
        raw_df, data_source, _stats = loader(**loader_kwargs)
        total_n = len(raw_df)
        if total_n <= warmup + 100:
            raise ValueError(
                f"Données insuffisantes : {total_n} bougies pour un warm-up de {warmup} + au moins 100 bougies simulées."
            )
        timestamps = list(raw_df.index)
        # Fenêtre de simulation IDENTIQUE pour toutes les configurations (sinon un SMA plus long démarrerait plus tard).
        req_start = sl._parse_date_to_ms(req.get("start_date"), 0) if req.get("start_date") else 0
        sim_start_idx = warmup
        if req_start:
            for pos, ts in enumerate(timestamps):
                ms = int(ts.timestamp() * 1000) if hasattr(ts, "timestamp") else 0
                if ms >= req_start:
                    sim_start_idx = max(pos, 1)
                    break
        window_n = total_n - sim_start_idx
        if window_n < 100:
            raise ValueError(f"Période simulée trop courte ({window_n} bougies, minimum 100 pour séparer training/validation/OOS).")
        start_iso = _isoformat(timestamps[sim_start_idx])
        n_train, n_val = int(window_n * 0.60), int(window_n * 0.20)
        windows = {
            "training": {"candles": n_train, "start": _isoformat(timestamps[sim_start_idx]), "end": _isoformat(timestamps[sim_start_idx + n_train - 1])},
            "validation": {"candles": n_val, "start": _isoformat(timestamps[sim_start_idx + n_train]), "end": _isoformat(timestamps[sim_start_idx + n_train + n_val - 1])},
            "oos": {"candles": window_n - n_train - n_val, "start": _isoformat(timestamps[sim_start_idx + n_train + n_val]), "end": _isoformat(timestamps[-1])},
        }
        run_warnings: List[str] = []
        _stats = _stats if isinstance(_stats, dict) else {}
        if _stats.get("period_clamped"):
            run_warnings.append(
                f"Période tronquée : la fenêtre demandée dépasse {_stats.get('max_period_candles')} bougies, seules les plus récentes ont été simulées."
            )
        if _stats.get("fetch_incomplete"):
            run_warnings.append("Téléchargement Binance incomplet : des bougies manquent dans la période simulée.")
        if n_train < 300:
            run_warnings.append("Fenêtre de training courte (< 300 bougies) : résultats statistiquement fragiles.")
        prog.step(1, force=True)

        cache: Dict[str, Any] = {}
        SPLIT_NAMES = {"training": "dev", "validation": "validation", "oos": "test"}

        def evaluate(override: Dict[str, Any], stage: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
            params = dict(base)
            params.update(override)
            try:
                res = sl.run_backtest_experiment(
                    symbol=symbol, timeframe=tf, trading_style=style, market_type=market,
                    period_split=SPLIT_NAMES[stage], start_date=start_iso, raw_params=params,
                    max_candles=total_n, allow_unreliable_data=True, preloaded_df=(raw_df, data_source),
                    opt_cache=cache, lean=True,
                )
                return scoring.slim_metrics(res["metrics"], res.get("candles_count", 0)), res
            except Exception as exc:  # une configuration en erreur ne doit pas arrêter le job
                logger.warning("[%s] config en erreur (%s): %s", job_id, stage, exc)
                return {"error": str(exc)[:300], "total_trades": 0}, None

        all_ids = [-1] + list(range(n))   # -1 = configuration actuelle de Bitsure (référence)
        override_of = {-1: {}}
        override_of.update({i: configs[i] for i in range(n)})

        def run_stage(stage: str, ids: List[int], label: str, count_configs: bool) -> Dict[int, Dict[str, Any]]:
            prog.stage = label
            done = store.load_results(job_id, stage, db=db)
            buffer: List[Tuple[int, str, Dict[str, Any], Dict[str, Any]]] = []
            last_flush = time.time()
            for idx in ids:
                if idx in done:
                    prog.step(1, config_done=count_configs)
                    continue
                metrics, _ = evaluate(override_of[idx], stage)
                done[idx] = {"params": override_of[idx], "metrics": metrics}
                buffer.append((idx, stage, override_of[idx], metrics))
                if len(buffer) >= 10 or time.time() - last_flush > 10:
                    store.save_results(job_id, buffer, db=db)
                    buffer, last_flush = [], time.time()
                prog.step(1, config_done=count_configs)
            if buffer:
                store.save_results(job_id, buffer, db=db)
            prog.beat()
            return done

        # ---------------- Stage 1 : training ----------------
        train_raw = run_stage("training", all_ids, "search", True)
        train: Dict[int, Dict[str, Any]] = {}
        n_errors = 0
        for idx, rec in train_raw.items():
            m = rec["metrics"]
            if m.get("error"):
                n_errors += 1
            train[idx] = {"metrics": m, "score": scoring.performance_score(m, min_trades)}
        if n_errors >= len(train_raw):
            raise RuntimeError("Toutes les configurations ont échoué dans le moteur de backtest.")
        if n_errors:
            run_warnings.append(f"{n_errors} configuration(s) en erreur dans le moteur (ignorées).")

        scored = [i for i in range(n) if train.get(i, {}).get("score") is not None]
        scored.sort(key=lambda i: train[i]["score"], reverse=True)
        finalists_ids = scored[:top_k]
        if not scored:
            run_warnings.append(
                f"Aucune configuration n'atteint {min_trades} trades en training : élargissez la période, le timeframe ou baissez le minimum de trades."
            )

        # ---------------- Stages 2 & 3 : validation + OOS ----------------
        eval_ids = [-1] + finalists_ids
        val_raw = run_stage("validation", eval_ids, "validation", False)
        oos_raw = run_stage("oos", eval_ids, "oos", False)

        # ---------------- Analyse ----------------
        prog.stage = "analysis"
        prog.beat()
        overrides_scored = {i: configs[i] for i in range(n)}
        vectors = scoring.build_vectors(overrides_scored, parameters)
        entries: Dict[int, Dict[str, Any]] = {}
        for idx in eval_ids:
            t_m = train[idx]["metrics"]
            v_m = val_raw[idx]["metrics"] if idx in val_raw else None
            o_m = oos_raw[idx]["metrics"] if idx in oos_raw else None
            t_s = train[idx]["score"]
            v_s = scoring.performance_score(v_m, max(3, min_trades // 3)) if v_m else None
            o_s = scoring.performance_score(o_m, max(3, min_trades // 3)) if o_m else None
            if idx >= 0:
                nb = scoring.neighbor_stats(idx, {i: train[i] for i in range(n) if i in train}, overrides_scored, parameters, vectors=vectors)
            else:
                nb = {"n": 0, "mean": None, "min": None, "std": None, "mean_distance": None, "stability": 0.0}
            cons = scoring.consistency(t_m, v_m, t_s, v_s)
            rob = scoring.robustness_score(nb, cons, t_m) if t_s is not None else None
            flags = scoring.overfit_flags(t_m, v_m, o_m, nb, n_tested=n, min_trades=min_trades)
            comp = None
            if t_s is not None:
                comp = round(0.5 * t_s + 0.5 * v_s, 4) if v_s is not None else round(0.5 * t_s, 4)
            entries[idx] = {
                "idx": idx, "params": override_of[idx],
                "training": t_m, "validation": v_m, "oos": o_m,
                "training_score": t_s, "validation_score": v_s, "oos_score": o_s,
                "neighbors": nb, "consistency": cons, "robustness": rob, "compromise": comp, "overfit": flags,
            }
        prog.step(1)

        finalists = [entries[i] for i in finalists_ids]
        categories: Dict[str, Optional[int]] = {"best_raw": None, "best_compromise": None, "best_robust": None, "best_overall": None}
        if finalists:
            categories["best_raw"] = max(
                finalists, key=lambda e: (_f(e["training"].get("total_return_pct")), e["training_score"] or -1e9))["idx"]
            categories["best_compromise"] = max(finalists, key=lambda e: e["compromise"] if e["compromise"] is not None else -1e9)["idx"]
            # Les catégories « robuste » et « global » excluent les candidats à risque de surapprentissage élevé
            # (OOS/validation qui contredit l'entraînement). Si TOUS sont à risque élevé, on garde le classement mais
            # un avertissement est ajouté au résumé.
            pool = [e for e in finalists if e["overfit"]["risk"] != "high"] or finalists
            if all(e["overfit"]["risk"] == "high" for e in finalists):
                run_warnings.append("Tous les finalistes présentent un risque de surapprentissage élevé : aucun résultat n'est à considérer comme robuste.")
            categories["best_robust"] = max(pool, key=lambda e: e["robustness"] if e["robustness"] is not None else -1e9)["idx"]
            categories["best_overall"] = max(
                pool, key=lambda e: 0.5 * (e["compromise"] or 0.0) + 0.5 * (e["robustness"] or 0.0))["idx"]
        prog.step(1)

        sens = scoring.sensitivity(parameters, overrides_scored, {i: train[i] for i in range(n) if i in train})
        prog.step(1)

        # ---------------- Détails des configurations retenues (courbes d'equity + Monte Carlo) ----------------
        prog.stage = "finalizing"
        prog.beat()
        details: Dict[str, Any] = {}
        detail_ids = sorted({i for i in categories.values() if i is not None} | {-1})
        for idx in detail_ids:
            per_split: Dict[str, Any] = {}
            pooled: List[float] = []
            init_cap = float(base.get("initial_capital", 10000.0))
            for stage in ("training", "validation", "oos"):
                metrics, res = evaluate(override_of[idx], stage)
                if res is None:
                    continue
                pnls = [float(t.get("pnl_usdt", 0.0)) for t in res.get("trades", [])]
                pooled.extend(pnls)
                eq = [round(float(p["equity"]), 2) for p in sl._downsample_list(res.get("equity_curve", []), 120)]
                per_split[stage] = {"equity": eq, "n_trades": len(pnls), "start": res.get("start_date"),
                                    "end": res.get("end_date"), "candles": res.get("candles_count")}
                if stage == "oos":
                    per_split[stage]["monte_carlo"] = scoring.monte_carlo(pnls, init_cap)
            details[str(idx)] = {"splits": per_split, "monte_carlo_all": scoring.monte_carlo(pooled, init_cap)}
        prog.step(1)
        # Fenêtres réellement simulées par le moteur (source de vérité pour le rapport)
        for stage, w in (details.get("-1", {}).get("splits", {}) or {}).items():
            if stage in windows and w.get("start"):
                windows[stage] = {"candles": w.get("candles"), "start": w.get("start"), "end": w.get("end")}

        def pub(e: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if e is None:
                return None
            out = dict(e)
            out["params_full"] = _override_subset({**base, **e["params"]}, param_keys)
            return out

        summary: Dict[str, Any] = {
            "version": OPTIMIZATION_VERSION,
            "job_id": job_id, "symbol": symbol, "timeframe": tf, "market_type": market, "trading_style": style,
            "data_source": data_source, "engine_version": sl.ENGINE_VERSION, "strategy_version": sl.STRATEGY_VERSION,
            "method": plan["method"], "seed": plan.get("seed"), "parameters": parameters, "param_keys": param_keys,
            "n_configs": n, "n_scored": len(scored), "n_errors": n_errors, "min_trades": min_trades, "top_k": top_k,
            "period": {"warmup_candles": warmup, "total_candles": total_n, "simulated_candles": window_n, "windows": windows},
            "baseline": pub(entries[-1]),
            "finalists": [pub(e) for e in finalists],
            "categories": categories,
            "details": details,
            "sensitivity": sens,
            "warnings": list(plan.get("warnings", [])) + run_warnings,
            "walk_forward": {"available": False, "reason": "Non implémenté : le moteur actuel n'expose pas de fenêtres glissantes ; la stabilité temporelle est évaluée via training/validation/OOS."},
            "selection_protocol": "Classement sur training + validation ; l'OOS ne modifie aucun score, mais les candidats que l'OOS contredit (risque élevé) sont exclus des choix « robuste » et « global ».",
            "disclaimer": DISCLAIMER,
            "duration_seconds": round(time.time() - float(job.get("started_at") or t_start), 1),
            "compute_seconds_this_run": round(time.time() - t_start, 1),
            "base_params": _override_subset(base, param_keys),
            # Contexte complet de la course : permet de recharger un candidat dans l'éditeur avec EXACTEMENT
            # la config testée (risque, levier, etc.), pas seulement les paramètres balayés.
            "base_params_full": {k: v for k, v in base.items() if isinstance(v, (int, float, str, bool)) or v is None},
            "request_period": {"start_date": req.get("start_date"), "end_date": req.get("end_date"), "max_candles": req.get("max_candles")},
        }
        from .report import build_report_html
        html = build_report_html(summary)
        prog.step(1)
        if not store.mark_completed(job_id, worker_id, summary, html, db=db):
            raise JobLost(job_id)
        if notifier:
            notifier.finished(prog.user_id, job_id, summary, html)
        return "completed"

    except JobCancelled:
        store.mark_cancelled(job_id, db=db)
        if notifier:
            notifier.cancelled(prog.user_id, job_id)
        return "cancelled"
    except WorkerShutdown:
        store.release_job(job_id, worker_id, db=db)
        return "released"
    except JobLost:
        logger.warning("[%s] job repris par un autre worker : arrêt sans écriture", job_id)
        return "lost"
    except Exception as exc:
        logger.error("[%s] échec à l'étape %s: %s", job_id, prog.stage, exc, exc_info=True)
        msg = f"[{prog.stage}] {type(exc).__name__}: {exc}"
        store.mark_failed(job_id, msg, worker_id=worker_id, db=db)
        if notifier:
            notifier.failed(prog.user_id, job_id, prog.stage, str(exc))
        return "failed"


def _f(v: Any) -> float:
    try:
        f = float(v)
        return f if not math.isnan(f) else -1e9
    except (TypeError, ValueError):
        return -1e9
