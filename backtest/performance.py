"""Performance metrics and export helpers for backtest results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


TIMEFRAME_MINUTES_MAP: Dict[str, float] = {
    "1m": 1.0,
    "3m": 3.0,
    "5m": 5.0,
    "15m": 15.0,
    "30m": 30.0,
    "1h": 60.0,
    "2h": 120.0,
    "4h": 240.0,
    "6h": 360.0,
    "8h": 480.0,
    "12h": 720.0,
    "1d": 1440.0,
    "1w": 10080.0,
}


def periods_per_year_for_timeframe(timeframe: Optional[str] = None, equity_curve: Optional[pd.DataFrame] = None) -> float:
    """Calcule le nombre de périodes par an (365.25 jours 24/7) selon le timeframe ou l'index de la courbe."""
    minutes_per_year = 365.25 * 24.0 * 60.0
    if timeframe:
        tf_norm = str(timeframe).strip().lower()
        if tf_norm in TIMEFRAME_MINUTES_MAP:
            return minutes_per_year / TIMEFRAME_MINUTES_MAP[tf_norm]
        if tf_norm.endswith("m") and tf_norm[:-1].isdigit():
            return minutes_per_year / max(1.0, float(tf_norm[:-1]))
        if tf_norm.endswith("h") and tf_norm[:-1].isdigit():
            return minutes_per_year / max(1.0, float(tf_norm[:-1]) * 60.0)
        if tf_norm.endswith("d") and tf_norm[:-1].isdigit():
            return minutes_per_year / max(1.0, float(tf_norm[:-1]) * 1440.0)

    if equity_curve is not None and not equity_curve.empty and isinstance(equity_curve.index, pd.DatetimeIndex) and len(equity_curve.index) >= 2:
        diffs = pd.Series(equity_curve.index).diff().dropna().dt.total_seconds() / 60.0
        diffs = diffs[diffs > 0]
        if not diffs.empty:
            median_min = float(diffs.median())
            if median_min > 0:
                return minutes_per_year / median_min

    return 365.25


def _trade_r_multiple(trade: Dict[str, Any]) -> Optional[float]:
    if trade.get("r_multiple") is not None:
        try:
            return float(trade["r_multiple"])
        except (TypeError, ValueError):
            pass
    pnl_net = float(trade.get("pnl_net", 0.0) or 0.0)
    initial_risk = trade.get("initial_risk")
    if initial_risk is None:
        try:
            entry_p = float(trade.get("entry_price") or 0.0)
            sl_p = float(trade.get("initial_sl") if trade.get("initial_sl") is not None else (trade.get("sl") or 0.0))
            qty = float(trade.get("qty") or 0.0)
            dist = abs(entry_p - sl_p)
            if dist > 0 and qty > 0:
                initial_risk = dist * qty
        except (TypeError, ValueError):
            initial_risk = None
    try:
        if initial_risk is not None and float(initial_risk) > 0:
            return pnl_net / float(initial_risk)
    except (TypeError, ValueError):
        pass
    return None


def build_summary(
    trades: List[Dict],
    equity_curve: pd.DataFrame,
    initial_capital: float,
    *,
    timeframe: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict:
    closed = [t for t in trades if t.get("status") == "closed" or "pnl_net" in t]
    wins = [t for t in closed if t.get("pnl_net", 0) > 0]
    losses = [t for t in closed if t.get("pnl_net", 0) <= 0]
    gross_profit = sum(float(t.get("pnl_net", 0) or 0.0) for t in wins)
    gross_loss = abs(sum(float(t.get("pnl_net", 0) or 0.0) for t in losses))
    final_equity = float(equity_curve["equity"].iloc[-1]) if not equity_curve.empty else (
        initial_capital + sum(float(t.get("pnl_net", 0) or 0.0) for t in closed)
    )
    returns = (
        equity_curve["equity"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        if not equity_curve.empty
        else pd.Series(dtype=float)
    )
    periods_per_year = periods_per_year_for_timeframe(timeframe=timeframe, equity_curve=equity_curve)
    sharpe = None
    if not returns.empty and returns.std() != 0 and not np.isnan(returns.std()):
        sharpe = float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))
    drawdown = 0.0
    if not equity_curve.empty:
        running_max = equity_curve["equity"].cummax()
        dd = (equity_curve["equity"] - running_max) / running_max.replace(0, np.nan)
        if not dd.dropna().empty:
            drawdown = float(dd.min() * 100)
    durations = [t.get("duration_bars", 0) for t in closed]

    expectancy = float(np.mean([float(t.get("pnl_net", 0.0) or 0.0) for t in closed])) if closed else 0.0
    r_multiples = [r for r in (_trade_r_multiple(t) for t in closed) if r is not None]
    expectancy_r = float(np.mean(r_multiples)) if r_multiples else 0.0

    period_returns = pd.Series(dtype=float)
    if not equity_curve.empty and isinstance(equity_curve.index, pd.DatetimeIndex):
        try:
            period_returns = equity_curve["equity"].resample("ME").last().pct_change().dropna()
        except Exception:
            period_returns = equity_curve["equity"].resample("M").last().pct_change().dropna()

    summary: Dict[str, Any] = {
        "total_trades": len(closed),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round((len(wins) / len(closed) * 100), 2) if closed else 0.0,
        "initial_capital": initial_capital,
        "final_equity": round(final_equity, 8),
        "net_profit": round(final_equity - initial_capital, 8),
        "net_profit_pct": round(((final_equity - initial_capital) / initial_capital * 100), 4) if initial_capital else 0.0,
        "expectancy": round(expectancy, 8),
        "expectancy_r": round(expectancy_r, 6),
        "max_drawdown_pct": round(drawdown, 4),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "periods_per_year": round(periods_per_year, 2),
        "best_period": str(period_returns.idxmax().date()) if not period_returns.empty else None,
        "worst_period": str(period_returns.idxmin().date()) if not period_returns.empty else None,
        "average_trade_duration_bars": round(float(np.mean(durations)), 2) if durations else 0.0,
    }
    if metadata:
        summary.update(metadata)
    return summary


def export_results(results_dir: Path, trades: List[Dict], equity_curve: pd.DataFrame, summary: Dict) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(trades).to_csv(results_dir / "trades.csv", index=False)
    equity_curve.to_csv(results_dir / "equity_curve.csv")
    with (results_dir / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False, default=str)
