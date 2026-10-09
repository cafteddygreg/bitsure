"""
strategy_lab.py — Bitsure Teddy Admin-Only Strategy Lab & Backtesting Engine
===========================================================================
STRICT ISOLATION GUARANTEE:
- This module is 100% isolated from live order execution, Binance trading endpoints,
  PaperTrader balances, and user auto-trading loops.
- It NEVER imports `live_trader`, `position_manager`, or any order placement function
  from `binance_manager`.
- All calculations run exclusively in-memory on historical OHLCV DataFrames and store
  results only in the dedicated `strategy_lab_*` database tables.
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
from indicators import macd, adx, bollinger_bands
from data_fetcher import normalize_symbol

logger = logging.getLogger("strategy_lab")

# Safety Assertion: Ensure no live order modules are ever imported here
FORBIDDEN_LIVE_MODULES = ("live_trader", "position_manager")

SUPPORTED_LAB_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
]

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


def load_historical_candles(
    symbol: str,
    timeframe: str = "15m",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_candles: int = 1200,
) -> Tuple[pd.DataFrame, str]:
    """
    Loads real historical OHLCV candles for the Strategy Lab:
    1. Checks DB cache (`strategy_lab_candles_cache`) if exact range was recently fetched.
    2. Queries public Binance Klines API (`/api/v3/klines` or `/fapi/v1/klines`) via requests (read-only).
    3. Falls back to local `/scratch/btc_15m.csv` or `DataFetcher` if network is restricted.
    Returns (DataFrame, data_source_label).
    """
    symbol = normalize_symbol(symbol or "BTCUSDT")
    if timeframe not in SUPPORTED_LAB_TIMEFRAMES:
        timeframe = "15m"
    max_candles = max(120, min(2500, int(max_candles or 1000)))

    now_ms = int(time.time() * 1000)
    tf_ms = TIMEFRAME_SECONDS.get(timeframe, 900) * 1000
    end_ms = _parse_date_to_ms(end_date, now_ms)
    default_start_ms = end_ms - (max_candles * tf_ms)
    start_ms = _parse_date_to_ms(start_date, default_start_ms)
    if start_ms >= end_ms:
        start_ms = end_ms - (300 * tf_ms)

    cache_key = f"{symbol}_{timeframe}_{start_ms // 60000}_{end_ms // 60000}_{max_candles}"
    db = get_db()

    # 1. Check DB Cache
    try:
        row = db.execute(
            "SELECT candles_json, data_source FROM strategy_lab_candles_cache WHERE cache_key = %s",
            (cache_key,),
        ).fetchone()
        if row and row.get("candles_json"):
            records = json.loads(row["candles_json"])
            if len(records) >= 60:
                df = pd.DataFrame(records)
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                df.set_index("timestamp", inplace=True)
                for col in ("Open", "High", "Low", "Close", "Volume"):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
                return df, f"{row.get('data_source', 'Binance Historical')} (Cache)"
    except Exception as e:
        logger.debug("Strategy Lab cache read skipped: %s", e)

    # 2. Fetch from Public Read-Only Binance Klines Endpoints (Spot / Futures mirrors)
    import requests
    klines_collected: List[Any] = []
    source_used = ""
    endpoints = [
        ("https://api.binance.com/api/v3/klines", "Binance Spot Historical"),
        ("https://data-api.binance.vision/api/v3/klines", "Binance Vision Archive"),
        ("https://fapi.binance.com/fapi/v1/klines", "Binance Futures Historical"),
    ]

    for url, label in endpoints:
        try:
            cursor_ms = start_ms
            batches = []
            while cursor_ms < end_ms and sum(len(b) for b in batches) < max_candles:
                needed = min(1000, max_candles - sum(len(b) for b in batches))
                resp = requests.get(
                    url,
                    params={
                        "symbol": symbol,
                        "interval": timeframe,
                        "startTime": cursor_ms,
                        "endTime": end_ms,
                        "limit": needed,
                    },
                    timeout=6,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                batches.append(data)
                last_open_time = int(data[-1][0])
                if last_open_time <= cursor_ms or len(data) < needed:
                    break
                cursor_ms = last_open_time + tf_ms

            flat = [item for sub in batches for item in sub]
            if len(flat) >= 60:
                klines_collected = flat
                source_used = label
                break
        except Exception as e:
            logger.debug("Public klines endpoint %s failed: %s", url, e)

    if klines_collected:
        rows = []
        for k in klines_collected[-max_candles:]:
            ts_iso = datetime.fromtimestamp(int(k[0]) / 1000.0, tz=timezone.utc).isoformat()
            rows.append(
                {
                    "timestamp": ts_iso,
                    "Open": float(k[1]),
                    "High": float(k[2]),
                    "Low": float(k[3]),
                    "Close": float(k[4]),
                    "Volume": float(k[5]),
                }
            )
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.set_index("timestamp", inplace=True)
        df = df[~df.index.duplicated(keep="last")].sort_index()

        # Store in DB cache
        try:
            db.execute(
                """
                INSERT INTO strategy_lab_candles_cache (cache_key, symbol, timeframe, start_ts, end_ts, data_source, candles_json, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET
                    candles_json = EXCLUDED.candles_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (cache_key, symbol, timeframe, start_ms, end_ms, source_used, json.dumps(rows), time.time()),
            )
        except Exception as e:
            logger.debug("Strategy Lab cache write skipped: %s", e)

        return df, source_used

    # 3. Fallback to local CSV archive (/scratch/btc_15m.csv) or DataFetcher
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
                if len(df) >= 60:
                    return df, "Archive Locale Bitsure (btc_15m.csv)"
            except Exception as e:
                logger.warning("Fallback CSV read error: %s", e)

    # 4. Final fallback via DataFetcher
    from data_fetcher import DataFetcher
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        df, src = loop.run_until_complete(
            DataFetcher.get_instance().get_historical_data(symbol, interval=timeframe, limit=min(500, max_candles))
        )
        loop.close()
        if df is not None and not df.empty:
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            return df.tail(max_candles), f"{src} (Fallback)"
    except Exception as e:
        logger.error("DataFetcher fallback failed in Strategy Lab: %s", e)

    raise ValueError(f"Impossible de charger les bougies historiques pour {symbol} ({timeframe}).")


def _compute_lab_indicators(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Computes parameterized technical indicators on the OHLCV DataFrame without look-ahead bias."""
    from indicators import rsi as calc_rsi, atr as calc_atr
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
    adx = float(row.get("ADX", 20.0) if not pd.isna(row.get("ADX")) else 20.0)
    macd_hist = float(row.get("MACD_Hist", 0.0) if not pd.isna(row.get("MACD_Hist")) else 0.0)
    prev_macd_hist = float(prev_row.get("MACD_Hist", 0.0) if not pd.isna(prev_row.get("MACD_Hist")) else 0.0)
    atr = float(row["LAB_ATR"])
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
    if adx >= float(params["adx_min"]):
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

    # Filter Pipeline (tracks exact rejection causes for admin diagnostics)
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

    if adx < float(params["adx_min"]):
        return {
            "signal": "WAIT",
            "candidate_direction": raw_direction,
            "teddy_score": raw_score,
            "rejected_by": "weak_adx_regime",
            "rejection_reason": f"Marché sans tendance claire (ADX {adx:.1f} < {params['adx_min']})",
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

    if bool(params.get("block_against_strong_trend", True)) and adx >= 30.0:
        if raw_direction == "BUY" and close < ema_slow and ema_fast < ema_slow:
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "counter_strong_trend",
                "rejection_reason": f"Signal BUY contre une tendance baissière forte (ADX {adx:.1f})",
                "reasons": primary_reasons,
            }
        if raw_direction == "SELL" and close > ema_slow and ema_fast > ema_slow:
            return {
                "signal": "WAIT",
                "candidate_direction": raw_direction,
                "teddy_score": raw_score,
                "rejected_by": "counter_strong_trend",
                "rejection_reason": f"Signal SELL contre une tendance haussière forte (ADX {adx:.1f})",
                "reasons": primary_reasons,
            }

    # Compute SL & TP distances
    if params.get("sl_mode") == "fixed_pct":
        sl_dist = close * (float(params["sl_fixed_pct"]) / 100.0)
    else:
        sl_dist = max(atr * float(params["sl_atr_mult"]), close * 0.0025)

    tp_mode = params.get("tp_mode", "rr")
    if tp_mode == "fixed_pct":
        tp_dist = close * (float(params["tp_fixed_pct"]) / 100.0)
    elif tp_mode == "atr":
        tp_dist = max(atr * float(params["tp_atr_mult"]), sl_dist * 1.1)
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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    raw_params: Optional[Dict[str, Any]] = None,
    max_candles: int = 1000,
    preloaded_df: Optional[Tuple[pd.DataFrame, str]] = None,
) -> Dict[str, Any]:
    """
    Runs a complete, deterministic candle-by-candle backtest simulation with zero look-ahead bias.
    Calculates all institutional KPIs, candle overlays, signal markers, rejection breakdown,
    and automatic diagnosis of strategy weaknesses.
    """
    t0 = time.time()
    symbol = normalize_symbol(symbol or "BTCUSDT")
    params = normalize_lab_params(raw_params, style=trading_style)

    if preloaded_df is not None:
        raw_df, data_source = preloaded_df
    else:
        raw_df, data_source = load_historical_candles(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            max_candles=max_candles,
        )

    df = _compute_lab_indicators(raw_df, params)
    warmup = max(35, min(120, int(params["ema_slow"]) + 5))
    if len(df) <= warmup + 10:
        warmup = max(15, len(df) // 5)

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
        atr = float(row["LAB_ATR"])

        candle_marker: Optional[Dict[str, Any]] = None

        # 1. Manage Open Position on Current Candle
        if open_pos is not None:
            open_pos["bars_held"] += 1
            side = open_pos["side"]
            entry_p = open_pos["entry_price"]
            init_sl_dist = open_pos["initial_sl_dist"]

            # Track MFE (Max Favorable Excursion) & MAE (Max Adverse Excursion)
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

            # A. Partial Take Profit Check
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

            # B. Break-Even Stop Adjustment
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

            # C. Dynamic Trailing Stop Adjustment
            if (
                bool(params.get("trailing_stop_enabled", True))
                and current_r >= float(params.get("trailing_activation_rr", 1.3))
            ):
                trail_dist = max(atr * float(params.get("trailing_distance_atr", 1.1)), entry_p * 0.002)
                if side == "BUY":
                    new_sl = high - trail_dist
                    if new_sl > open_pos["sl_price"]:
                        open_pos["sl_price"] = new_sl
                        open_pos["trailing_activated"] = True
                else:
                    new_sl = low + trail_dist
                    if new_sl < open_pos["sl_price"]:
                        open_pos["sl_price"] = new_sl
                        open_pos["trailing_activated"] = True

            # D. Check Stop Loss / Take Profit / Max Bars Exit
            exit_reason = None
            raw_exit_price = None

            if side == "BUY":
                if low <= open_pos["sl_price"]:
                    raw_exit_price = open_pos["sl_price"]
                    exit_reason = "TRAILING_SL" if open_pos["trailing_activated"] else ("BREAKEVEN_SL" if open_pos["be_activated"] else "STOP_LOSS")
                elif high >= open_pos["tp_price"]:
                    raw_exit_price = open_pos["tp_price"]
                    exit_reason = "TAKE_PROFIT"
            else:
                if high >= open_pos["sl_price"]:
                    raw_exit_price = open_pos["sl_price"]
                    exit_reason = "TRAILING_SL" if open_pos["trailing_activated"] else ("BREAKEVEN_SL" if open_pos["be_activated"] else "STOP_LOSS")
                elif low <= open_pos["tp_price"]:
                    raw_exit_price = open_pos["tp_price"]
                    exit_reason = "TAKE_PROFIT"

            if exit_reason is None and open_pos["bars_held"] >= int(params.get("max_bars_in_trade", 48)):
                raw_exit_price = close
                exit_reason = "TIME_STOP"

            # E. Check Opposite Signal Exit if still open
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
                    "side": side,
                    "price": round(exec_exit, 4),
                    "pnl_usdt": round(total_net_pnl, 2),
                    "exit_reason": exit_reason,
                }

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
                # Check Cooldown, Max Trades/Day, Max Consecutive Losses
                if i < cooldown_until_idx:
                    rejection_counts["cooldown_or_limits"] += 1
                elif trades_today >= int(params.get("max_trades_per_day", 8)):
                    rejection_counts["cooldown_or_limits"] += 1
                elif consecutive_losses >= int(params.get("max_consecutive_losses", 4)):
                    rejection_counts["cooldown_or_limits"] += 1
                    # Reset consecutive loss circuit breaker after skipping one valid setup
                    consecutive_losses = max(0, consecutive_losses - 1)
                else:
                    side = sig_eval["signal"]
                    exec_entry = close * (1.0 + slippage_rate) if side == "BUY" else close * (1.0 - slippage_rate)
                    sl_dist = float(sig_eval["sl_dist"])
                    tp_dist = float(sig_eval["tp_dist"])
                    sl_price = exec_entry - sl_dist if side == "BUY" else exec_entry + sl_dist
                    tp_price = exec_entry + tp_dist if side == "BUY" else exec_entry - tp_dist

                    # Position Sizing
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
                            "side": side,
                            "price": round(exec_entry, 4),
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

    # Compute Comprehensive Institutional Metrics
    metrics = _compute_backtest_metrics(
        initial_capital=initial_capital,
        final_equity=equity_curve[-1]["equity"] if equity_curve else initial_capital,
        closed_trades=closed_trades,
        equity_curve=equity_curve,
        timeframe=timeframe,
    )

    # Diagnostic Insights for the Admin ("Pourquoi la stratégie perd ou gagne")
    diagnostics = _build_strategy_diagnostics(metrics, closed_trades, rejection_counts, params)

    elapsed_ms = int((time.time() - t0) * 1000)

    # Downsample chart_candles & equity_curve if > 450 points to keep UI ultra-responsive while keeping all markers
    sampled_candles = _downsample_candles_preserving_markers(chart_candles, max_points=450)
    sampled_equity = _downsample_list(equity_curve, max_points=450)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "trading_style": trading_style,
        "data_source": data_source,
        "start_date": str(df.index[warmup].isoformat()) if len(df) > warmup else "",
        "end_date": str(df.index[-1].isoformat()) if len(df) > 0 else "",
        "candles_count": len(df) - warmup,
        "execution_ms": elapsed_ms,
        "params": params,
        "metrics": metrics,
        "diagnostics": diagnostics,
        "signals_summary": {
            "total_candles_evaluated": len(df) - warmup,
            "valid_signals": valid_signals_count,
            "executed_trades": len(closed_trades),
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

    # Max Consecutive Wins / Losses
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

    # Drawdown & Sharpe / Sortino / Calmar
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

    # Performance by exit reason
    by_exit_reason: Dict[str, Dict[str, Any]] = {}
    for t in closed_trades:
        r = t["exit_reason"]
        if r not in by_exit_reason:
            by_exit_reason[r] = {"count": 0, "pnl_usdt": 0.0, "wins": 0}
        by_exit_reason[r]["count"] += 1
        by_exit_reason[r]["pnl_usdt"] = round(by_exit_reason[r]["pnl_usdt"] + t["pnl_usdt"], 2)
        if t["pnl_usdt"] > 0:
            by_exit_reason[r]["wins"] += 1

    # Buy & Hold benchmark comparison on same period
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
    }


def _build_strategy_diagnostics(
    metrics: Dict[str, Any],
    closed_trades: List[Dict[str, Any]],
    rejection_counts: Dict[str, int],
    params: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Generates clear French quantitative diagnostics to help the administrator improve the strategy."""
    insights: List[Dict[str, str]] = []
    total_trades = metrics["total_trades"]

    if total_trades == 0:
        top_rej = max(rejection_counts.items(), key=lambda x: x[1])[0] if rejection_counts else "score_too_low"
        insights.append({
            "severity": "warning",
            "title": "Aucun trade exécuté sur la période",
            "detail": f"Les filtres actuels ont bloqué 100% des configurations (cause principale : {top_rej}). Essayez d'abaisser le Teddy Score minimum ({params['min_teddy_score']}) ou le filtre ADX ({params['adx_min']}).",
        })
        return insights

    # 1. Stop Loss Premature Hit Analysis (MFE vs SL)
    sl_trades = [t for t in closed_trades if t["exit_reason"] == "STOP_LOSS"]
    premature_sl = [t for t in sl_trades if t["mfe_pct"] >= 0.75]
    if len(sl_trades) >= 3 and len(premature_sl) / len(sl_trades) >= 0.45:
        insights.append({
            "severity": "warning",
            "title": "Stop Loss fréquemment touché après un départ favorable",
            "detail": f"{len(premature_sl)}/{len(sl_trades)} positions stoppées avaient pourtant évolué en gain (MFE >= +0.75%). Envisagez d'augmenter le multiplicateur SL ATR ({params['sl_atr_mult']}x -> {round(params['sl_atr_mult'] + 0.3, 1)}x) ou d'abaisser le seuil Break-Even.",
        })

    # 2. Long vs Short Asymmetry
    if metrics["long_trades"] >= 3 and metrics["short_trades"] >= 3:
        if metrics["long_pnl_usdt"] > 0 and metrics["short_pnl_usdt"] < -abs(metrics["long_pnl_usdt"]) * 0.5:
            insights.append({
                "severity": "info",
                "title": "Asymétrie Long / Short marquée (Shorts déficitaires)",
                "detail": f"Les positions LONG génèrent {metrics['long_pnl_usdt']:+.2f} USDT ({metrics['long_win_rate_pct']}% WR) tandis que les SHORT perdent {metrics['short_pnl_usdt']:+.2f} USDT ({metrics['short_win_rate_pct']}% WR). Activer le filtre de tendance EMA {params['ema_trend']} peut filtrer les shorts à contre-tendance.",
            })
        elif metrics["short_pnl_usdt"] > 0 and metrics["long_pnl_usdt"] < -abs(metrics["short_pnl_usdt"]) * 0.5:
            insights.append({
                "severity": "info",
                "title": "Asymétrie Long / Short marquée (Longs déficitaires)",
                "detail": f"Les positions SHORT génèrent {metrics['short_pnl_usdt']:+.2f} USDT ({metrics['short_win_rate_pct']}% WR) tandis que les LONG perdent {metrics['long_pnl_usdt']:+.2f} USDT ({metrics['long_win_rate_pct']}% WR).",
            })

    # 3. Fee Drag Analysis
    gross_abs = abs(metrics["net_profit_usdt"]) + metrics["total_fees_usdt"]
    if metrics["total_fees_usdt"] > 0 and gross_abs > 0 and (metrics["total_fees_usdt"] / gross_abs) > 0.35:
        insights.append({
            "severity": "warning",
            "title": "Impact élevé des frais et du slippage (Overtrading)",
            "detail": f"Les frais cumulés ({metrics['total_fees_usdt']:.2f} USDT) absorbent une part importante de la performance sur {total_trades} trades. Augmentez le Cooldown ({params['cooldown_candles']} bougies) ou le Teddy Score minimum.",
        })

    # 4. Strong Robustness Confirmation
    if metrics["profit_factor"] >= 1.35 and metrics["max_drawdown_pct"] <= 12.0 and total_trades >= 8:
        insights.append({
            "severity": "success",
            "title": "Profil de risque robuste sur l'échantillon",
            "detail": f"Profit Factor de {metrics['profit_factor']} avec un Drawdown maîtrisé ({metrics['max_drawdown_pct']:.2f}%) et une espérance positive de {metrics['expectancy_usdt']:+.2f} USDT/trade.",
        })
    elif metrics["net_profit_usdt"] < 0:
        insights.append({
            "severity": "error",
            "title": "Espérance mathématique négative sur cette configuration",
            "detail": f"Perte nette de {metrics['net_profit_usdt']:.2f} USDT (Profit Factor {metrics['profit_factor']}). Utilisez l'outil Balayage de Paramètres (Grid Sweep) pour identifier la zone optimale de Score Teddy et SL ATR.",
        })

    return insights


def run_parameter_sweep(
    symbol: str,
    timeframe: str,
    trading_style: str,
    base_params: Dict[str, Any],
    param_name: str,
    values: List[Any],
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
    preloaded = load_historical_candles(
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        max_candles=max_candles,
    )

    results = []
    for val in clean_values:
        p = dict(base_params or {})
        p[param_name] = val
        run_res = run_backtest_experiment(
            symbol=symbol,
            timeframe=timeframe,
            trading_style=trading_style,
            start_date=start_date,
            end_date=end_date,
            raw_params=p,
            max_candles=max_candles,
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

    best_row = max(results, key=lambda r: (r["profit_factor"] if r["total_trades"] >= 3 else -999.0, r["total_return_pct"])) if results else None
    return {
        "symbol": normalize_symbol(symbol),
        "timeframe": timeframe,
        "trading_style": trading_style,
        "param_name": param_name,
        "param_label": allowed_sweep_params.get(param_name, param_name),
        "results": results,
        "best": best_row,
    }


# ==============================================================================
# DATABASE PERSISTENCE HELPERS (ADMIN ONLY)
# ==============================================================================
def ensure_default_presets(admin_user_id: int) -> None:
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS cnt FROM strategy_lab_presets").fetchone()
    if row and int(row.get("cnt", 0)) > 0:
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
    for r in rows:
        try:
            params = json.loads(r["params_json"])
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
    symbol = normalize_symbol(payload.get("symbol") or "BTCUSDT")
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


def save_lab_run(admin_user_id: int, run_data: Dict[str, Any], name: Optional[str] = None, notes: str = "", tags: str = "") -> int:
    db = get_db()
    now = time.time()
    run_name = (
        name
        or f"{run_data['symbol']} {run_data['timeframe']} ({run_data['trading_style'].upper()}) — Score>={run_data['params'].get('min_teddy_score', 58)}"
    )[:140]
    db.execute(
        """
        INSERT INTO strategy_lab_runs
        (name, preset_id, symbol, timeframe, trading_style, start_date, end_date, data_source, candles_count,
         params_json, metrics_json, trades_json, equity_json, signals_summary_json, tags, is_favorite, notes, created_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
        """,
        (
            run_name,
            run_data.get("preset_id"),
            run_data["symbol"],
            run_data["timeframe"],
            run_data["trading_style"],
            run_data.get("start_date", ""),
            run_data.get("end_date", ""),
            run_data.get("data_source", "Binance Historical"),
            int(run_data.get("candles_count", 0)),
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


def list_lab_runs(limit: int = 30) -> List[Dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        """
        SELECT id, name, preset_id, symbol, timeframe, trading_style, start_date, end_date,
               data_source, candles_count, params_json, metrics_json, tags, is_favorite, notes, created_at
        FROM strategy_lab_runs
        ORDER BY is_favorite DESC, created_at DESC
        LIMIT %s
        """,
        (int(limit),),
    ).fetchall()
    out = []
    for r in rows:
        try:
            params = json.loads(r["params_json"])
        except Exception:
            params = {}
        try:
            metrics = json.loads(r["metrics_json"])
        except Exception:
            metrics = {}
        out.append(
            {
                "id": int(r["id"]),
                "name": r["name"],
                "preset_id": r.get("preset_id"),
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "trading_style": r["trading_style"],
                "start_date": r.get("start_date") or "",
                "end_date": r.get("end_date") or "",
                "data_source": r.get("data_source") or "",
                "candles_count": int(r.get("candles_count") or 0),
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
    r = db.execute("SELECT * FROM strategy_lab_runs WHERE id = %s", (int(run_id),)).fetchone()
    if not r:
        return None
    extra = json.loads(r.get("signals_summary_json") or "{}")
    return {
        "id": int(r["id"]),
        "name": r["name"],
        "symbol": r["symbol"],
        "timeframe": r["timeframe"],
        "trading_style": r["trading_style"],
        "start_date": r.get("start_date") or "",
        "end_date": r.get("end_date") or "",
        "data_source": r.get("data_source") or "",
        "candles_count": int(r.get("candles_count") or 0),
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


def update_lab_run_meta(run_id: int, name: Optional[str] = None, notes: Optional[str] = None, tags: Optional[str] = None, is_favorite: Optional[bool] = None) -> bool:
    db = get_db()
    row = db.execute("SELECT id, name, notes, tags, is_favorite FROM strategy_lab_runs WHERE id = %s", (int(run_id),)).fetchone()
    if not row:
        return False
    new_name = (name if name is not None else row["name"]).strip()[:140]
    new_notes = (notes if notes is not None else (row.get("notes") or "")).strip()[:2000]
    new_tags = (tags if tags is not None else (row.get("tags") or "")).strip()[:150]
    new_fav = (1 if is_favorite else 0) if is_favorite is not None else int(row.get("is_favorite") or 0)
    db.execute(
        "UPDATE strategy_lab_runs SET name = %s, notes = %s, tags = %s, is_favorite = %s WHERE id = %s",
        (new_name, new_notes, new_tags, new_fav, int(run_id)),
    )
    return True


def delete_lab_run(run_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM strategy_lab_runs WHERE id = %s", (int(run_id),))
