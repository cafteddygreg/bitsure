"""
strategy_lab.py — Bitsure Teddy Admin-Only Strategy Lab & Backtesting Engine
===========================================================================
STRICT ISOLATION GUARANTEE:
- This module is 100% isolated from live order execution, Binance trading endpoints,
  PaperTrader balances, and user auto-trading loops.
- It NEVER imports `live_trader`, `position_manager`, or any order placement function
  from `binance_manager`.
- All historical candles are persisted per-candle in `strategy_lab_ohlcv` keyed by
  (market_type, symbol, timeframe, open_time_ms) to avoid redundant downloads.
- All experiments are stored in `strategy_lab_runs` with full reproducibility metadata.
"""

import os
import json
import time
import math
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd

from database import get_db
from indicators import macd, adx, bollinger_bands, rsi as calc_rsi, atr as calc_atr
from data_fetcher import normalize_symbol

logger = logging.getLogger("strategy_lab")

ENGINE_VERSION = "2.1.0"
STRATEGY_VERSION = "teddy_confluence_v2"
FORBIDDEN_LIVE_MODULES = ("live_trader", "position_manager")

SUPPORTED_LAB_MARKETS = ["futures", "spot"]

SUPPORTED_LAB_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "XAUUSD",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
]


def _normalize_lab_symbol(raw_symbol: Optional[str]) -> str:
    """Normalizes symbols for Strategy Lab (supports documented symbols + extended crypto research pairs)."""
    s = str(raw_symbol or "BTCUSDT").strip().upper().replace("/", "").replace("-", "")
    if s in ("XAUUSD", "GOLD", "XAUUSDT", "PAXGUSDT"):
        return "XAUUSD"
    if s in SUPPORTED_LAB_SYMBOLS:
        return s
    try:
        return normalize_symbol(s)
    except Exception:
        if s.endswith("USDT") and len(s) >= 6:
            return s
        return "BTCUSDT"

SUPPORTED_LAB_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# Built-in Official Bitsure Strategy Presets (mirrors signal_engine.py STYLE_PARAMS + variations)
DEFAULT_STRATEGY_PRESETS: List[Dict[str, Any]] = [
    {
        "key": "bitsure_day_official",
        "name": "Bitsure Teddy Officiel — Day Trading",
        "description": "Stratégie officielle actuelle de Bitsure (signal_engine.py) équilibrée pour Day Trading 15m/1h.",
        "trading_style": "day",
        "timeframe": "15m",
        "tags": "officiel,day,production",
        "params": {
            "initial_capital": 10000.0,
            "position_sizing_mode": "risk_pct",  # 'risk_pct' | 'fixed_usdt' | 'capital_pct'
            "risk_per_trade_pct": 1.0,
            "fixed_position_usdt": 1000.0,
            "capital_allocation_pct": 10.0,
            "leverage": 2.0,
            "fee_bps": 4.0,          # 0.04% per side
            "slippage_bps": 2.0,     # 0.02% per side
            "allow_long": True,
            "allow_short": True,
            "max_open_positions": 1,
            "cooldown_candles": 2,
            "max_trades_per_day": 8,
            "max_consecutive_losses": 4,
            # Indicators
            "ema_fast": 20,
            "ema_slow": 50,
            "ema_trend": 200,
            "rsi_period": 14,
            "rsi_oversold": 32.0,
            "rsi_overbought": 68.0,
            "adx_period": 14,
            "adx_min": 20.0,
            "atr_period": 14,
            "min_atr_pct": 0.12,
            "volume_ma_period": 20,
            "min_volume_ratio": 0.65,
            # Scoring & Confluence
            "min_teddy_score": 58,
            "require_ema_alignment": True,
            "require_macd_confirmation": True,
            "require_trend_filter_ema200": False,
            "block_against_strong_trend": True,
            # Risk, SL, TP, Trailing, Break-even
            "sl_mode": "atr",        # 'atr' | 'fixed_pct'
            "sl_atr_mult": 1.5,
            "sl_fixed_pct": 1.2,
            "tp_mode": "rr",         # 'rr' | 'atr' | 'fixed_pct'
            "min_rr_ratio": 1.8,
            "tp_atr_mult": 2.8,
            "tp_fixed_pct": 2.4,
            "partial_tp_enabled": True,
            "partial_tp_rr": 1.2,
            "partial_tp_close_pct": 50.0,
            "breakeven_enabled": True,
            "breakeven_trigger_rr": 1.0,
            "trailing_stop_enabled": True,
            "trailing_activation_rr": 1.3,
            "trailing_distance_atr": 1.1,
            "exit_on_opposite_signal": True,
            "max_bars_in_trade": 48,
        },
    },
    {
        "key": "bitsure_scalp_aggressive",
        "name": "Bitsure Scalp Réactif — 5m / 15m",
        "description": "Configuration réactive inspirée du mode Scalp Bitsure : SL resserré (1.2x ATR), prise de profit rapide.",
        "trading_style": "scalp",
        "timeframe": "15m",
        "tags": "officiel,scalp,rapide",
        "params": {
            "initial_capital": 10000.0,
            "position_sizing_mode": "risk_pct",
            "risk_per_trade_pct": 0.8,
            "fixed_position_usdt": 1000.0,
            "capital_allocation_pct": 10.0,
            "leverage": 3.0,
            "fee_bps": 4.0,
            "slippage_bps": 2.0,
            "allow_long": True,
            "allow_short": True,
            "max_open_positions": 1,
            "cooldown_candles": 1,
            "max_trades_per_day": 14,
            "max_consecutive_losses": 4,
            "ema_fast": 12,
            "ema_slow": 26,
            "ema_trend": 100,
            "rsi_period": 14,
            "rsi_oversold": 35.0,
            "rsi_overbought": 65.0,
            "adx_period": 14,
            "adx_min": 18.0,
            "atr_period": 14,
            "min_atr_pct": 0.08,
            "volume_ma_period": 20,
            "min_volume_ratio": 0.75,
            "min_teddy_score": 54,
            "require_ema_alignment": True,
            "require_macd_confirmation": False,
            "require_trend_filter_ema200": False,
            "block_against_strong_trend": True,
            "sl_mode": "atr",
            "sl_atr_mult": 1.2,
            "sl_fixed_pct": 0.8,
            "tp_mode": "rr",
            "min_rr_ratio": 1.5,
            "tp_atr_mult": 1.8,
            "tp_fixed_pct": 1.4,
            "partial_tp_enabled": True,
            "partial_tp_rr": 1.0,
            "partial_tp_close_pct": 50.0,
            "breakeven_enabled": True,
            "breakeven_trigger_rr": 0.8,
            "trailing_stop_enabled": True,
            "trailing_activation_rr": 1.1,
            "trailing_distance_atr": 0.9,
            "exit_on_opposite_signal": True,
            "max_bars_in_trade": 24,
        },
    },
    {
        "key": "bitsure_swing_institutional",
        "name": "Bitsure Swing Institutionnel — Haute Sélectivité",
        "description": "Filtre de tendance strict EMA 200 + ADX >= 24 + Score Teddy >= 65 et R:R minimum de 2.2.",
        "trading_style": "swing",
        "timeframe": "1h",
        "tags": "officiel,swing,conservateur",
        "params": {
            "initial_capital": 10000.0,
            "position_sizing_mode": "risk_pct",
            "risk_per_trade_pct": 1.25,
            "fixed_position_usdt": 1500.0,
            "capital_allocation_pct": 15.0,
            "leverage": 2.0,
            "fee_bps": 4.0,
            "slippage_bps": 2.0,
            "allow_long": True,
            "allow_short": True,
            "max_open_positions": 1,
            "cooldown_candles": 3,
            "max_trades_per_day": 4,
            "max_consecutive_losses": 3,
            "ema_fast": 20,
            "ema_slow": 50,
            "ema_trend": 200,
            "rsi_period": 14,
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "adx_period": 14,
            "adx_min": 24.0,
            "atr_period": 14,
            "min_atr_pct": 0.20,
            "volume_ma_period": 20,
            "min_volume_ratio": 0.85,
            "min_teddy_score": 65,
            "require_ema_alignment": True,
            "require_macd_confirmation": True,
            "require_trend_filter_ema200": True,
            "block_against_strong_trend": True,
            "sl_mode": "atr",
            "sl_atr_mult": 2.0,
            "sl_fixed_pct": 1.8,
            "tp_mode": "rr",
            "min_rr_ratio": 2.2,
            "tp_atr_mult": 4.4,
            "tp_fixed_pct": 4.0,
            "partial_tp_enabled": True,
            "partial_tp_rr": 1.4,
            "partial_tp_close_pct": 50.0,
            "breakeven_enabled": True,
            "breakeven_trigger_rr": 1.1,
            "trailing_stop_enabled": True,
            "trailing_activation_rr": 1.5,
            "trailing_distance_atr": 1.3,
            "exit_on_opposite_signal": False,
            "max_bars_in_trade": 96,
        },
    },
]


def normalize_lab_params(raw_params: Optional[Dict[str, Any]], style: str = "day") -> Dict[str, Any]:
    """Merge user-provided strategy parameters with safe defaults for the selected style."""
    base = dict(DEFAULT_STRATEGY_PRESETS[0]["params"])
    for preset in DEFAULT_STRATEGY_PRESETS:
        if preset["trading_style"] == style:
            base = dict(preset["params"])
            break
    if isinstance(raw_params, dict):
        for k, v in raw_params.items():
            if v is not None:
                base[k] = v

    # Enforce safe numerical bounds
    base["initial_capital"] = max(100.0, min(10_000_000.0, float(base.get("initial_capital", 10000.0))))
    base["risk_per_trade_pct"] = max(0.1, min(25.0, float(base.get("risk_per_trade_pct", 1.0))))
    base["fixed_position_usdt"] = max(10.0, min(1_000_000.0, float(base.get("fixed_position_usdt", 1000.0))))
    base["capital_allocation_pct"] = max(1.0, min(100.0, float(base.get("capital_allocation_pct", 10.0))))
    base["leverage"] = max(1.0, min(50.0, float(base.get("leverage", 2.0))))
    base["fee_bps"] = max(0.0, min(100.0, float(base.get("fee_bps", 4.0))))
    base["slippage_bps"] = max(0.0, min(100.0, float(base.get("slippage_bps", 2.0))))
    base["cooldown_candles"] = max(0, min(100, int(base.get("cooldown_candles", 2))))
    base["max_trades_per_day"] = max(1, min(100, int(base.get("max_trades_per_day", 8))))
    base["max_consecutive_losses"] = max(1, min(50, int(base.get("max_consecutive_losses", 4))))
    base["ema_fast"] = max(3, min(100, int(base.get("ema_fast", 20))))
    base["ema_slow"] = max(5, min(250, int(base.get("ema_slow", 50))))
    base["ema_trend"] = max(20, min(500, int(base.get("ema_trend", 200))))
    base["rsi_period"] = max(4, min(50, int(base.get("rsi_period", 14))))
    base["rsi_oversold"] = max(10.0, min(49.0, float(base.get("rsi_oversold", 32.0))))
    base["rsi_overbought"] = max(51.0, min(90.0, float(base.get("rsi_overbought", 68.0))))
    base["adx_period"] = max(5, min(50, int(base.get("adx_period", 14))))
    base["adx_min"] = max(5.0, min(60.0, float(base.get("adx_min", 20.0))))
    base["atr_period"] = max(5, min(50, int(base.get("atr_period", 14))))
    base["min_atr_pct"] = max(0.0, min(5.0, float(base.get("min_atr_pct", 0.12))))
    base["volume_ma_period"] = max(5, min(100, int(base.get("volume_ma_period", 20))))
    base["min_volume_ratio"] = max(0.0, min(5.0, float(base.get("min_volume_ratio", 0.65))))
    base["min_teddy_score"] = max(20, min(95, int(base.get("min_teddy_score", 58))))
    base["sl_atr_mult"] = max(0.3, min(10.0, float(base.get("sl_atr_mult", 1.5))))
    base["sl_fixed_pct"] = max(0.1, min(25.0, float(base.get("sl_fixed_pct", 1.2))))
    base["min_rr_ratio"] = max(0.5, min(10.0, float(base.get("min_rr_ratio", 1.8))))
    base["tp_atr_mult"] = max(0.5, min(20.0, float(base.get("tp_atr_mult", 2.8))))
    base["tp_fixed_pct"] = max(0.2, min(50.0, float(base.get("tp_fixed_pct", 2.4))))
    base["partial_tp_rr"] = max(0.3, min(10.0, float(base.get("partial_tp_rr", 1.2))))
    base["partial_tp_close_pct"] = max(10.0, min(90.0, float(base.get("partial_tp_close_pct", 50.0))))
    base["breakeven_trigger_rr"] = max(0.3, min(10.0, float(base.get("breakeven_trigger_rr", 1.0))))
    base["trailing_activation_rr"] = max(0.4, min(10.0, float(base.get("trailing_activation_rr", 1.3))))
    base["trailing_distance_atr"] = max(0.3, min(10.0, float(base.get("trailing_distance_atr", 1.1))))
    base["max_bars_in_trade"] = max(4, min(1000, int(base.get("max_bars_in_trade", 48))))
    return base


def _parse_date_to_ms(date_str: Optional[str], default_ms: int) -> int:
    if not date_str:
        return default_ms
    try:
        s = str(date_str).strip()
        if s.isdigit():
            val = int(s)
            return val * 1000 if val < 10_000_000_000 else val
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return default_ms


def validate_and_clean_ohlcv(
    df: pd.DataFrame,
    timeframe: str,
    now_ms: Optional[int] = None,
    cached_candles_count: int = 0,
    fetched_candles_count: int = 0,
    data_source: str = "Binance Historical",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Validates historical OHLCV candles before backtesting:
    1. Checks required columns (Open, High, Low, Close, Volume).
    2. Filters out invalid prices (<= 0) or negative volumes.
    3. Verifies OHLC coherence (High >= max(Open, Close) and Low <= min(Open, Close)).
    4. Sorts chronologically and removes duplicate timestamps.
    5. Excludes any unclosed/incomplete current candle (`close_time_ms > now_ms`).
    6. Detects missing intervals (gaps) and computes an integrity status ('VALID', 'WARNING', 'UNRELIABLE').
    Never fabricates or interpolates missing prices.
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    tf_ms = TIMEFRAME_SECONDS.get(timeframe, 900) * 1000

    raw_count = len(df) if df is not None else 0
    if df is None or df.empty:
        return pd.DataFrame(), {
            "status": "UNRELIABLE",
            "raw_candles": 0,
            "valid_closed_candles": 0,
            "cached_reused_candles": cached_candles_count,
            "newly_fetched_candles": fetched_candles_count,
            "duplicates_removed": 0,
            "unclosed_excluded": 0,
            "invalid_ohlc_removed": 0,
            "missing_intervals_count": 0,
            "gap_ratio_pct": 100.0,
            "gaps_sample": [],
            "data_source": data_source,
            "warnings": ["Aucune bougie historique disponible pour cette sélection."],
        }

    work = df.copy()
    if hasattr(pd, "to_numeric"):
        for col in ("Open", "High", "Low", "Close", "Volume"):
            work[col] = pd.to_numeric(work[col], errors="coerce")
    if hasattr(work, "dropna"):
        try:
            work.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
        except TypeError:
            pass

    # Sort & deduplicate
    before_dedup = len(work)
    if hasattr(work.index, "duplicated"):
        work = work[~work.index.duplicated(keep="last")].sort_index()
    elif hasattr(work, "sort_index"):
        work = work.sort_index()
    duplicates_removed = max(0, before_dedup - len(work))

    # Filter out unclosed candle (if open_time + tf_ms > now_ms)
    unclosed_excluded = 0
    valid_indices = []
    invalid_ohlc_removed = 0

    ts_list = list(work.index)
    for idx_pos, ts in enumerate(ts_list):
        row = work.iloc[idx_pos]
        o = float(row["Open"])
        h = float(row["High"])
        l = float(row["Low"])
        c = float(row["Close"])
        v = float(row["Volume"]) if not pd.isna(row["Volume"]) else 0.0

        # Check timestamp ms
        if hasattr(ts, "timestamp"):
            open_ms = int(ts.timestamp() * 1000)
        else:
            open_ms = _parse_date_to_ms(str(ts), 0)

        if open_ms > 0 and (open_ms + tf_ms) > now_ms:
            unclosed_excluded += 1
            continue

        # OHLC & price validity check
        if o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0:
            invalid_ohlc_removed += 1
            continue
        if h < max(o, c) - 1e-8 or l > min(o, c) + 1e-8 or h < l:
            invalid_ohlc_removed += 1
            continue

        valid_indices.append(idx_pos)

    cleaned = work.iloc[valid_indices].copy() if len(valid_indices) < len(work) else work

    # Detect gaps (missing intervals) without interpolating
    missing_intervals = 0
    gaps_sample: List[Dict[str, Any]] = []
    clean_ts = list(cleaned.index)
    for k in range(1, len(clean_ts)):
        t_prev = clean_ts[k - 1]
        t_cur = clean_ts[k]
        ms_prev = int(t_prev.timestamp() * 1000) if hasattr(t_prev, "timestamp") else _parse_date_to_ms(str(t_prev), 0)
        ms_cur = int(t_cur.timestamp() * 1000) if hasattr(t_cur, "timestamp") else _parse_date_to_ms(str(t_cur), 0)
        diff_ms = ms_cur - ms_prev
        if diff_ms > int(tf_ms * 1.5):
            missed = max(1, int(round(diff_ms / tf_ms)) - 1)
            missing_intervals += missed
            if len(gaps_sample) < 10:
                gaps_sample.append({
                    "from": t_prev.isoformat() if hasattr(t_prev, "isoformat") else str(t_prev),
                    "to": t_cur.isoformat() if hasattr(t_cur, "isoformat") else str(t_cur),
                    "missing_candles": missed,
                })

    total_expected = len(cleaned) + missing_intervals
    gap_ratio_pct = round((missing_intervals / total_expected * 100.0), 2) if total_expected > 0 else 0.0

    warnings: List[str] = []
    if unclosed_excluded > 0:
        warnings.append(f"{unclosed_excluded} chandelier(s) en cours de formation exclu(s) pour éviter le repainting.")
    if duplicates_removed > 0:
        warnings.append(f"{duplicates_removed} doublon(s) horodaté(s) éliminé(s).")
    if invalid_ohlc_removed > 0:
        warnings.append(f"{invalid_ohlc_removed} chandelier(s) incohérent(s) (High < Low ou prix <= 0) écarté(s).")
    if missing_intervals > 0:
        warnings.append(
            f"{missing_intervals} intervalle(s) manquant(s) détecté(s) ({gap_ratio_pct}% de la période). Aucune donnée fictive n'a été interpolée."
        )

    status = "VALID"
    if len(cleaned) < 50 or gap_ratio_pct > 20.0:
        status = "UNRELIABLE"
    elif missing_intervals > 0 or invalid_ohlc_removed > 0:
        status = "WARNING"

    quality_report = {
        "status": status,
        "raw_candles": raw_count,
        "valid_closed_candles": len(cleaned),
        "cached_reused_candles": cached_candles_count,
        "newly_fetched_candles": fetched_candles_count,
        "duplicates_removed": duplicates_removed,
        "unclosed_excluded": unclosed_excluded,
        "invalid_ohlc_removed": invalid_ohlc_removed,
        "missing_intervals_count": missing_intervals,
        "gap_ratio_pct": gap_ratio_pct,
        "gaps_sample": gaps_sample,
        "data_source": data_source,
        "first_candle_utc": clean_ts[0].isoformat() if clean_ts and hasattr(clean_ts[0], "isoformat") else "",
        "last_candle_utc": clean_ts[-1].isoformat() if clean_ts and hasattr(clean_ts[-1], "isoformat") else "",
        "warnings": warnings,
    }
    return cleaned, quality_report


def load_historical_candles(
    symbol: str,
    timeframe: str = "15m",
    market_type: str = "futures",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_candles: int = 1000,
) -> Tuple[pd.DataFrame, str, Dict[str, int]]:
    """
    Loads real historical OHLCV candles for the Strategy Lab with incremental PostgreSQL caching:
    1. Queries `strategy_lab_ohlcv` for already stored candles matching (market_type, symbol, timeframe) in [start_ms, end_ms].
    2. Identifies missing time ranges and fetches ONLY missing candles from official Binance Spot (`/api/v3/klines`)
       or USD-M Futures (`/fapi/v1/klines`) endpoints with pagination and deduplication.
    3. Persists newly fetched closed candles into `strategy_lab_ohlcv` (`ON CONFLICT DO NOTHING`).
    4. Falls back to local CSV archive (`/scratch/btc_15m.csv`) only if network is unreachable in sandbox.
    Returns (DataFrame, data_source_label, stats_dict).
    """
    symbol = _normalize_lab_symbol(symbol or "BTCUSDT")
    binance_query_symbol = "PAXGUSDT" if symbol == "XAUUSD" else symbol
    market_type = "spot" if (str(market_type).lower() == "spot" or symbol == "XAUUSD") else "futures"
    if timeframe not in SUPPORTED_LAB_TIMEFRAMES:
        timeframe = "15m"
    max_candles = max(80, min(2500, int(max_candles or 800)))

    now_ms = int(time.time() * 1000)
    tf_ms = TIMEFRAME_SECONDS.get(timeframe, 900) * 1000
    # Align end_ms to last closed candle boundary
    aligned_now_ms = (now_ms // tf_ms) * tf_ms
    end_ms = min(_parse_date_to_ms(end_date, aligned_now_ms), aligned_now_ms)
    default_start_ms = end_ms - (max_candles * tf_ms)
    start_ms = _parse_date_to_ms(start_date, default_start_ms)
    if start_ms >= end_ms:
        start_ms = end_ms - (300 * tf_ms)

    db = get_db()
    cached_rows = []
    try:
        cached_rows = db.execute(
            """
            SELECT open_time_ms, close_time_ms, open, high, low, close, volume, source
            FROM strategy_lab_ohlcv
            WHERE market_type = %s AND symbol = %s AND timeframe = %s
              AND open_time_ms >= %s AND open_time_ms <= %s
            ORDER BY open_time_ms ASC
            """,
            (market_type, symbol, timeframe, start_ms, end_ms),
        ).fetchall()
    except Exception as e:
        logger.debug("strategy_lab_ohlcv read skipped: %s", e)

    cached_by_open_ms: Dict[int, Dict[str, Any]] = {}
    for r in cached_rows:
        oms = int(r["open_time_ms"])
        cached_by_open_ms[oms] = {
            "open_time_ms": oms,
            "close_time_ms": int(r["close_time_ms"]),
            "Open": float(r["open"]),
            "High": float(r["high"]),
            "Low": float(r["low"]),
            "Close": float(r["close"]),
            "Volume": float(r["volume"]),
            "source": r.get("source") or f"Binance {market_type.capitalize()}",
        }

    cached_count = len(cached_by_open_ms)
    expected_candles = max(1, min(max_candles, int((end_ms - start_ms) // tf_ms)))

    # Determine if we need to fetch missing ranges from Binance
    newly_fetched_count = 0
    source_used = f"PostgreSQL Cache ({market_type.upper()})"

    if cached_count < int(expected_candles * 0.92):
        # Determine missing window [fetch_start_ms, end_ms]
        if cached_by_open_ms:
            max_cached_ms = max(cached_by_open_ms.keys())
            min_cached_ms = min(cached_by_open_ms.keys())
            # If we are missing recent candles after max_cached_ms, fetch only from max_cached_ms + tf_ms
            if min_cached_ms <= start_ms + tf_ms * 2 and max_cached_ms < end_ms - tf_ms:
                fetch_start_ms = max_cached_ms + tf_ms
            else:
                fetch_start_ms = start_ms
        else:
            fetch_start_ms = start_ms

        import requests
        if market_type == "futures" and symbol != "XAUUSD":
            endpoints = [
                ("https://fapi.binance.com/fapi/v1/klines", "Binance USD-M Futures API"),
                ("https://data-api.binance.vision/api/v3/klines", "Binance Vision Archive"),
                ("https://api.binance.com/api/v3/klines", "Binance Spot API (Fallback)"),
            ]
        else:
            endpoints = [
                ("https://data-api.binance.vision/api/v3/klines", "Binance Spot Vision Archive"),
                ("https://api.binance.com/api/v3/klines", "Binance Spot API"),
                ("https://fapi.binance.com/fapi/v1/klines", "Binance USD-M Futures API (Fallback)"),
            ]

        for url, label in endpoints:
            try:
                cursor_ms = fetch_start_ms
                fetched_batches = []
                while cursor_ms < end_ms and sum(len(b) for b in fetched_batches) < max_candles:
                    needed = min(1000, max_candles - sum(len(b) for b in fetched_batches))
                    resp = requests.get(
                        url,
                        params={
                            "symbol": binance_query_symbol,
                            "interval": timeframe,
                            "startTime": cursor_ms,
                            "endTime": end_ms,
                            "limit": needed,
                        },
                        timeout=6,
                    )
                    if resp.status_code == 429:
                        logger.warning("Binance rate limit 429 hit on %s, backing off", url)
                        break
                    if resp.status_code != 200:
                        break
                    batch = resp.json()
                    if not isinstance(batch, list) or not batch:
                        break
                    fetched_batches.append(batch)
                    last_open = int(batch[-1][0])
                    if last_open <= cursor_ms or len(batch) < needed:
                        break
                    cursor_ms = last_open + tf_ms

                flat = [item for sub in fetched_batches for item in sub]
                if flat:
                    source_used = label if cached_count == 0 else f"{label} + Cache PostgreSQL"
                    now_ts = time.time()
                    for k in flat:
                        oms = int(k[0])
                        cms = int(k[6]) if len(k) > 6 else (oms + tf_ms - 1)
                        # Only persist closed candles
                        if cms > now_ms:
                            continue
                        if oms not in cached_by_open_ms:
                            newly_fetched_count += 1
                        cached_by_open_ms[oms] = {
                            "open_time_ms": oms,
                            "close_time_ms": cms,
                            "Open": float(k[1]),
                            "High": float(k[2]),
                            "Low": float(k[3]),
                            "Close": float(k[4]),
                            "Volume": float(k[5]),
                            "source": label,
                        }
                        try:
                            db.execute(
                                """
                                INSERT INTO strategy_lab_ohlcv
                                (market_type, symbol, timeframe, open_time_ms, close_time_ms, open, high, low, close, volume, source, fetched_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (market_type, symbol, timeframe, open_time_ms) DO NOTHING
                                """,
                                (
                                    market_type,
                                    symbol,
                                    timeframe,
                                    oms,
                                    cms,
                                    float(k[1]),
                                    float(k[2]),
                                    float(k[3]),
                                    float(k[4]),
                                    float(k[5]),
                                    label,
                                    now_ts,
                                ),
                            )
                        except Exception:
                            pass
                    break
            except Exception as e:
                logger.debug("Endpoint %s failed: %s", url, e)

    if cached_by_open_ms:
        sorted_oms = sorted(cached_by_open_ms.keys())[-max_candles:]
        rows = []
        for oms in sorted_oms:
            item = cached_by_open_ms[oms]
            ts_iso = datetime.fromtimestamp(oms / 1000.0, tz=timezone.utc).isoformat()
            rows.append(
                {
                    "timestamp": ts_iso,
                    "Open": item["Open"],
                    "High": item["High"],
                    "Low": item["Low"],
                    "Close": item["Close"],
                    "Volume": item["Volume"],
                }
            )
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.set_index("timestamp", inplace=True)
        return df, source_used, {"cached": cached_count, "fetched": newly_fetched_count}

    # Fallback to local CSV archive (/scratch/btc_15m.csv)
    candidate_csvs = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch", "btc_15m.csv"),
        "/scratch/btc_15m.csv",
    ]
    for csv_path in candidate_csvs:
        if os.path.exists(csv_path) and symbol == "BTCUSDT":
            try:
                df = pd.read_csv(csv_path)
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                    df.set_index("timestamp", inplace=True)
                df = df.tail(max_candles).copy()
                for col in ("Open", "High", "Low", "Close", "Volume"):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
                if len(df) >= 50:
                    return df, "Archive Locale Bitsure (btc_15m.csv)", {"cached": len(df), "fetched": 0}
            except Exception as e:
                logger.warning("Fallback CSV read error: %s", e)

    # Final fallback via DataFetcher
    from data_fetcher import DataFetcher
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        fetched_res = loop.run_until_complete(
            DataFetcher.get_instance().get_historical_data(symbol, timeframe=timeframe)
        )
        loop.close()
        df = fetched_res[0] if isinstance(fetched_res, tuple) else fetched_res
        src = fetched_res[1] if isinstance(fetched_res, tuple) and len(fetched_res) > 1 else "DataFetcher Spot"
        if df is not None and not df.empty:
            if getattr(df.index, "tz", None) is None and hasattr(df.index, "tz_localize"):
                df.index = df.index.tz_localize("UTC")
            return df.tail(max_candles), f"{src} ({market_type.upper()})", {"cached": 0, "fetched": len(df)}
    except Exception as e:
        logger.error("DataFetcher fallback failed in Strategy Lab: %s", e)

    raise ValueError(f"Données historiques indisponibles pour {symbol} ({market_type.upper()} • {timeframe}).")


def _compute_lab_indicators(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Computes parameterized technical indicators on the OHLCV DataFrame without look-ahead bias."""
    data = df.copy()

    ema_fast_p = int(params.get("ema_fast", 20))
    ema_slow_p = int(params.get("ema_slow", 50))
    ema_trend_p = int(params.get("ema_trend", 200))
    rsi_p = int(params.get("rsi_period", 14))
    atr_p = int(params.get("atr_period", 14))
    adx_p = int(params.get("adx_period", 14))
    vol_p = int(params.get("volume_ma_period", 20))

    close = data["Close"].astype(float)
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    vol = data["Volume"].astype(float)

    data["LAB_EMA_FAST"] = close.ewm(span=ema_fast_p, adjust=False).mean().fillna(close)
    data["LAB_EMA_SLOW"] = close.ewm(span=ema_slow_p, adjust=False).mean().fillna(close)
    data["LAB_EMA_TREND"] = close.ewm(span=ema_trend_p, adjust=False).mean().fillna(close)

    # MACD, ADX, Bollinger Bands from indicators.py
    macd_line, sig_line, hist_line = macd(close)
    data["MACD_Line"] = macd_line.fillna(0.0)
    data["MACD_Signal"] = sig_line.fillna(0.0)
    data["MACD_Hist"] = hist_line.fillna(0.0)

    adx_s, plus_di, minus_di = adx(high, low, close, period=adx_p)
    data["ADX"] = adx_s.fillna(20.0)

    bb_up, bb_mid, bb_low = bollinger_bands(close, period=20, std=2.0)
    data["BB_Upper"] = bb_up.fillna(close * 1.02)
    data["BB_Lower"] = bb_low.fillna(close * 0.98)

    # Parameterized RSI & ATR via indicators.py
    data["LAB_RSI"] = calc_rsi(close, period=rsi_p).fillna(50.0)
    data["LAB_ATR"] = calc_atr(high, low, close, period=atr_p).fillna(close * 0.005)
    data["LAB_ATR_PCT"] = ((data["LAB_ATR"] / close.replace(0, np.nan)) * 100.0).fillna(0.2)

    # Volume Ratio
    vol_ma = vol.rolling(window=vol_p, min_periods=1).mean().replace(0, np.nan)
    data["LAB_VOL_RATIO"] = (vol / vol_ma).fillna(1.0)

    return data


def _evaluate_candle_signal(row: pd.Series, prev_row: pd.Series, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates the Bitsure Teddy confluence score and filter pipeline on a single closed candle.
    Returns direction ('BUY'|'SELL'|'WAIT'), teddy_score (0..100), components, and rejection_reason if filtered.
    """
    close = float(row["Close"])
    ema_fast = float(row["LAB_EMA_FAST"])
    ema_slow = float(row["LAB_EMA_SLOW"])
    ema_trend = float(row["LAB_EMA_TREND"])
    rsi = float(row["LAB_RSI"])
    prev_rsi = float(prev_row["LAB_RSI"])
    adx_val = float(row.get("ADX", 20.0) if not pd.isna(row.get("ADX")) else 20.0)
    macd_hist = float(row.get("MACD_Hist", 0.0) if not pd.isna(row.get("MACD_Hist")) else 0.0)
    prev_macd_hist = float(prev_row.get("MACD_Hist", 0.0) if not pd.isna(prev_row.get("MACD_Hist")) else 0.0)
    atr_val = float(row["LAB_ATR"])
    atr_pct = float(row["LAB_ATR_PCT"])
    vol_ratio = float(row["LAB_VOL_RATIO"])
    bb_lower = float(row.get("BB_Lower", close * 0.98) if not pd.isna(row.get("BB_Lower")) else close * 0.98)
    bb_upper = float(row.get("BB_Upper", close * 1.02) if not pd.isna(row.get("BB_Upper")) else close * 1.02)

    bull_points = 0.0
    bear_points = 0.0
    reasons_bull: List[str] = []
    reasons_bear: List[str] = []

    # 1. Trend Alignment (up to 30 pts)
    if close > ema_fast > ema_slow:
        bull_points += 22.0
        reasons_bull.append("Alignement haussier EMA rapide > EMA lente")
    elif close > ema_fast:
        bull_points += 12.0
    if close < ema_fast < ema_slow:
        bear_points += 22.0
        reasons_bear.append("Alignement baissier EMA rapide < EMA lente")
    elif close < ema_fast:
        bear_points += 12.0

    if close > ema_trend:
        bull_points += 8.0
    else:
        bear_points += 8.0

    # 2. RSI Momentum & Rebound (up to 25 pts)
    rsi_os = float(params["rsi_oversold"])
    rsi_ob = float(params["rsi_overbought"])
    if rsi <= rsi_os or (prev_rsi <= rsi_os and rsi > prev_rsi):
        bull_points += 24.0
        reasons_bull.append(f"Rebond survente RSI ({rsi:.1f})")
    elif 45.0 <= rsi < rsi_ob and rsi > prev_rsi:
        bull_points += 15.0
        reasons_bull.append(f"Momentum RSI haussier ({rsi:.1f})")

    if rsi >= rsi_ob or (prev_rsi >= rsi_ob and rsi < prev_rsi):
        bear_points += 24.0
        reasons_bear.append(f"Rejet surachat RSI ({rsi:.1f})")
    elif rsi_os < rsi <= 55.0 and rsi < prev_rsi:
        bear_points += 15.0
        reasons_bear.append(f"Momentum RSI baissier ({rsi:.1f})")

    # 3. MACD Histogram Impulse (up to 20 pts)
    if macd_hist > 0 and macd_hist >= prev_macd_hist:
        bull_points += 18.0
        reasons_bull.append("Impulsion MACD positive croissante")
    elif macd_hist > prev_macd_hist:
        bull_points += 10.0

    if macd_hist < 0 and macd_hist <= prev_macd_hist:
        bear_points += 18.0
        reasons_bear.append("Impulsion MACD négative")
    elif macd_hist < prev_macd_hist:
        bear_points += 10.0

    # 4. ADX Trend Strength + Bollinger Position + Volume (up to 25 pts)
    if adx_val >= float(params["adx_min"]):
        if bull_points >= bear_points:
            bull_points += 12.0
        else:
            bear_points += 12.0
    if close <= bb_lower * 1.004:
        bull_points += 8.0
        reasons_bull.append("Test bande basse Bollinger")
    elif close >= bb_upper * 0.996:
        bear_points += 8.0
        reasons_bear.append("Test bande haute Bollinger")

    if vol_ratio >= 1.15:
        if bull_points >= bear_points:
            bull_points += 7.0
            reasons_bull.append(f"Volume soutenu ({vol_ratio:.2f}x)")
        else:
            bear_points += 7.0
            reasons_bear.append(f"Volume baissier soutenu ({vol_ratio:.2f}x)")

    raw_direction = "BUY" if bull_points >= bear_points else "SELL"
    raw_score = int(round(min(100.0, max(bull_points, bear_points))))
    primary_reasons = reasons_bull if raw_direction == "BUY" else reasons_bear

    # Filter Pipeline
    min_score = int(params["min_teddy_score"])
    if raw_score < min_score:
        return {
            "signal": "WAIT",
            "candidate_direction": raw_direction,
            "teddy_score": raw_score,
            "rejected_by": "score_too_low",
            "rejection_reason": f"Teddy Score ({raw_score}/100) inférieur au seuil ({min_score})",
            "reasons": primary_reasons,
        }

    if raw_direction == "BUY" and not bool(params.get("allow_long", True)):
        return {
            "signal": "WAIT",
            "candidate_direction": raw_direction,
            "teddy_score": raw_score,
            "rejected_by": "direction_disabled",
            "rejection_reason": "Positions LONG désactivées dans le scénario",
            "reasons": primary_reasons,
        }
    if raw_direction == "SELL" and not bool(params.get("allow_short", True)):
        return {
            "signal": "WAIT",
            "candidate_direction": raw_direction,
            "teddy_score": raw_score,
            "rejected_by": "direction_disabled",
            "rejection_reason": "Positions SHORT désactivées dans le scénario",
            "reasons": primary_reasons,
        }

    if atr_pct < float(params["min_atr_pct"]):
        return {
            "signal": "WAIT",
            "candidate_direction": raw_direction,
            "teddy_score": raw_score,
            "rejected_by": "low_volatility_atr",
            "rejection_reason": f"Volatilité ATR trop faible ({atr_pct:.2f}% < {params['min_atr_pct']}%)",
            "reasons": primary_reasons,
        }

    if adx_val < float(params["adx_min"]):
        return {
            "signal": "WAIT",
            "candidate_direction": raw_direction,
            "teddy_score": raw_score,
            "rejected_by": "weak_adx_regime",
            "rejection_reason": f"Marché sans tendance claire (ADX {adx_val:.1f} < {params['adx_min']})",
            "reasons": primary_reasons,
        }

    if vol_ratio < float(params["min_volume_ratio"]):
        return {
            "signal": "WAIT",
            "candidate_direction": raw_direction,
            "teddy_score": raw_score,
            "rejected_by": "low_volume",
            "rejection_reason": f"Volume relatif insuffisant ({vol_ratio:.2f}x < {params['min_volume_ratio']}x)",
            "reasons": primary_reasons,
        }

    if bool(params.get("require_ema_alignment", True)):
        if raw_direction == "BUY" and not (close >= ema_fast and ema_fast >= ema_slow * 0.998):
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "ema_misaligned",
                "rejection_reason": "EMA rapide et EMA lente non alignées à la hausse",
                "reasons": primary_reasons,
            }
        if raw_direction == "SELL" and not (close <= ema_fast and ema_fast <= ema_slow * 1.002):
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "ema_misaligned",
                "rejection_reason": "EMA rapide et EMA lente non alignées à la baisse",
                "reasons": primary_reasons,
            }

    if bool(params.get("require_macd_confirmation", True)):
        if raw_direction == "BUY" and macd_hist < 0 and macd_hist < prev_macd_hist:
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "macd_divergence",
                "rejection_reason": "Histogramme MACD opposé au signal d'achat",
                "reasons": primary_reasons,
            }
        if raw_direction == "SELL" and macd_hist > 0 and macd_hist > prev_macd_hist:
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "macd_divergence",
                "rejection_reason": "Histogramme MACD opposé au signal de vente",
                "reasons": primary_reasons,
            }

    if bool(params.get("require_trend_filter_ema200", False)):
        if raw_direction == "BUY" and close < ema_trend:
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "against_ema200_trend",
                "rejection_reason": f"Prix sous l'EMA de tendance ({params['ema_trend']})",
                "reasons": primary_reasons,
            }
        if raw_direction == "SELL" and close > ema_trend:
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "against_ema200_trend",
                "rejection_reason": f"Prix au-dessus de l'EMA de tendance ({params['ema_trend']})",
                "reasons": primary_reasons,
            }

    if bool(params.get("block_against_strong_trend", True)) and adx_val >= 30.0:
        if raw_direction == "BUY" and close < ema_slow and ema_fast < ema_slow:
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "counter_strong_trend",
                "rejection_reason": f"Signal BUY contre une tendance baissière forte (ADX {adx_val:.1f})",
                "reasons": primary_reasons,
            }
        if raw_direction == "SELL" and close > ema_slow and ema_fast > ema_slow:
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "counter_strong_trend",
                "rejection_reason": f"Signal SELL contre une tendance haussière forte (ADX {adx_val:.1f})",
                "reasons": primary_reasons,
            }

    # Compute SL & TP distances
    if params.get("sl_mode") == "fixed_pct":
        sl_dist = close * (float(params["sl_fixed_pct"]) / 100.0)
    else:
        sl_dist = max(atr_val * float(params["sl_atr_mult"]), close * 0.0025)

    tp_mode = params.get("tp_mode", "rr")
    if tp_mode == "fixed_pct":
        tp_dist = close * (float(params["tp_fixed_pct"]) / 100.0)
    elif tp_mode == "atr":
        tp_dist = max(atr_val * float(params["tp_atr_mult"]), sl_dist * 1.1)
    else:
        tp_dist = sl_dist * float(params["min_rr_ratio"])

    rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0
    if rr_ratio < float(params["min_rr_ratio"]) - 0.05:
        return {
            "signal": "WAIT",
            "candidate_direction": raw_direction,
            "teddy_score": raw_score,
            "rejected_by": "insufficient_rr",
            "rejection_reason": f"Ratio Risque/Rendement ({rr_ratio:.2f}) inférieur au minimum ({params['min_rr_ratio']})",
            "reasons": primary_reasons,
        }

    sl_price = close - sl_dist if raw_direction == "BUY" else close + sl_dist
    tp_price = close + tp_dist if raw_direction == "BUY" else close - tp_dist

    return {
        "signal": raw_direction,
        "candidate_direction": raw_direction,
        "teddy_score": raw_score,
        "rejected_by": None,
        "rejection_reason": None,
        "reasons": primary_reasons or [f"Confluence Teddy Score {raw_score}/100 ({raw_direction})"],
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_dist": sl_dist,
        "tp_dist": tp_dist,
        "rr_ratio": rr_ratio,
    }


def run_backtest_experiment(
    symbol: str,
    timeframe: str = "15m",
    trading_style: str = "day",
    market_type: str = "futures",
    period_split: str = "full",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    raw_params: Optional[Dict[str, Any]] = None,
    max_candles: int = 1000,
    allow_unreliable_data: bool = False,
    preloaded_df: Optional[Tuple[pd.DataFrame, str]] = None,
) -> Dict[str, Any]:
    """
    Runs a complete, deterministic candle-by-candle backtest simulation with zero look-ahead bias.
    Tracks real execution steps, data quality validation, conservative intra-candle SL/TP conflict resolution,
    and supports Dev / Validation / Test sample splitting to prevent overfitting.
    """
    t0 = time.time()
    execution_steps: List[Dict[str, Any]] = []

    def add_step(step_num: int, label: str, detail: str, status: str = "done") -> None:
        execution_steps.append({
            "step": step_num,
            "label": label,
            "detail": detail,
            "status": status,
            "elapsed_ms": int((time.time() - t0) * 1000),
        })

    # Step 1: Configuration verification
    symbol = _normalize_lab_symbol(symbol or "BTCUSDT")
    market_type = "spot" if str(market_type).lower() == "spot" else "futures"
    params = normalize_lab_params(raw_params, style=trading_style)
    if market_type == "spot":
        # Spot market cannot use leverage > 1
        params["leverage"] = 1.0
    add_step(
        1,
        "Vérification de la configuration",
        f"Actif {symbol} ({market_type.upper()} • {timeframe}) | Style {trading_style.upper()} | Score>={params['min_teddy_score']}",
    )

    # Step 2 & 3: Search local storage & fetch missing candles
    if preloaded_df is not None:
        raw_df, data_source = preloaded_df
        cache_stats = {"cached": len(raw_df), "fetched": 0}
        add_step(2, "Recherche des données locales", f"{len(raw_df)} chandeliers préchargés en mémoire.")
        add_step(3, "Récupération des données manquantes", "Aucun téléchargement externe requis (0 chandelier manquant).")
    else:
        raw_df, data_source, cache_stats = load_historical_candles(
            symbol=symbol,
            timeframe=timeframe,
            market_type=market_type,
            start_date=start_date,
            end_date=end_date,
            max_candles=max_candles,
        )
        add_step(
            2,
            "Recherche des données déjà disponibles",
            f"{cache_stats.get('cached', 0)} chandeliers trouvés dans le stockage PostgreSQL local.",
        )
        add_step(
            3,
            "Récupération des données manquantes",
            f"{cache_stats.get('fetched', 0)} nouveaux chandeliers téléchargés depuis {data_source}.",
        )

    # Step 4: Validate candles & data quality
    cleaned_df, data_quality = validate_and_clean_ohlcv(
        raw_df,
        timeframe=timeframe,
        cached_candles_count=cache_stats.get("cached", 0),
        fetched_candles_count=cache_stats.get("fetched", 0),
        data_source=data_source,
    )
    add_step(
        4,
        "Validation des chandeliers OHLCV",
        f"{data_quality['valid_closed_candles']} chandeliers clôturés validés (statut : {data_quality['status']}, lacunes : {data_quality['missing_intervals_count']}).",
        status="warning" if data_quality["status"] != "VALID" else "done",
    )

    if data_quality["status"] == "UNRELIABLE" and not allow_unreliable_data and preloaded_df is None:
        raise ValueError(
            f"Qualité des données insuffisante ({data_quality['valid_closed_candles']} bougies, {data_quality['gap_ratio_pct']}% de lacunes). "
            "Cochez « Forcer malgré les lacunes » si vous souhaitez tout de même exécuter ce test."
        )

    # Step 5: Anti-overfitting sample split (Full / Dev 60% / Validation 20% / Test 20%)
    total_n = len(cleaned_df)
    period_split = (period_split or "full").lower()
    if period_split == "dev" and total_n >= 100:
        df_slice = cleaned_df.iloc[: int(total_n * 0.60)].copy()
        split_label = "Développement In-Sample (60%)"
    elif period_split == "validation" and total_n >= 100:
        df_slice = cleaned_df.iloc[int(total_n * 0.60) : int(total_n * 0.80)].copy()
        split_label = "Validation Out-of-Sample (20%)"
    elif period_split == "test" and total_n >= 100:
        df_slice = cleaned_df.iloc[int(total_n * 0.80) :].copy()
        split_label = "Test Final Out-of-Sample (20%)"
    else:
        df_slice = cleaned_df
        period_split = "full"
        split_label = "Période Complète (100%)"

    add_step(
        5,
        "Préparation de l'échantillon",
        f"Segment sélectionné : {split_label} ({len(df_slice)} chandeliers).",
    )

    # Step 6: Indicator calculation
    df = _compute_lab_indicators(df_slice, params)
    warmup = max(25, min(80, int(params["ema_slow"]) + 2))
    if len(df) <= warmup + 10:
        warmup = max(10, len(df) // 5)
    add_step(
        6,
        "Calcul des indicateurs techniques",
        f"EMA({params['ema_fast']}/{params['ema_slow']}/{params['ema_trend']}), RSI({params['rsi_period']}), ADX({params['adx_period']}), ATR({params['atr_period']}), MACD, Bollinger calculés sans biais.",
    )

    # Step 7: Chronological Trade Simulation
    initial_capital = float(params["initial_capital"])
    balance = initial_capital
    peak_equity = initial_capital
    fee_rate = float(params["fee_bps"]) / 10000.0
    slippage_rate = float(params["slippage_bps"]) / 10000.0
    leverage = float(params["leverage"])

    open_pos: Optional[Dict[str, Any]] = None
    closed_trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    chart_candles: List[Dict[str, Any]] = []

    rejection_counts: Dict[str, int] = {
        "score_too_low": 0,
        "low_volatility_atr": 0,
        "weak_adx_regime": 0,
        "low_volume": 0,
        "ema_misaligned": 0,
        "macd_divergence": 0,
        "against_ema200_trend": 0,
        "counter_strong_trend": 0,
        "insufficient_rr": 0,
        "cooldown_or_limits": 0,
        "direction_disabled": 0,
    }
    rejected_signals_sample: List[Dict[str, Any]] = []
    valid_signals_count = 0
    ambiguous_sl_tp_candles = 0

    cooldown_until_idx = -1
    consecutive_losses = 0
    current_day_str = ""
    trades_today = 0

    timestamps = list(df.index)
    for i in range(warmup, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        ts = timestamps[i]
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        day_str = ts_iso[:10]
        if day_str != current_day_str:
            current_day_str = day_str
            trades_today = 0

        high = float(row["High"])
        low = float(row["Low"])
        close = float(row["Close"])
        open_p = float(row["Open"])
        atr_val = float(row["LAB_ATR"])

        candle_marker: Optional[Dict[str, Any]] = None

        # 1. Manage Open Position on Current Candle
        if open_pos is not None:
            open_pos["bars_held"] += 1
            side = open_pos["side"]
            entry_p = open_pos["entry_price"]
            init_sl_dist = open_pos["initial_sl_dist"]

            if side == "BUY":
                fav_pct = ((high - entry_p) / entry_p) * 100.0
                adv_pct = ((low - entry_p) / entry_p) * 100.0
                current_r = (high - entry_p) / init_sl_dist if init_sl_dist > 0 else 0.0
            else:
                fav_pct = ((entry_p - low) / entry_p) * 100.0
                adv_pct = ((entry_p - high) / entry_p) * 100.0
                current_r = (entry_p - low) / init_sl_dist if init_sl_dist > 0 else 0.0

            open_pos["mfe_pct"] = max(open_pos["mfe_pct"], fav_pct)
            open_pos["mae_pct"] = min(open_pos["mae_pct"], adv_pct)

            # CONSERVATIVE INTRA-CANDLE RULE:
            # Check Stop Loss & Take Profit BEFORE assuming favorable intra-candle trailing/partial TP
            # If both SL and TP are touched within the exact same candle, apply the documented conservative rule:
            # Stop Loss is assumed hit first (worst-case execution) so backtest never overstates returns.
            exit_reason = None
            raw_exit_price = None

            if side == "BUY":
                sl_hit = low <= open_pos["sl_price"]
                tp_hit = high >= open_pos["tp_price"]
            else:
                sl_hit = high >= open_pos["sl_price"]
                tp_hit = low <= open_pos["tp_price"]

            if sl_hit and tp_hit:
                ambiguous_sl_tp_candles += 1
                raw_exit_price = open_pos["sl_price"]
                exit_reason = "STOP_LOSS_AMBIGUOUS_BAR"
            elif sl_hit:
                raw_exit_price = open_pos["sl_price"]
                exit_reason = (
                    "TRAILING_SL"
                    if open_pos["trailing_activated"]
                    else ("BREAKEVEN_SL" if open_pos["be_activated"] else "STOP_LOSS")
                )
            elif tp_hit:
                raw_exit_price = open_pos["tp_price"]
                exit_reason = "TAKE_PROFIT"

            # If position survived this candle's extremes, apply Partial TP, Break-Even & Trailing for subsequent candles
            if exit_reason is None:
                if (
                    bool(params.get("partial_tp_enabled", True))
                    and not open_pos["partial_taken"]
                    and current_r >= float(params.get("partial_tp_rr", 1.2))
                ):
                    partial_pct = float(params.get("partial_tp_close_pct", 50.0)) / 100.0
                    partial_price = (
                        entry_p + init_sl_dist * float(params.get("partial_tp_rr", 1.2))
                        if side == "BUY"
                        else entry_p - init_sl_dist * float(params.get("partial_tp_rr", 1.2))
                    )
                    qty_closed = open_pos["qty_remaining"] * partial_pct
                    raw_partial_pnl = (
                        (partial_price - entry_p) * qty_closed
                        if side == "BUY"
                        else (entry_p - partial_price) * qty_closed
                    )
                    partial_fee = partial_price * qty_closed * fee_rate
                    open_pos["realized_partial_pnl"] += raw_partial_pnl - partial_fee
                    open_pos["fees_paid"] += partial_fee
                    open_pos["qty_remaining"] -= qty_closed
                    open_pos["partial_taken"] = True
                    balance += raw_partial_pnl - partial_fee

                if (
                    bool(params.get("breakeven_enabled", True))
                    and not open_pos["be_activated"]
                    and current_r >= float(params.get("breakeven_trigger_rr", 1.0))
                ):
                    be_buffer = entry_p * (fee_rate * 2.2)
                    if side == "BUY":
                        open_pos["sl_price"] = max(open_pos["sl_price"], entry_p + be_buffer)
                    else:
                        open_pos["sl_price"] = min(open_pos["sl_price"], entry_p - be_buffer)
                    open_pos["be_activated"] = True

                if (
                    bool(params.get("trailing_stop_enabled", True))
                    and current_r >= float(params.get("trailing_activation_rr", 1.3))
                ):
                    trail_dist = max(atr_val * float(params.get("trailing_distance_atr", 1.1)), entry_p * 0.002)
                    if side == "BUY":
                        new_sl = close - trail_dist
                        if new_sl > open_pos["sl_price"]:
                            open_pos["sl_price"] = new_sl
                            open_pos["trailing_activated"] = True
                    else:
                        new_sl = close + trail_dist
                        if new_sl < open_pos["sl_price"]:
                            open_pos["sl_price"] = new_sl
                            open_pos["trailing_activated"] = True

            if exit_reason is None and open_pos["bars_held"] >= int(params.get("max_bars_in_trade", 48)):
                raw_exit_price = close
                exit_reason = "TIME_STOP"

            sig_eval = _evaluate_candle_signal(row, prev_row, params)
            if (
                exit_reason is None
                and bool(params.get("exit_on_opposite_signal", True))
                and sig_eval["signal"] in ("BUY", "SELL")
                and sig_eval["signal"] != side
            ):
                raw_exit_price = close
                exit_reason = "OPPOSITE_SIGNAL"

            if exit_reason is not None and raw_exit_price is not None:
                exec_exit = (
                    raw_exit_price * (1.0 - slippage_rate)
                    if side == "BUY"
                    else raw_exit_price * (1.0 + slippage_rate)
                )
                qty_rem = open_pos["qty_remaining"]
                rem_pnl = (exec_exit - entry_p) * qty_rem if side == "BUY" else (entry_p - exec_exit) * qty_rem
                exit_fee = exec_exit * qty_rem * fee_rate
                net_rem_pnl = rem_pnl - exit_fee
                balance += net_rem_pnl

                total_net_pnl = open_pos["realized_partial_pnl"] + net_rem_pnl - open_pos["entry_fee"]
                total_fees = open_pos["fees_paid"] + exit_fee
                notional = open_pos["initial_qty"] * entry_p
                pnl_pct = (total_net_pnl / open_pos["margin_used"] * 100.0) if open_pos["margin_used"] > 0 else 0.0
                r_multiple = (
                    total_net_pnl / open_pos["initial_risk_usdt"]
                    if open_pos["initial_risk_usdt"] > 0
                    else 0.0
                )

                trade_record = {
                    "id": len(closed_trades) + 1,
                    "symbol": symbol,
                    "side": side,
                    "entry_time": open_pos["entry_time"],
                    "exit_time": ts_iso,
                    "entry_index": open_pos["entry_index"],
                    "exit_index": i,
                    "bars_held": open_pos["bars_held"],
                    "entry_price": round(entry_p, 4),
                    "exit_price": round(exec_exit, 4),
                    "sl_initial": round(open_pos["initial_sl"], 4),
                    "tp_initial": round(open_pos["tp_price"], 4),
                    "qty": round(open_pos["initial_qty"], 6),
                    "notional_usdt": round(notional, 2),
                    "margin_used": round(open_pos["margin_used"], 2),
                    "pnl_usdt": round(total_net_pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "r_multiple": round(r_multiple, 2),
                    "fees_usdt": round(total_fees, 2),
                    "mfe_pct": round(open_pos["mfe_pct"], 2),
                    "mae_pct": round(open_pos["mae_pct"], 2),
                    "teddy_score": open_pos["teddy_score"],
                    "entry_reasons": open_pos["entry_reasons"],
                    "exit_reason": exit_reason,
                    "partial_taken": open_pos["partial_taken"],
                }
                closed_trades.append(trade_record)
                candle_marker = {
                    "type": "EXIT",
                    "trade_id": trade_record["id"],
                    "side": side,
                    "price": round(exec_exit, 4),
                    "entry_price": trade_record["entry_price"],
                    "exit_price": trade_record["exit_price"],
                    "sl": trade_record["sl_initial"],
                    "tp": trade_record["tp_initial"],
                    "score": trade_record["teddy_score"],
                    "pnl_usdt": round(total_net_pnl, 2),
                    "pnl_pct": trade_record["pnl_pct"],
                    "r_multiple": trade_record["r_multiple"],
                    "bars_held": trade_record["bars_held"],
                    "exit_reason": exit_reason,
                    "reason": open_pos["entry_reasons"][0] if open_pos["entry_reasons"] else "Signal validé",
                }
                # Backfill the corresponding ENTRY marker in chart_candles with final trade outcome
                for prev_c in reversed(chart_candles):
                    m_prev = prev_c.get("marker")
                    if m_prev and m_prev.get("type") == "ENTRY" and m_prev.get("trade_id") == trade_record["id"]:
                        m_prev["exit_price"] = trade_record["exit_price"]
                        m_prev["pnl_usdt"] = trade_record["pnl_usdt"]
                        m_prev["pnl_pct"] = trade_record["pnl_pct"]
                        m_prev["r_multiple"] = trade_record["r_multiple"]
                        m_prev["bars_held"] = trade_record["bars_held"]
                        m_prev["exit_reason"] = trade_record["exit_reason"]
                        break

                if total_net_pnl < 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0

                cooldown_until_idx = i + int(params.get("cooldown_candles", 2))
                open_pos = None

        # 2. Evaluate Entry Signal When Flat
        if open_pos is None:
            sig_eval = _evaluate_candle_signal(row, prev_row, params)
            if sig_eval["signal"] in ("BUY", "SELL"):
                valid_signals_count += 1
                if i < cooldown_until_idx:
                    rejection_counts["cooldown_or_limits"] += 1
                elif trades_today >= int(params.get("max_trades_per_day", 8)):
                    rejection_counts["cooldown_or_limits"] += 1
                elif consecutive_losses >= int(params.get("max_consecutive_losses", 4)):
                    rejection_counts["cooldown_or_limits"] += 1
                    consecutive_losses = max(0, consecutive_losses - 1)
                else:
                    side = sig_eval["signal"]
                    exec_entry = close * (1.0 + slippage_rate) if side == "BUY" else close * (1.0 - slippage_rate)
                    sl_dist = float(sig_eval["sl_dist"])
                    tp_dist = float(sig_eval["tp_dist"])
                    sl_price = exec_entry - sl_dist if side == "BUY" else exec_entry + sl_dist
                    tp_price = exec_entry + tp_dist if side == "BUY" else exec_entry - tp_dist

                    sizing_mode = params.get("position_sizing_mode", "risk_pct")
                    if sizing_mode == "fixed_usdt":
                        notional_usdt = min(float(params["fixed_position_usdt"]) * leverage, balance * leverage * 0.95)
                        qty = notional_usdt / exec_entry if exec_entry > 0 else 0.0
                        risk_usdt = qty * sl_dist
                    elif sizing_mode == "capital_pct":
                        alloc_usdt = balance * (float(params["capital_allocation_pct"]) / 100.0)
                        notional_usdt = alloc_usdt * leverage
                        qty = notional_usdt / exec_entry if exec_entry > 0 else 0.0
                        risk_usdt = qty * sl_dist
                    else:
                        risk_usdt = balance * (float(params["risk_per_trade_pct"]) / 100.0)
                        qty = risk_usdt / sl_dist if sl_dist > 0 else 0.0
                        notional_usdt = qty * exec_entry
                        max_notional = balance * leverage * 0.95
                        if notional_usdt > max_notional and exec_entry > 0:
                            notional_usdt = max_notional
                            qty = notional_usdt / exec_entry
                            risk_usdt = qty * sl_dist

                    if qty > 0 and balance > 20.0:
                        entry_fee = notional_usdt * fee_rate
                        balance -= entry_fee
                        margin_used = notional_usdt / leverage if leverage > 0 else notional_usdt
                        open_pos = {
                            "side": side,
                            "entry_time": ts_iso,
                            "entry_index": i,
                            "entry_price": exec_entry,
                            "initial_sl": sl_price,
                            "sl_price": sl_price,
                            "tp_price": tp_price,
                            "initial_sl_dist": sl_dist,
                            "initial_qty": qty,
                            "qty_remaining": qty,
                            "margin_used": margin_used,
                            "initial_risk_usdt": max(risk_usdt, 1.0),
                            "entry_fee": entry_fee,
                            "fees_paid": entry_fee,
                            "realized_partial_pnl": 0.0,
                            "partial_taken": False,
                            "be_activated": False,
                            "trailing_activated": False,
                            "bars_held": 0,
                            "mfe_pct": 0.0,
                            "mae_pct": 0.0,
                            "teddy_score": sig_eval["teddy_score"],
                            "entry_reasons": sig_eval["reasons"],
                        }
                        trades_today += 1
                        candle_marker = {
                            "type": "ENTRY",
                            "trade_id": len(closed_trades) + 1,
                            "side": side,
                            "price": round(exec_entry, 4),
                            "entry_price": round(exec_entry, 4),
                            "sl": round(sl_price, 4),
                            "tp": round(tp_price, 4),
                            "score": sig_eval["teddy_score"],
                            "reason": sig_eval["reasons"][0] if sig_eval["reasons"] else "Signal validé",
                        }
            else:
                rej_key = sig_eval.get("rejected_by")
                if rej_key in rejection_counts:
                    rejection_counts[rej_key] += 1
                if sig_eval.get("teddy_score", 0) >= max(45, int(params["min_teddy_score"]) - 12):
                    if len(rejected_signals_sample) < 40:
                        rejected_signals_sample.append(
                            {
                                "timestamp": ts_iso,
                                "price": round(close, 4),
                                "candidate": sig_eval.get("candidate_direction", "WAIT"),
                                "score": sig_eval.get("teddy_score", 0),
                                "rejected_by": rej_key,
                                "reason": sig_eval.get("rejection_reason", ""),
                            }
                        )

        # 3. Mark-to-Market Equity & Drawdown
        unrealized = 0.0
        if open_pos is not None:
            if open_pos["side"] == "BUY":
                unrealized = (close - open_pos["entry_price"]) * open_pos["qty_remaining"]
            else:
                unrealized = (open_pos["entry_price"] - close) * open_pos["qty_remaining"]

        current_equity = max(0.0, balance + unrealized)
        if current_equity > peak_equity:
            peak_equity = current_equity
        dd_pct = ((peak_equity - current_equity) / peak_equity * 100.0) if peak_equity > 0 else 0.0
        dd_usdt = peak_equity - current_equity

        equity_curve.append(
            {
                "timestamp": ts_iso,
                "equity": round(current_equity, 2),
                "balance": round(balance, 2),
                "drawdown_pct": round(-dd_pct, 2),
                "drawdown_usdt": round(dd_usdt, 2),
                "price": round(close, 4),
            }
        )

        chart_candles.append(
            {
                "index": i,
                "timestamp": ts_iso,
                "open": round(open_p, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": round(float(row["Volume"]), 2),
                "ema_fast": round(float(row["LAB_EMA_FAST"]), 4),
                "ema_slow": round(float(row["LAB_EMA_SLOW"]), 4),
                "ema_trend": round(float(row["LAB_EMA_TREND"]), 4),
                "bb_upper": round(float(row.get("BB_Upper", close)), 4) if not pd.isna(row.get("BB_Upper")) else None,
                "bb_lower": round(float(row.get("BB_Lower", close)), 4) if not pd.isna(row.get("BB_Lower")) else None,
                "rsi": round(float(row["LAB_RSI"]), 1),
                "adx": round(float(row.get("ADX", 20.0)), 1) if not pd.isna(row.get("ADX")) else 20.0,
                "marker": candle_marker,
            }
        )

    add_step(
        7,
        "Simulation chronologique des transactions",
        f"{len(df) - warmup} chandeliers simulés → {len(closed_trades)} transactions exécutées ({ambiguous_sl_tp_candles} conflit(s) SL/TP résolu(s) prudemment).",
    )

    # Step 8: Compute Comprehensive Institutional Metrics
    metrics = _compute_backtest_metrics(
        initial_capital=initial_capital,
        final_equity=equity_curve[-1]["equity"] if equity_curve else initial_capital,
        closed_trades=closed_trades,
        equity_curve=equity_curve,
        timeframe=timeframe,
    )
    add_step(
        8,
        "Calcul des métriques de performance",
        f"Rendement {metrics['total_return_pct']:+.2f}% | Win Rate {metrics['win_rate_pct']:.1f}% | Profit Factor {metrics['profit_factor']} | Max DD -{metrics['max_drawdown_pct']:.2f}%.",
    )

    diagnostics = _build_strategy_diagnostics(metrics, closed_trades, rejection_counts, params, data_quality)
    elapsed_ms = int((time.time() - t0) * 1000)

    sampled_candles = _downsample_candles_preserving_markers(chart_candles, max_points=450)
    sampled_equity = _downsample_list(equity_curve, max_points=450)

    first_ts = timestamps[warmup] if len(timestamps) > warmup else (timestamps[0] if timestamps else "")
    last_ts = timestamps[-1] if timestamps else ""

    return {
        "market_type": market_type,
        "symbol": symbol,
        "timeframe": timeframe,
        "trading_style": trading_style,
        "period_split": period_split,
        "split_label": split_label,
        "engine_version": ENGINE_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "status": "COMPLETED",
        "data_source": data_source,
        "start_date": first_ts.isoformat() if hasattr(first_ts, "isoformat") else str(first_ts),
        "end_date": last_ts.isoformat() if hasattr(last_ts, "isoformat") else str(last_ts),
        "candles_count": len(df) - warmup,
        "execution_ms": elapsed_ms,
        "data_quality": data_quality,
        "execution_steps": execution_steps,
        "params": params,
        "metrics": metrics,
        "diagnostics": diagnostics,
        "signals_summary": {
            "total_candles_evaluated": len(df) - warmup,
            "valid_signals": valid_signals_count,
            "executed_trades": len(closed_trades),
            "ambiguous_sl_tp_candles": ambiguous_sl_tp_candles,
            "rejection_counts": rejection_counts,
            "rejected_sample": rejected_signals_sample[:25],
        },
        "trades": closed_trades,
        "equity_curve": sampled_equity,
        "candles": sampled_candles,
    }


def _downsample_list(items: List[Dict[str, Any]], max_points: int = 450) -> List[Dict[str, Any]]:
    if len(items) <= max_points:
        return items
    step = max(1, len(items) // max_points)
    res = [items[idx] for idx in range(0, len(items), step)]
    if res[-1] != items[-1]:
        res.append(items[-1])
    return res


def _downsample_candles_preserving_markers(candles: List[Dict[str, Any]], max_points: int = 450) -> List[Dict[str, Any]]:
    if len(candles) <= max_points:
        return candles
    step = max(1, len(candles) // max_points)
    selected = []
    for idx, c in enumerate(candles):
        if idx % step == 0 or c.get("marker") is not None or idx == len(candles) - 1:
            selected.append(c)
    return selected


def _compute_backtest_metrics(
    initial_capital: float,
    final_equity: float,
    closed_trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
    timeframe: str,
) -> Dict[str, Any]:
    total_trades = len(closed_trades)
    net_profit = final_equity - initial_capital
    total_return_pct = ((final_equity - initial_capital) / initial_capital * 100.0) if initial_capital > 0 else 0.0

    wins = [t for t in closed_trades if t["pnl_usdt"] > 0]
    losses = [t for t in closed_trades if t["pnl_usdt"] <= 0]
    long_trades = [t for t in closed_trades if t["side"] == "BUY"]
    short_trades = [t for t in closed_trades if t["side"] == "SELL"]
    long_wins = [t for t in long_trades if t["pnl_usdt"] > 0]
    short_wins = [t for t in short_trades if t["pnl_usdt"] > 0]

    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    gross_profit = sum(t["pnl_usdt"] for t in wins)
    gross_loss = abs(sum(t["pnl_usdt"] for t in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)

    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (-gross_loss / len(losses)) if losses else 0.0
    expectancy_usdt = (net_profit / total_trades) if total_trades > 0 else 0.0
    avg_r_multiple = (sum(t["r_multiple"] for t in closed_trades) / total_trades) if total_trades > 0 else 0.0
    payoff_ratio = round(avg_win / abs(avg_loss), 2) if avg_loss < 0 else 0.0

    best_trade = max((t["pnl_usdt"] for t in closed_trades), default=0.0)
    worst_trade = min((t["pnl_usdt"] for t in closed_trades), default=0.0)
    total_fees = sum(t["fees_usdt"] for t in closed_trades)
    avg_bars_held = (sum(t["bars_held"] for t in closed_trades) / total_trades) if total_trades > 0 else 0.0
    tf_minutes = TIMEFRAME_SECONDS.get(timeframe, 900) / 60.0
    avg_duration_minutes = round(avg_bars_held * tf_minutes, 1)

    max_win_streak = 0
    max_loss_streak = 0
    cur_w = 0
    cur_l = 0
    for t in closed_trades:
        if t["pnl_usdt"] > 0:
            cur_w += 1
            cur_l = 0
            max_win_streak = max(max_win_streak, cur_w)
        else:
            cur_l += 1
            cur_w = 0
            max_loss_streak = max(max_loss_streak, cur_l)

    max_dd_pct = 0.0
    max_dd_usdt = 0.0
    for pt in equity_curve:
        dd_p = abs(float(pt.get("drawdown_pct", 0.0)))
        dd_u = float(pt.get("drawdown_usdt", 0.0))
        if dd_p > max_dd_pct:
            max_dd_pct = dd_p
        if dd_u > max_dd_usdt:
            max_dd_usdt = dd_u

    sharpe_ratio = 0.0
    sortino_ratio = 0.0
    if len(equity_curve) > 5:
        eq_vals = [float(pt["equity"]) for pt in equity_curve]
        rets = [
            (eq_vals[k] - eq_vals[k - 1]) / eq_vals[k - 1]
            for k in range(1, len(eq_vals))
            if eq_vals[k - 1] > 0
        ]
        periods_per_year = (365.0 * 86400.0) / TIMEFRAME_SECONDS.get(timeframe, 900)
        if len(rets) > 2:
            mean_r = sum(rets) / len(rets)
            var_r = sum((r - mean_r) ** 2 for r in rets) / max(1, len(rets) - 1)
            std_r = math.sqrt(var_r)
            if std_r > 1e-9:
                sharpe_ratio = float((mean_r / std_r) * math.sqrt(periods_per_year))
            downside = [r for r in rets if r < 0]
            if len(downside) > 2:
                mean_d = sum(downside) / len(downside)
                var_d = sum((r - mean_d) ** 2 for r in downside) / max(1, len(downside) - 1)
                std_d = math.sqrt(var_d)
                if std_d > 1e-9:
                    sortino_ratio = float((mean_r / std_d) * math.sqrt(periods_per_year))

    calmar_ratio = round(total_return_pct / max_dd_pct, 2) if max_dd_pct > 0.05 else 0.0

    by_exit_reason: Dict[str, Dict[str, Any]] = {}
    for t in closed_trades:
        r = t["exit_reason"]
        if r not in by_exit_reason:
            by_exit_reason[r] = {"count": 0, "pnl_usdt": 0.0, "wins": 0}
        by_exit_reason[r]["count"] += 1
        by_exit_reason[r]["pnl_usdt"] = round(by_exit_reason[r]["pnl_usdt"] + t["pnl_usdt"], 2)
        if t["pnl_usdt"] > 0:
            by_exit_reason[r]["wins"] += 1

    # PnL distribution buckets (in R multiples) for trade distribution chart
    r_buckets = [
        {"bucket": "<= -1.5R", "count": 0, "pnl_usdt": 0.0},
        {"bucket": "-1.5R à -0.5R", "count": 0, "pnl_usdt": 0.0},
        {"bucket": "-0.5R à 0R", "count": 0, "pnl_usdt": 0.0},
        {"bucket": "0R à +1R", "count": 0, "pnl_usdt": 0.0},
        {"bucket": "+1R à +2R", "count": 0, "pnl_usdt": 0.0},
        {"bucket": "> +2R", "count": 0, "pnl_usdt": 0.0},
    ]
    for t in closed_trades:
        rm = float(t["r_multiple"])
        p = float(t["pnl_usdt"])
        if rm <= -1.5:
            idx = 0
        elif rm <= -0.5:
            idx = 1
        elif rm <= 0.0:
            idx = 2
        elif rm <= 1.0:
            idx = 3
        elif rm <= 2.0:
            idx = 4
        else:
            idx = 5
        r_buckets[idx]["count"] += 1
        r_buckets[idx]["pnl_usdt"] = round(r_buckets[idx]["pnl_usdt"] + p, 2)

    buy_hold_return_pct = 0.0
    if len(equity_curve) >= 2 and equity_curve[0]["price"] > 0:
        first_p = equity_curve[0]["price"]
        last_p = equity_curve[-1]["price"]
        buy_hold_return_pct = round(((last_p - first_p) / first_p) * 100.0, 2)

    return {
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(final_equity, 2),
        "net_profit_usdt": round(net_profit, 2),
        "total_return_pct": round(total_return_pct, 2),
        "buy_hold_return_pct": buy_hold_return_pct,
        "alpha_vs_buy_hold_pct": round(total_return_pct - buy_hold_return_pct, 2),
        "total_trades": total_trades,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": profit_factor,
        "expectancy_usdt": round(expectancy_usdt, 2),
        "avg_r_multiple": round(avg_r_multiple, 2),
        "payoff_ratio": payoff_ratio,
        "avg_win_usdt": round(avg_win, 2),
        "avg_loss_usdt": round(avg_loss, 2),
        "best_trade_usdt": round(best_trade, 2),
        "worst_trade_usdt": round(worst_trade, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_usdt": round(max_dd_usdt, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "sortino_ratio": round(sortino_ratio, 2),
        "calmar_ratio": calmar_ratio,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "avg_bars_held": round(avg_bars_held, 1),
        "avg_duration_minutes": avg_duration_minutes,
        "total_fees_usdt": round(total_fees, 2),
        "long_trades": len(long_trades),
        "long_win_rate_pct": round((len(long_wins) / len(long_trades) * 100.0), 1) if long_trades else 0.0,
        "long_pnl_usdt": round(sum(t["pnl_usdt"] for t in long_trades), 2),
        "short_trades": len(short_trades),
        "short_win_rate_pct": round((len(short_wins) / len(short_trades) * 100.0), 1) if short_trades else 0.0,
        "short_pnl_usdt": round(sum(t["pnl_usdt"] for t in short_trades), 2),
        "by_exit_reason": by_exit_reason,
        "r_distribution": r_buckets,
    }


def _build_strategy_diagnostics(
    metrics: Dict[str, Any],
    closed_trades: List[Dict[str, Any]],
    rejection_counts: Dict[str, int],
    params: Dict[str, Any],
    data_quality: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Generates deterministic French quantitative diagnostics distinguishing calculated facts from hypotheses."""
    insights: List[Dict[str, str]] = []
    total_trades = metrics["total_trades"]

    if data_quality and data_quality.get("missing_intervals_count", 0) > 0:
        insights.append({
            "severity": "warning",
            "title": f"Fait calculé : {data_quality['missing_intervals_count']} intervalle(s) manquant(s) sur la période",
            "detail": f"La série historique comporte {data_quality['gap_ratio_pct']}% de lacunes non interpolées. Les indicateurs ont repris sur les bougies réelles suivantes.",
        })

    if total_trades == 0:
        top_rej = max(rejection_counts.items(), key=lambda x: x[1])[0] if rejection_counts else "score_too_low"
        insights.append({
            "severity": "warning",
            "title": "Fait calculé : 0 transaction exécutée sur l'échantillon",
            "detail": f"Les filtres actuels ont bloqué 100% des configurations (filtre principal : {top_rej}). Piste d'ajustement : réduire le Teddy Score minimum ({params['min_teddy_score']}) ou le filtre ADX ({params['adx_min']}).",
        })
        return insights

    sl_trades = [t for t in closed_trades if "STOP_LOSS" in t["exit_reason"]]
    premature_sl = [t for t in sl_trades if t["mfe_pct"] >= 0.75]
    if len(sl_trades) >= 3 and len(premature_sl) / len(sl_trades) >= 0.45:
        insights.append({
            "severity": "warning",
            "title": "Fait calculé : Stop Loss touché après excursion favorable (MFE >= +0.75%)",
            "detail": f"{len(premature_sl)}/{len(sl_trades)} positions stoppées avaient d'abord évolué en gain. Hypothèse à tester : élargir le multiplicateur SL ATR ({params['sl_atr_mult']}x) ou abaisser le seuil Break-Even ({params['breakeven_trigger_rr']}R).",
        })

    if metrics["long_trades"] >= 3 and metrics["short_trades"] >= 3:
        if metrics["long_pnl_usdt"] > 0 and metrics["short_pnl_usdt"] < -abs(metrics["long_pnl_usdt"]) * 0.5:
            insights.append({
                "severity": "info",
                "title": "Fait calculé : Asymétrie Long / Short (Shorts déficitaires)",
                "detail": f"Les LONG génèrent {metrics['long_pnl_usdt']:+.2f} USDT ({metrics['long_win_rate_pct']}% WR) contre {metrics['short_pnl_usdt']:+.2f} USDT ({metrics['short_win_rate_pct']}% WR) sur les SHORT. Hypothèse : activer le filtre EMA {params['ema_trend']}.",
            })
        elif metrics["short_pnl_usdt"] > 0 and metrics["long_pnl_usdt"] < -abs(metrics["short_pnl_usdt"]) * 0.5:
            insights.append({
                "severity": "info",
                "title": "Fait calculé : Asymétrie Long / Short (Longs déficitaires)",
                "detail": f"Les SHORT génèrent {metrics['short_pnl_usdt']:+.2f} USDT ({metrics['short_win_rate_pct']}% WR) contre {metrics['long_pnl_usdt']:+.2f} USDT ({metrics['long_win_rate_pct']}% WR) sur les LONG.",
            })

    gross_abs = abs(metrics["net_profit_usdt"]) + metrics["total_fees_usdt"]
    if metrics["total_fees_usdt"] > 0 and gross_abs > 0 and (metrics["total_fees_usdt"] / gross_abs) > 0.35:
        insights.append({
            "severity": "warning",
            "title": "Fait calculé : Poids élevé des frais et du slippage",
            "detail": f"Les frais cumulés ({metrics['total_fees_usdt']:.2f} USDT) représentent plus de 35% de la variation brute sur {total_trades} trades. Hypothèse : augmenter le Cooldown ({params['cooldown_candles']} bougies).",
        })

    if metrics["profit_factor"] >= 1.35 and metrics["max_drawdown_pct"] <= 12.0 and total_trades >= 8:
        insights.append({
            "severity": "success",
            "title": "Fait calculé : Espérance positive sur cet échantillon",
            "detail": f"Profit Factor de {metrics['profit_factor']} avec un Drawdown maximal de -{metrics['max_drawdown_pct']:.2f}% ({metrics['expectancy_usdt']:+.2f} USDT/trade). Vérifiez la tenue sur le segment Validation (Out-of-Sample) pour écarter tout surajustement.",
        })
    elif metrics["net_profit_usdt"] < 0:
        insights.append({
            "severity": "error",
            "title": "Fait calculé : Espérance mathématique négative sur la période",
            "detail": f"Perte nette de {metrics['net_profit_usdt']:.2f} USDT (Profit Factor {metrics['profit_factor']}). Comparez avec un autre scénario dans le Comparateur A/B.",
        })

    return insights


def run_parameter_sweep(
    symbol: str,
    timeframe: str,
    trading_style: str,
    base_params: Dict[str, Any],
    param_name: str,
    values: List[Any],
    market_type: str = "futures",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_candles: int = 800,
) -> Dict[str, Any]:
    """
    Runs a controlled sensitivity sweep across up to 8 values of a chosen parameter
    using the exact same preloaded historical dataset for speed and fairness.
    """
    allowed_sweep_params = {
        "min_teddy_score": "Score Teddy Minimum",
        "sl_atr_mult": "Multiplicateur SL (ATR)",
        "min_rr_ratio": "Ratio Risque/Rendement (R:R)",
        "adx_min": "Seuil ADX Minimum",
        "rsi_oversold": "Seuil RSI Survente",
        "rsi_overbought": "Seuil RSI Surachat",
        "ema_fast": "Période EMA Rapide",
        "ema_slow": "Période EMA Lente",
        "cooldown_candles": "Cooldown (bougies)",
        "risk_per_trade_pct": "Risque par Trade (%)",
    }
    if param_name not in allowed_sweep_params:
        param_name = "min_teddy_score"

    clean_values = values[:8] if isinstance(values, list) and values else [50, 55, 60, 65, 70]
    raw_df, data_source, _ = load_historical_candles(
        symbol=symbol,
        timeframe=timeframe,
        market_type=market_type,
        start_date=start_date,
        end_date=end_date,
        max_candles=max_candles,
    )
    preloaded = (raw_df, data_source)

    results = []
    for val in clean_values:
        p = dict(base_params or {})
        p[param_name] = val
        run_res = run_backtest_experiment(
            symbol=symbol,
            timeframe=timeframe,
            trading_style=trading_style,
            market_type=market_type,
            start_date=start_date,
            end_date=end_date,
            raw_params=p,
            max_candles=max_candles,
            allow_unreliable_data=True,
            preloaded_df=preloaded,
        )
        m = run_res["metrics"]
        results.append(
            {
                "param_value": val,
                "total_return_pct": m["total_return_pct"],
                "net_profit_usdt": m["net_profit_usdt"],
                "win_rate_pct": m["win_rate_pct"],
                "profit_factor": m["profit_factor"],
                "max_drawdown_pct": m["max_drawdown_pct"],
                "sharpe_ratio": m["sharpe_ratio"],
                "total_trades": m["total_trades"],
                "expectancy_usdt": m["expectancy_usdt"],
            }
        )

    best_row = max(
        results,
        key=lambda r: (r["profit_factor"] if r["total_trades"] >= 3 else -999.0, r["total_return_pct"]),
    ) if results else None
    return {
        "market_type": market_type,
        "symbol": _normalize_lab_symbol(symbol),
        "timeframe": timeframe,
        "trading_style": trading_style,
        "param_name": param_name,
        "param_label": allowed_sweep_params.get(param_name, param_name),
        "results": results,
        "best": best_row,
    }


def generate_gemini_lab_analysis(
    run_a: Dict[str, Any],
    run_b: Optional[Dict[str, Any]] = None,
    admin_question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    On-demand AI interpretation of already-calculated Strategy Lab results.
    - NEVER invents metrics; receives exact engine-computed JSON.
    - Clearly separates [FAITS CALCULÉS PAR LE MOTEUR] and [HYPOTHÈSES & PISTES DE RECHERCHE].
    - Falls back to a structured deterministic quantitative synthesis if GEMINI_API_KEY is not configured.
    """
    m1 = run_a.get("metrics", {})
    p1 = run_a.get("params", {})
    q1 = run_a.get("data_quality", {})

    facts_lines = [
        f"• Expérience #{run_a.get('id', 'Active')} : {run_a.get('symbol')} ({run_a.get('market_type', 'futures').upper()} • {run_a.get('timeframe')}) sur {run_a.get('candles_count')} chandeliers ({run_a.get('data_source')}).",
        f"• Qualité des données : statut {q1.get('status', 'VALID')}, {q1.get('missing_intervals_count', 0)} intervalle(s) manquant(s), {q1.get('cached_reused_candles', 0)} bougies réutilisées du cache.",
        f"• Capital initial : {m1.get('initial_capital')} USDT → Capital final : {m1.get('final_capital')} USDT (Profit net : {m1.get('net_profit_usdt'):+.2f} USDT / {m1.get('total_return_pct'):+.2f}%).",
        f"• Transactions : {m1.get('total_trades')} ({m1.get('winning_trades')} gagnantes, {m1.get('losing_trades')} perdantes, Taux de réussite : {m1.get('win_rate_pct')}%).",
        f"• Profit Factor : {m1.get('profit_factor')} | Drawdown maximal : -{m1.get('max_drawdown_pct')}% (-{m1.get('max_drawdown_usdt')} USDT) | Frais totaux : {m1.get('total_fees_usdt')} USDT.",
    ]
    if run_b and run_b.get("metrics"):
        m2 = run_b["metrics"]
        facts_lines.append(
            f"• Comparaison avec Expérience #{run_b.get('id', 'B')} ({run_b.get('symbol')} {run_b.get('timeframe')}) : "
            f"Rendement {m2.get('total_return_pct'):+.2f}% vs {m1.get('total_return_pct'):+.2f}%, "
            f"Profit Factor {m2.get('profit_factor')} vs {m1.get('profit_factor')}, "
            f"Drawdown -{m2.get('max_drawdown_pct')}% vs -{m1.get('max_drawdown_pct')}%."
        )

    gemini_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if gemini_key:
        try:
            import requests
            prompt = (
                "Tu es l'analyste quantitatif du Strategy Lab privé de Bitsure. "
                "RÈGLE ABSOLUE : N'invente JAMAIS aucune métrique numérique. Utilise uniquement les chiffres fournis ci-dessous par le moteur de backtesting. "
                "Structure obligatoirement ta réponse en français en 3 sections courtes :\n"
                "1. FAITS CALCULÉS PAR LE MOTEUR (rappel fidèle des chiffres clés et de la qualité des données)\n"
                "2. HYPOTHÈSES D'INTERPRÉTATION & LIMITES (analyse du drawdown, des frais, du risque de surajustement)\n"
                "3. PISTES DE TEST MANUEL (sans modifier automatiquement les paramètres).\n\n"
                f"DONNÉES CALCULÉES :\n{chr(10).join(facts_lines)}\n"
                f"PARAMÈTRES A : Score>={p1.get('min_teddy_score')}, SL={p1.get('sl_atr_mult')}xATR, R:R>={p1.get('min_rr_ratio')}, ADX>={p1.get('adx_min')}\n"
            )
            if admin_question:
                prompt += f"\nQuestion de l'administrateur : {admin_question}\n"

            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=12,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates") or []
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts") or []
                    if parts and parts[0].get("text"):
                        return {
                            "provider": "Gemini 2.5 Flash (Assisté)",
                            "analysis": parts[0]["text"],
                            "facts_summary": facts_lines,
                        }
        except Exception as e:
            logger.warning("Gemini Lab analysis fallback: %s", e)

    # Deterministic structured synthesis when Gemini key is absent or unreachable
    hypotheses = []
    if m1.get("total_trades", 0) < 15:
        hypotheses.append(
            "• Échantillon statistique restreint (< 15 transactions) : les métriques (Win Rate, Profit Factor) ont une variance élevée et peuvent être sensibles au surajustement."
        )
    if m1.get("max_drawdown_pct", 0) > 10.0:
        hypotheses.append(
            f"• Drawdown maximal notable (-{m1.get('max_drawdown_pct')}%) : réduire le risque par trade ({p1.get('risk_per_trade_pct')}%) ou activer le filtre de tendance EMA {p1.get('ema_trend')} pourrait amortir les séries de pertes."
        )
    if m1.get("profit_factor", 0) >= 1.25:
        hypotheses.append(
            "• Le ratio gains/pertes est positif sur cette période. Il est recommandé de relancer exactement ces paramètres sur le segment « Validation (20% Out-of-Sample) » avant de désigner cette configuration comme candidate."
        )
    else:
        hypotheses.append(
            "• Le Profit Factor est inférieur à 1.25 : vérifiez dans l'onglet « Diagnostic des Filtres » si les pertes proviennent de signaux à contre-tendance ou de Stop Loss trop serrés."
        )

    text_report = (
        "1. FAITS CALCULÉS PAR LE MOTEUR (100% Déterministes)\n"
        + "\n".join(facts_lines)
        + "\n\n2. HYPOTHÈSES D'INTERPRÉTATION & LIMITES MÉTHODOLOGIQUES\n"
        + "\n".join(hypotheses)
    )
    return {
        "provider": "Synthèse Quantitative Déterministe Bitsure (Moteur Interne)",
        "analysis": text_report,
        "facts_summary": facts_lines,
    }


# ==============================================================================
# DATABASE PERSISTENCE HELPERS (ADMIN ONLY)
# ==============================================================================
def ensure_default_presets(admin_user_id: int) -> None:
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS cnt FROM strategy_lab_presets").fetchone()
    if row:
        rd = dict(row) if hasattr(row, "keys") else {"cnt": row[0]}
        if int(rd.get("cnt", 0)) > 0:
            return
    now = time.time()
    for p in DEFAULT_STRATEGY_PRESETS:
        db.execute(
            """
            INSERT INTO strategy_lab_presets
            (name, description, symbol, timeframe, trading_style, params_json, tags, is_favorite, notes, created_by, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
            """,
            (
                p["name"],
                p["description"],
                "BTCUSDT",
                p["timeframe"],
                p["trading_style"],
                json.dumps(p["params"]),
                p["tags"],
                "Preset officiel Bitsure pré-configuré.",
                admin_user_id,
                now,
                now,
            ),
        )


def list_lab_presets(admin_user_id: int) -> List[Dict[str, Any]]:
    ensure_default_presets(admin_user_id)
    db = get_db()
    rows = db.execute(
        "SELECT * FROM strategy_lab_presets ORDER BY is_favorite DESC, updated_at DESC"
    ).fetchall()
    out = []
    for raw_r in rows:
        r = dict(raw_r)
        try:
            params = json.loads(r.get("params_json") or "{}")
        except Exception:
            params = {}
        out.append(
            {
                "id": int(r["id"]),
                "name": r["name"],
                "description": r.get("description") or "",
                "symbol": r.get("symbol") or "BTCUSDT",
                "timeframe": r.get("timeframe") or "15m",
                "trading_style": r.get("trading_style") or "day",
                "params": params,
                "tags": r.get("tags") or "",
                "is_favorite": bool(r.get("is_favorite")),
                "notes": r.get("notes") or "",
                "created_at": float(r.get("created_at") or 0),
                "updated_at": float(r.get("updated_at") or 0),
            }
        )
    return out


def save_lab_preset(admin_user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    now = time.time()
    name = (payload.get("name") or "Stratégie Personnalisée").strip()[:120]
    description = (payload.get("description") or "").strip()[:500]
    symbol = _normalize_lab_symbol(payload.get("symbol") or "BTCUSDT")
    timeframe = payload.get("timeframe") or "15m"
    style = payload.get("trading_style") or "day"
    params = normalize_lab_params(payload.get("params"), style=style)
    tags = (payload.get("tags") or "custom").strip()[:120]
    notes = (payload.get("notes") or "").strip()[:1000]
    is_fav = 1 if payload.get("is_favorite") else 0

    preset_id = payload.get("id")
    if preset_id:
        db.execute(
            """
            UPDATE strategy_lab_presets
            SET name = %s, description = %s, symbol = %s, timeframe = %s, trading_style = %s,
                params_json = %s, tags = %s, is_favorite = %s, notes = %s, updated_at = %s
            WHERE id = %s
            """,
            (name, description, symbol, timeframe, style, json.dumps(params), tags, is_fav, notes, now, int(preset_id)),
        )
    else:
        db.execute(
            """
            INSERT INTO strategy_lab_presets
            (name, description, symbol, timeframe, trading_style, params_json, tags, is_favorite, notes, created_by, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (name, description, symbol, timeframe, style, json.dumps(params), tags, is_fav, notes, admin_user_id, now, now),
        )
    return {"ok": True, "presets": list_lab_presets(admin_user_id)}


def delete_lab_preset(admin_user_id: int, preset_id: int) -> List[Dict[str, Any]]:
    db = get_db()
    db.execute("DELETE FROM strategy_lab_presets WHERE id = %s", (int(preset_id),))
    return list_lab_presets(admin_user_id)


def save_lab_run(
    admin_user_id: int,
    run_data: Dict[str, Any],
    name: Optional[str] = None,
    notes: str = "",
    tags: str = "",
    parent_run_id: Optional[int] = None,
) -> int:
    db = get_db()
    now = time.time()
    mkt = run_data.get("market_type", "futures")
    split = run_data.get("period_split", "full")
    run_name = (
        name
        or f"{run_data['symbol']} {mkt.upper()} {run_data['timeframe']} ({run_data['trading_style'].upper()}) — Score>={run_data['params'].get('min_teddy_score', 58)}"
    )[:140]
    db.execute(
        """
        INSERT INTO strategy_lab_runs
        (name, preset_id, parent_run_id, market_type, symbol, timeframe, trading_style, period_split,
         start_date, end_date, data_source, candles_count, engine_version, strategy_version, status,
         is_candidate, data_quality_json, steps_json, params_json, metrics_json, trades_json, equity_json,
         signals_summary_json, tags, is_favorite, notes, created_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
        """,
        (
            run_name,
            run_data.get("preset_id"),
            int(parent_run_id) if parent_run_id else None,
            mkt,
            run_data["symbol"],
            run_data["timeframe"],
            run_data["trading_style"],
            split,
            run_data.get("start_date", ""),
            run_data.get("end_date", ""),
            run_data.get("data_source", "Binance Historical"),
            int(run_data.get("candles_count", 0)),
            run_data.get("engine_version", ENGINE_VERSION),
            run_data.get("strategy_version", STRATEGY_VERSION),
            run_data.get("status", "COMPLETED"),
            json.dumps(run_data.get("data_quality", {})),
            json.dumps(run_data.get("execution_steps", [])),
            json.dumps(run_data.get("params", {})),
            json.dumps(run_data.get("metrics", {})),
            json.dumps(run_data.get("trades", [])),
            json.dumps(run_data.get("equity_curve", [])),
            json.dumps({
                "signals_summary": run_data.get("signals_summary", {}),
                "diagnostics": run_data.get("diagnostics", []),
                "candles": run_data.get("candles", []),
            }),
            tags,
            notes,
            admin_user_id,
            now,
        ),
    )
    row = db.execute("SELECT id FROM strategy_lab_runs ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else 0


def list_lab_runs(limit: int = 35) -> List[Dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        """
        SELECT id, name, preset_id, parent_run_id, market_type, symbol, timeframe, trading_style,
               period_split, start_date, end_date, data_source, candles_count, engine_version,
               strategy_version, status, is_candidate, data_quality_json, params_json, metrics_json,
               tags, is_favorite, notes, created_at
        FROM strategy_lab_runs
        ORDER BY is_candidate DESC, is_favorite DESC, created_at DESC
        LIMIT %s
        """,
        (int(limit),),
    ).fetchall()
    out = []
    for raw_r in rows:
        r = dict(raw_r)
        try:
            params = json.loads(r.get("params_json") or "{}")
        except Exception:
            params = {}
        try:
            metrics = json.loads(r.get("metrics_json") or "{}")
        except Exception:
            metrics = {}
        try:
            dq = json.loads(r.get("data_quality_json") or "{}")
        except Exception:
            dq = {}
        out.append(
            {
                "id": int(r["id"]),
                "name": r["name"],
                "preset_id": r.get("preset_id"),
                "parent_run_id": r.get("parent_run_id"),
                "market_type": r.get("market_type") or "futures",
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "trading_style": r["trading_style"],
                "period_split": r.get("period_split") or "full",
                "start_date": r.get("start_date") or "",
                "end_date": r.get("end_date") or "",
                "data_source": r.get("data_source") or "",
                "candles_count": int(r.get("candles_count") or 0),
                "engine_version": r.get("engine_version") or ENGINE_VERSION,
                "strategy_version": r.get("strategy_version") or STRATEGY_VERSION,
                "status": r.get("status") or "COMPLETED",
                "is_candidate": bool(r.get("is_candidate")),
                "data_quality": dq,
                "params": params,
                "metrics": metrics,
                "tags": r.get("tags") or "",
                "is_favorite": bool(r.get("is_favorite")),
                "notes": r.get("notes") or "",
                "created_at": float(r.get("created_at") or 0),
            }
        )
    return out


def get_lab_run_detail(run_id: int) -> Optional[Dict[str, Any]]:
    db = get_db()
    raw_r = db.execute("SELECT * FROM strategy_lab_runs WHERE id = %s", (int(run_id),)).fetchone()
    if not raw_r:
        return None
    r = dict(raw_r)
    extra = json.loads(r.get("signals_summary_json") or "{}")
    return {
        "id": int(r["id"]),
        "name": r["name"],
        "preset_id": r.get("preset_id"),
        "parent_run_id": r.get("parent_run_id"),
        "market_type": r.get("market_type") or "futures",
        "symbol": r["symbol"],
        "timeframe": r["timeframe"],
        "trading_style": r["trading_style"],
        "period_split": r.get("period_split") or "full",
        "start_date": r.get("start_date") or "",
        "end_date": r.get("end_date") or "",
        "data_source": r.get("data_source") or "",
        "candles_count": int(r.get("candles_count") or 0),
        "engine_version": r.get("engine_version") or ENGINE_VERSION,
        "strategy_version": r.get("strategy_version") or STRATEGY_VERSION,
        "status": r.get("status") or "COMPLETED",
        "is_candidate": bool(r.get("is_candidate")),
        "data_quality": json.loads(r.get("data_quality_json") or "{}"),
        "execution_steps": json.loads(r.get("steps_json") or "[]"),
        "params": json.loads(r.get("params_json") or "{}"),
        "metrics": json.loads(r.get("metrics_json") or "{}"),
        "trades": json.loads(r.get("trades_json") or "[]"),
        "equity_curve": json.loads(r.get("equity_json") or "[]"),
        "signals_summary": extra.get("signals_summary", {}),
        "diagnostics": extra.get("diagnostics", []),
        "candles": extra.get("candles", []),
        "tags": r.get("tags") or "",
        "is_favorite": bool(r.get("is_favorite")),
        "notes": r.get("notes") or "",
        "created_at": float(r.get("created_at") or 0),
    }


def update_lab_run_meta(
    run_id: int,
    name: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[str] = None,
    is_favorite: Optional[bool] = None,
    is_candidate: Optional[bool] = None,
) -> bool:
    db = get_db()
    raw_row = db.execute(
        "SELECT id, name, notes, tags, is_favorite, is_candidate FROM strategy_lab_runs WHERE id = %s",
        (int(run_id),),
    ).fetchone()
    if not raw_row:
        return False
    row = dict(raw_row)
    new_name = (name if name is not None else row["name"]).strip()[:140]
    new_notes = (notes if notes is not None else (row.get("notes") or "")).strip()[:2000]
    new_tags = (tags if tags is not None else (row.get("tags") or "")).strip()[:150]
    new_fav = (1 if is_favorite else 0) if is_favorite is not None else int(row.get("is_favorite") or 0)
    new_cand = (1 if is_candidate else 0) if is_candidate is not None else int(row.get("is_candidate") or 0)

    if is_candidate is True:
        # Clear previous candidate flag so the newly designated candidate stands out clearly
        db.execute("UPDATE strategy_lab_runs SET is_candidate = 0 WHERE is_candidate = 1")

    db.execute(
        "UPDATE strategy_lab_runs SET name = %s, notes = %s, tags = %s, is_favorite = %s, is_candidate = %s WHERE id = %s",
        (new_name, new_notes, new_tags, new_fav, new_cand, int(run_id)),
    )
    return True


def delete_lab_run(run_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM strategy_lab_runs WHERE id = %s", (int(run_id),))
