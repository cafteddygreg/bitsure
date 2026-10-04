"""
indicators.py
-------------
Calculs vectorisés des indicateurs techniques sans biais de prévision (Lookahead Bias)
ni repainting, avec gestion stricte du warmup et filtrage des valeurs NaN / Inf.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, Iterable

# Période minimale de warmup recommandée pour stabiliser les EMA / Wilder smoothing
MIN_WARMUP_PERIODS: int = 200


def closed_series(series: pd.Series, use_closed_candle: bool = False) -> pd.Series:
    """Retourne la série arrêtée à la dernière bougie clôturée (exclut `iloc[-1]`)
    lorsque `use_closed_candle=True`, sinon retourne la série telle quelle.
    """
    if use_closed_candle and len(series) >= 2:
        return series.iloc[:-1]
    return series


# =========================================================
# RSI (Wilder / Rolling avec gestion propre des NaN)
# =========================================================

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calcule le Relative Strength Index (RSI) sur une série de prix de clôture.

    Remplace les divisions par zéro et les NaN de début de série par 50.0 (neutre)
    uniquement après calcul pour éviter toute exception en aval, tout en préservant
    la précision sur les bougies clôturées.
    """
    if close is None or close.empty or len(close) < period + 1:
        return pd.Series(dtype=float, index=close.index if close is not None else None)

    delta = close.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi_series = 100.0 - (100.0 / (1.0 + rs))
    # Lorsque avg_loss == 0 et avg_gain > 0, le RSI vaut 100 ; si les deux valent 0, 50.
    rsi_series = np.where((avg_loss == 0.0) & (avg_gain > 0.0), 100.0, rsi_series)
    rsi_series = pd.Series(rsi_series, index=close.index, dtype=float)
    return rsi_series.replace([np.inf, -np.inf], np.nan).fillna(50.0)


# =========================================================
# STOCHASTIC
# =========================================================

def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth: int = 3,
) -> Tuple[pd.Series, pd.Series]:
    """Calcule l'oscillateur Stochastique (%K lissé et %D)."""
    lowest_low = low.astype(float).rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.astype(float).rolling(window=k_period, min_periods=k_period).max()
    denom = (highest_high - lowest_low).replace(0.0, np.nan)
    stoch_k = 100.0 * ((close.astype(float) - lowest_low) / denom)
    stoch_k = stoch_k.replace([np.inf, -np.inf], np.nan).fillna(50.0)
    stoch_k_smooth = stoch_k.rolling(window=smooth, min_periods=1).mean()
    stoch_d = stoch_k_smooth.rolling(window=d_period, min_periods=1).mean()
    return stoch_k_smooth, stoch_d


# =========================================================
# WILDER SMOOTHING
# =========================================================

def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Lissage de Wilder : moyenne mobile exponentielle avec alpha = 1 / period."""
    return series.astype(float).ewm(alpha=1.0 / max(period, 1), adjust=False).mean()


# =========================================================
# ADX (Average Directional Index)
# =========================================================

def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calcule l'ADX, +DI et -DI avec le lissage de Wilder."""
    if len(high) < period + 1:
        zeros = pd.Series([0.0] * len(high), index=high.index, dtype=float)
        return zeros, zeros, zeros

    high_f = high.astype(float)
    low_f = low.astype(float)
    close_f = close.astype(float)

    tr1 = high_f - low_f
    tr2 = (high_f - close_f.shift(1)).abs()
    tr3 = (low_f - close_f.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high_f.diff()
    down_move = -low_f.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0.0), up_move, 0.0),
        index=high_f.index,
        dtype=float,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0.0), down_move, 0.0),
        index=high_f.index,
        dtype=float,
    )

    atr_smooth = _wilder_smooth(tr, period)
    plus_dm_smooth = _wilder_smooth(plus_dm, period)
    minus_dm_smooth = _wilder_smooth(minus_dm, period)

    safe_atr = atr_smooth.replace(0.0, np.nan)
    plus_di = (100.0 * (plus_dm_smooth / safe_atr)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    minus_di = (100.0 * (minus_dm_smooth / safe_atr)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    denom = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * ((plus_di - minus_di).abs() / denom)
    dx = dx.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    adx_series = _wilder_smooth(dx, period).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return adx_series, plus_di, minus_di


# =========================================================
# ATR (Average True Range — Wilder smoothing)
# =========================================================

def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Calcule l'Average True Range (ATR) avec le lissage de Wilder."""
    high_f = high.astype(float)
    low_f = low.astype(float)
    close_f = close.astype(float)

    tr1 = high_f - low_f
    tr2 = (high_f - close_f.shift(1)).abs()
    tr3 = (low_f - close_f.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return _wilder_smooth(tr, period).replace([np.inf, -np.inf], np.nan)


# =========================================================
# MACD
# =========================================================

def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calcule la ligne MACD, la ligne de signal et l'histogramme."""
    close_f = close.astype(float)
    ema_fast = close_f.ewm(span=fast, adjust=False).mean()
    ema_slow = close_f.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# =========================================================
# BOLLINGER BANDS
# =========================================================

def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calcule les Bandes de Bollinger (Upper, Mid/SMA, Lower)."""
    close_f = close.astype(float)
    sma_mid = close_f.rolling(window=period, min_periods=period).mean()
    rolling_std = close_f.rolling(window=period, min_periods=period).std()
    upper = sma_mid + (rolling_std * std)
    lower = sma_mid - (rolling_std * std)
    return upper, sma_mid, lower


# =========================================================
# SMA (Simple Moving Average)
# =========================================================

def sma(series: pd.Series, period: int) -> pd.Series:
    """Calcule la moyenne mobile simple sur `period` bougies."""
    return series.astype(float).rolling(window=period, min_periods=period).mean()


# =========================================================
# SUPPORT / RÉSISTANCE (Sans Lookahead Bias)
# =========================================================

def support_resistance(
    high: pd.Series,
    low: pd.Series,
    lookback: int = 50,
    use_closed_candle: bool = False,
) -> Tuple[Optional[float], Optional[float]]:
    """Calcule les niveaux de support et de résistance sur les `lookback` dernières bougies.

    Si `use_closed_candle=True`, exclut la bougie en cours de formation (`iloc[-1]`)
    afin d'éviter tout repainting intra-bougie.
    """
    h = closed_series(high, use_closed_candle=use_closed_candle)
    l = closed_series(low, use_closed_candle=use_closed_candle)

    if len(h) < lookback or len(l) < lookback:
        return None, None

    recent_high = h.iloc[-lookback:].dropna()
    recent_low = l.iloc[-lookback:].dropna()
    if recent_high.empty or recent_low.empty:
        return None, None

    sup_val = float(recent_low.min())
    res_val = float(recent_high.max())
    if np.isnan(sup_val) or np.isnan(res_val):
        return None, None
    return sup_val, res_val


# =========================================================
# DIVERGENCE RSI / PRIX (Sur bougies clôturées)
# =========================================================

def detect_divergence(
    close: pd.Series,
    rsi_series: pd.Series,
    lookback: int = 10,
    use_closed_candle: bool = False,
) -> Optional[str]:
    """Détecte une divergence haussière ou baissière entre le prix et le RSI."""
    c = closed_series(close, use_closed_candle=use_closed_candle).dropna()
    r = closed_series(rsi_series, use_closed_candle=use_closed_candle).dropna()

    if len(c) < lookback + 5 or len(r) < lookback + 5:
        return None

    price_prev = c.iloc[-lookback:-5]
    price_now = c.iloc[-5:]
    rsi_prev = r.iloc[-lookback:-5]
    rsi_now = r.iloc[-5:]

    if price_prev.empty or price_now.empty or rsi_prev.empty or rsi_now.empty:
        return None

    # Divergence baissière : plus haut sur le prix, plus bas sur le RSI
    if price_now.max() > price_prev.max() and rsi_now.max() < rsi_prev.max():
        return "bearish"

    # Divergence haussière : plus bas sur le prix, plus haut sur le RSI
    if price_now.min() < price_prev.min() and rsi_now.min() > rsi_prev.min():
        return "bullish"

    return None


# =========================================================
# FIBONACCI
# =========================================================

def fibonacci_levels(high: float, low: float) -> Dict[str, float]:
    """Calcule les niveaux de retracement de Fibonacci (38.2%, 50%, 61.8%)."""
    if pd.isna(high) or pd.isna(low) or high <= low:
        safe_low = 0.0 if pd.isna(low) else float(low)
        return {"0.382": safe_low, "0.500": safe_low, "0.618": safe_low}
    diff = float(high) - float(low)
    return {
        "0.382": round(float(high) - diff * 0.382, 5),
        "0.500": round(float(high) - diff * 0.500, 5),
        "0.618": round(float(high) - diff * 0.618, 5),
    }


# =========================================================
# HELPERS POUR SCALPING / TICKS
# =========================================================

def _to_series(values: Iterable[float]) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.astype(float)
    return pd.Series(list(values), dtype=float)


def rsi_from_ticks(ticks: Iterable[float], period: int = 14) -> pd.Series:
    return rsi(_to_series(ticks), period)


def macd_from_ticks(
    ticks: Iterable[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    return macd(_to_series(ticks), fast, slow, signal)
