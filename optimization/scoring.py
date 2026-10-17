"""Scores, robustesse, sensibilité, surapprentissage et Monte Carlo — uniquement à partir des résultats réels du moteur."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

MIN_TRADES_DEFAULT = 20
PF_CAP = 10.0

# Sous-ensemble de métriques conservées (jamais de métrique inventée : absente => None / N/A)
SLIM_METRIC_KEYS = (
    "total_return_pct", "net_profit_usdt", "win_rate_pct", "total_trades", "profit_factor", "payoff_ratio",
    "expectancy_usdt", "avg_r_multiple", "avg_win_usdt", "avg_loss_usdt", "max_drawdown_pct", "sharpe_ratio",
    "sortino_ratio", "calmar_ratio", "buy_hold_return_pct", "alpha_vs_buy_hold_pct", "max_win_streak",
    "max_loss_streak", "avg_duration_minutes", "avg_bars_held", "long_trades", "short_trades",
    "long_win_rate_pct", "short_win_rate_pct", "long_pnl_usdt", "short_pnl_usdt", "by_exit_reason",
    "total_execution_costs_usdt",
)


def _num(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(f):
        return default
    if math.isinf(f):
        return PF_CAP if f > 0 else -PF_CAP
    return f


def slim_metrics(metrics: Dict[str, Any], candles_count: int = 0) -> Dict[str, Any]:
    out = {k: metrics.get(k) for k in SLIM_METRIC_KEYS if k in metrics}
    for k, v in list(out.items()):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            out[k] = PF_CAP if (v > 0 and not math.isnan(v)) else None
    out["candles_count"] = int(candles_count or 0)
    return out


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def performance_score(m: Optional[Dict[str, Any]], min_trades: int = MIN_TRADES_DEFAULT) -> Optional[float]:
    """Score composite (0-100 environ) : rendement/drawdown, profit factor, R moyen, pondéré par le nombre de trades.

    Retourne None si trop peu de trades (résultat non exploitable statistiquement) ou en cas d'erreur.
    """
    if not m or m.get("error"):
        return None
    trades = int(_num(m.get("total_trades"), 0) or 0)
    if trades < min_trades:
        return None
    ret = _num(m.get("total_return_pct"), 0.0)
    dd = _num(m.get("max_drawdown_pct"), 0.0)
    pf = _num(m.get("profit_factor"), 0.0)
    avg_r = _num(m.get("avg_r_multiple"), 0.0)
    calmar_like = ret / max(abs(dd), 1.0)
    reliability = min(1.0, math.sqrt(trades / 60.0))
    perf = (
        0.40 * clip(calmar_like, -3.0, 8.0) / 8.0
        + 0.30 * clip(pf - 1.0, -1.0, 3.0) / 3.0
        + 0.30 * clip(avg_r, -0.5, 1.0) / 1.0
    )
    return round(100.0 * perf * reliability, 4)


def _norm_vector(params: Dict[str, Any], parameters: List[Dict[str, Any]]) -> List[float]:
    vec = []
    for p in parameters:
        vals = p["values"]
        v = params.get(p["key"])
        try:
            fv = [float(x) for x in vals]
            lo, hi = min(fv), max(fv)
            vec.append(0.0 if hi == lo else (float(v) - lo) / (hi - lo))
        except (TypeError, ValueError):
            vec.append(float(vals.index(v)) / max(1, len(vals) - 1) if v in vals else 0.0)
    return vec


def build_vectors(overrides: Dict[int, Dict[str, Any]], parameters: List[Dict[str, Any]]) -> Dict[int, List[float]]:
    """Position normalisée (0-1 par paramètre) de chaque configuration — calculée une seule fois par job."""
    return {i: _norm_vector(ov, parameters) for i, ov in overrides.items()}


def neighbor_stats(
    idx: int,
    train: Dict[int, Dict[str, Any]],
    overrides: Dict[int, Dict[str, Any]],
    parameters: List[Dict[str, Any]],
    k: int = 6,
    vectors: Optional[Dict[int, List[float]]] = None,
) -> Dict[str, Any]:
    """Performance des k configurations les plus proches (espace des paramètres normalisé)."""
    own = train.get(idx, {}).get("score")
    vectors = vectors if vectors is not None else build_vectors(overrides, parameters)
    ids = [j for j, rec in train.items() if j != idx and rec.get("score") is not None and j in vectors]
    if own is None or not ids:
        return {"n": 0, "mean": None, "min": None, "std": None, "mean_distance": None, "stability": 0.0}
    mat = np.asarray([vectors[j] for j in ids], dtype=float)
    me = np.asarray(vectors[idx], dtype=float)
    dist = np.abs(mat - me).sum(axis=1)
    order = np.argsort(dist, kind="stable")[:k]
    scores = np.asarray([train[ids[o]]["score"] for o in order], dtype=float)
    mean = float(scores.mean())
    stability = 0.0 if own <= 0 else clip(mean / own, 0.0, 1.0)
    if float(scores.min()) < 0:
        stability *= 0.7
    return {
        "n": int(len(order)),
        "mean": round(mean, 4),
        "min": round(float(scores.min()), 4),
        "std": round(float(scores.std()), 4),
        "mean_distance": round(float(dist[order].mean()), 4),
        "stability": round(float(stability), 4),
    }


def consistency(train_m: Dict[str, Any], val_m: Optional[Dict[str, Any]], train_s: Optional[float], val_s: Optional[float]) -> float:
    """Cohérence training/validation (0-1) : proximité des scores + accord de signe du rendement."""
    if not val_m or train_s is None or val_s is None:
        return 0.0
    denom = max(abs(train_s), abs(val_s), 1.0)
    closeness = 1.0 - clip(abs(train_s - val_s) / denom, 0.0, 1.0)
    same_sign = 1.0 if (_num(train_m.get("total_return_pct"), 0.0) > 0) == (_num(val_m.get("total_return_pct"), 0.0) > 0) else 0.0
    return round(0.6 * closeness + 0.4 * same_sign, 4)


def robustness_score(nb: Dict[str, Any], cons: float, train_m: Dict[str, Any]) -> float:
    dd = abs(_num(train_m.get("max_drawdown_pct"), 0.0) or 0.0)
    trades = int(_num(train_m.get("total_trades"), 0) or 0)
    risk_factor = (1.0 - clip(dd / 30.0, 0.0, 1.0)) * min(1.0, math.sqrt(trades / 60.0))
    return round(100.0 * (0.45 * nb.get("stability", 0.0) + 0.35 * cons + 0.20 * risk_factor), 4)


def overfit_flags(
    train_m: Dict[str, Any],
    val_m: Optional[Dict[str, Any]],
    oos_m: Optional[Dict[str, Any]],
    nb: Dict[str, Any],
    n_tested: int,
    min_trades: int = MIN_TRADES_DEFAULT,
) -> Dict[str, Any]:
    flags: List[str] = []
    t_ret = _num(train_m.get("total_return_pct"), 0.0)
    t_pf = _num(train_m.get("profit_factor"), 0.0)
    if val_m is None:
        flags.append("validation_unavailable")
    else:
        v_ret = _num(val_m.get("total_return_pct"), 0.0)
        if t_ret > 0 and v_ret <= 0:
            flags.append("validation_loss")
        elif t_ret > 0 and v_ret < 0.3 * t_ret:
            flags.append("validation_drop")
    if oos_m is None:
        flags.append("oos_unavailable")
    else:
        o_ret = _num(oos_m.get("total_return_pct"), 0.0)
        o_pf = _num(oos_m.get("profit_factor"), 0.0)
        o_trades = int(_num(oos_m.get("total_trades"), 0) or 0)
        if t_ret > 0 and o_ret <= 0:
            flags.append("oos_collapse")
        elif t_pf > 1.3 and o_pf < 1.0:
            flags.append("oos_profit_factor_below_1")
        if o_trades < max(5, min_trades // 4):
            flags.append("oos_few_trades")
    if nb.get("stability", 0.0) < 0.5:
        flags.append("isolated_peak")
    if int(_num(train_m.get("total_trades"), 0) or 0) < 2 * min_trades:
        flags.append("few_training_trades")
    severe = {"validation_loss", "oos_collapse", "oos_profit_factor_below_1"}
    n_sev = sum(1 for f in flags if f in severe)
    n_minor = sum(1 for f in flags if f in {"validation_drop", "isolated_peak", "few_training_trades", "oos_few_trades"})
    risk = "high" if n_sev >= 1 or n_minor >= 3 else ("medium" if n_minor >= 1 else "low")
    return {"flags": flags, "risk": risk, "selection_bias_note": n_tested > 1, "n_tested": n_tested}


def sensitivity(
    parameters: List[Dict[str, Any]],
    overrides: Dict[int, Dict[str, Any]],
    train: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Score training moyen par valeur de chaque paramètre + amplitude (sensibilité). Un seul passage sur les configurations."""
    all_scores = [r["score"] for r in train.values() if r.get("score") is not None]
    overall_std = float(np.std(all_scores)) if len(all_scores) > 1 else 0.0
    acc: Dict[str, Dict[str, List[float]]] = {p["key"]: {} for p in parameters}
    for i, ov in overrides.items():
        sc = train.get(i, {}).get("score")
        if sc is None:
            continue
        for p in parameters:
            acc[p["key"]].setdefault(repr(ov.get(p["key"])), []).append(sc)
    out = []
    for p in parameters:
        rows = []
        for v in p["values"]:
            sc = acc[p["key"]].get(repr(v), [])
            rows.append({"value": v, "n": len(sc), "mean_score": round(float(np.mean(sc)), 4) if sc else None,
                         "max_score": round(float(np.max(sc)), 4) if sc else None})
        means = [r["mean_score"] for r in rows if r["mean_score"] is not None]
        spread = (max(means) - min(means)) if len(means) >= 2 else 0.0
        out.append({
            "key": p["key"],
            "values": rows,
            "spread": round(spread, 4),
            "importance": round(spread / overall_std, 4) if overall_std > 1e-9 else None,
        })
    out.sort(key=lambda r: (r["importance"] is None, -(r["importance"] or 0.0)))
    return out


def monte_carlo(pnls: Sequence[float], initial_capital: float, n_sims: int = 1000, seed: int = 7) -> Optional[Dict[str, Any]]:
    """Bootstrap des P&L réels des trades (avec remise) : distribution du rendement final et du drawdown."""
    arr = np.asarray([p for p in pnls if p is not None and not math.isnan(p)], dtype=float)
    if len(arr) < 10 or initial_capital <= 0:
        return None
    rng = np.random.default_rng(seed)
    draws = rng.choice(arr, size=(n_sims, len(arr)), replace=True)
    curves = initial_capital + np.cumsum(draws, axis=1)
    peaks = np.maximum.accumulate(np.concatenate([np.full((n_sims, 1), initial_capital), curves], axis=1), axis=1)[:, 1:]
    dd = (peaks - curves) / np.maximum(peaks, 1e-9) * 100.0
    final_ret = (curves[:, -1] / initial_capital - 1.0) * 100.0
    max_dd = dd.max(axis=1)
    return {
        "n_sims": int(n_sims),
        "n_trades": int(len(arr)),
        "return_p5": round(float(np.percentile(final_ret, 5)), 2),
        "return_p50": round(float(np.percentile(final_ret, 50)), 2),
        "return_p95": round(float(np.percentile(final_ret, 95)), 2),
        "max_dd_p50": round(float(np.percentile(max_dd, 50)), 2),
        "max_dd_p95": round(float(np.percentile(max_dd, 95)), 2),
        "prob_loss_pct": round(float((final_ret < 0).mean() * 100.0), 1),
    }
