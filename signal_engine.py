import pandas as pd
from typing import Dict, Optional, Tuple

from indicators import rsi, macd, sma, atr, adx, bollinger_bands, support_resistance
from config import (
    ATR_MULTIPLIER_SL, RR_RATIO_TARGET, SYMBOL_CONFIGS
)
from i18n import get_text
from decision_journal import SignalDecisionRecord, decision_journal, STRATEGY_VERSION


# =========================================================
# CONFIG STYLES DE TRADING (Calibrés par validation walk-forward Train 60% / Test OOS 40% :
# SL >= 1.35x-1.90x ATR pour éviter le bruit intra-bougie, RR cible = 2.10R)
# =========================================================

STYLE_CONFIG = {
    "scalping":     {"sl_mult": 1.35, "tp_mult": 2.84, "min_sl_pct": 0.0045},  # RR ~ 2.10
    "scalping_15m": {"sl_mult": 1.45, "tp_mult": 3.05, "min_sl_pct": 0.0055},  # RR ~ 2.10
    "day":          {"sl_mult": 1.60, "tp_mult": 3.36, "min_sl_pct": 0.0060},  # RR = 2.10
    "swing":        {"sl_mult": 1.90, "tp_mult": 3.99, "min_sl_pct": 0.0060},  # RR = 2.10
    "position":     {"sl_mult": 2.20, "tp_mult": 4.62, "min_sl_pct": 0.0080},  # RR = 2.10
}

# =========================================================
# SCORING
# =========================================================

SCORE_WEIGHTS = {
    "trend": 30,
    "rr":    25,
    "sr":    20,
    "adx":   15,
    "rsi":   10,
}

# Seuils de rejet unifiés par style (sans double addition de delta contradictoire)
REJECTION_THRESHOLDS = {
    "scalping":     {"min_score": 66, "min_adx": 22, "min_rr": 1.95},
    "scalping_15m": {"min_score": 66, "min_adx": 22, "min_rr": 2.00},
    "day":          {"min_score": 65, "min_adx": 22, "min_rr": 2.00},
    "swing":        {"min_score": 64, "min_adx": 22, "min_rr": 2.05},
    "position":     {"min_score": 64, "min_adx": 20, "min_rr": 2.10},
}

# Buffer S/R par style (multiplicateur de l'ATR)
BUFFER_MULTIPLIERS = {
    "scalping": 0.10,
    "scalping_15m": 0.12,
    "day":      0.15,
    "swing":    0.20,
    "position": 0.25,
}

ASSET_CLASS_RULES = {
    "crypto": {
        "symbols": {"BTCUSDT", "ETHUSDT"},
        "sl_factor": 1.00,
        "tp_factor": 1.00,
        "adx_delta": 0,
        "min_score_delta": 0,
        "min_rr_delta": 0.0,
        "pullback_pct": 0.025, # Entrée au plus près de la SMA20 (max 2.5% d'écart)
        "overextension_factor": 0.90, # Max 1.8x ATR sur 5 bougies en day
        "sr_buffer_factor": 1.15,
        "atr_min_pct": 0.0025, # Évite les marchés plats où les frais mangent le RR
        "min_sl_pct": 0.0060,  # Distance SL minimale (0.60% du prix) validée hors échantillon
    },
    "metal": {
        "symbols": {"XAUUSD"},
        "sl_factor": 1.00,
        "tp_factor": 1.00,
        "adx_delta": 0,
        "min_score_delta": 0,
        "min_rr_delta": 0.0,
        "pullback_pct": 0.025,
        "overextension_factor": 0.90,
        "sr_buffer_factor": 1.20,
        "atr_min_pct": 0.0015,
        "min_sl_pct": 0.0050,
    },
}

DEFAULT_ASSET_RULE = {
    "sl_factor": 1.00,
    "tp_factor": 1.00,
    "adx_delta": 0,
    "min_score_delta": 0,
    "min_rr_delta": 0.0,
    "pullback_pct": 0.025,
    "overextension_factor": 0.90,
    "sr_buffer_factor": 1.00,
    "atr_min_pct": 0.0020,
    "min_sl_pct": 0.0055,
}

TREND_BULLISH = "HAUSSIER"
TREND_BEARISH = "BAISSIER"
TREND_NEUTRAL = "NEUTRE"


class SignalEngine:

    @staticmethod
    def _asset_profile(symbol: str) -> Tuple[str, Dict]:
        symbol_clean = (symbol or "").upper().replace(" ", "").replace("/", "").replace("-", "")
        for asset_class, rules in ASSET_CLASS_RULES.items():
            if symbol_clean in rules["symbols"] or (symbol or "").upper() in rules["symbols"]:
                profile = DEFAULT_ASSET_RULE.copy()
                profile.update({k: v for k, v in rules.items() if k != "symbols"})
                return asset_class, profile
        return "generic", DEFAULT_ASSET_RULE.copy()

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        """Normalise les noms de colonnes en Capitalize (Open, High, Low, Close, Volume)."""
        rename = {}
        for c in df.columns:
            if c.lower() in ["open", "high", "low", "close", "volume"]:
                rename[c] = c.capitalize()
        return df.rename(columns=rename) if rename else df

    @staticmethod
    def _valid_df(df: pd.DataFrame, min_len: int = 60) -> bool:
        """Vérifie que le DataFrame est valide et suffisamment long."""
        required = {"Open", "High", "Low", "Close"}
        return (
            df is not None
            and not df.empty
            and required.issubset(df.columns)
            and len(df) >= min_len
        )

    @staticmethod
    def _clamp_score(score: float) -> int:
        score = max(0, min(100, score))
        return int(round(score))

    TIMEFRAME_RULE_MINUTES = {
        "1m": 1,
        "1min": 1,
        "5m": 5,
        "5min": 5,
        "15m": 15,
        "15min": 15,
        "1h": 60,
        "60m": 60,
        "60min": 60,
        "4h": 240,
        "240m": 240,
        "240min": 240,
        "1d": 1440,
        "1D": 1440,
        "1440m": 1440,
    }

    PANDAS_RESAMPLE_RULES = {
        5: "5min",
        15: "15min",
        60: "1h",
        240: "4h",
        1440: "1D",
    }

    @staticmethod
    def filter_closed_candles(
        df: Optional[pd.DataFrame],
        now: Optional[pd.Timestamp] = None,
        timeframe_minutes: Optional[float] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Retourne uniquement les bougies effectivement clôturées.
        - Respecte `df.attrs['last_candle_open']` / `df.attrs['has_open_candle']` si défini.
        - Respecte la colonne `is_closed` si présente.
        - Respecte la colonne `CloseTime` / `close_time` si présente.
        - Vérifie `OpenTime + timeframe <= now` sur un `DatetimeIndex` sans introduire
          de décalage sur des données historiques déjà clôturées.
        """
        if df is None or df.empty:
            return df

        out = df.copy()
        if isinstance(out.index, pd.DatetimeIndex) and not out.index.is_monotonic_increasing:
            out = out.sort_index()

        if df.attrs.get("last_candle_open") is True or df.attrs.get("has_open_candle") is True:
            if len(out) >= 1:
                out = out.iloc[:-1]
                out.attrs = dict(df.attrs)
                out.attrs["last_candle_open"] = False
                out.attrs["has_open_candle"] = False

        if "is_closed" in out.columns:
            out = out[out["is_closed"].astype(bool)]
            if out.empty:
                return out

        ref_ts = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")

        close_col = "CloseTime" if "CloseTime" in out.columns else ("close_time" if "close_time" in out.columns else None)
        if close_col is not None and not out.empty:
            raw_ct = out[close_col]
            if pd.api.types.is_numeric_dtype(raw_ct):
                med = float(raw_ct.dropna().median()) if not raw_ct.dropna().empty else 0.0
                unit = "ms" if med > 1e11 else "s"
                ct_series = pd.to_datetime(raw_ct, unit=unit, utc=True)
            else:
                ct_series = pd.to_datetime(raw_ct, utc=True)
            ref_utc = ref_ts.tz_localize("UTC") if ref_ts.tzinfo is None else ref_ts.tz_convert("UTC")
            out = out[ct_series <= ref_utc]
            if out.empty:
                return out

        if isinstance(out.index, pd.DatetimeIndex) and len(out.index) >= 2:
            tf_min = timeframe_minutes or SignalEngine._infer_timeframe_minutes(out)
            if tf_min is not None and tf_min > 0:
                if out.index.tz is None:
                    ref_cmp = ref_ts.tz_convert("UTC").tz_localize(None) if ref_ts.tzinfo is not None else ref_ts
                else:
                    ref_cmp = ref_ts.tz_localize(out.index.tz) if ref_ts.tzinfo is None else ref_ts.tz_convert(out.index.tz)
                candle_close_times = out.index + pd.Timedelta(minutes=float(tf_min))
                out = out[candle_close_times <= ref_cmp]

        return out

    @staticmethod
    def _detect_timeframe_trend(df: Optional[pd.DataFrame]) -> str:
        """Détecte la tendance avec la règle SMA20 / SMA50 (exige au moins 50 bougies clôturées)."""
        if df is None or not SignalEngine._valid_df(df, min_len=50):
            return TREND_NEUTRAL

        close = df["Close"]
        sma_fast_val = sma(close, 20).iloc[-1]
        sma_slow_val = sma(close, 50).iloc[-1]
        last_price = close.iloc[-1]

        if pd.isna(last_price) or pd.isna(sma_fast_val) or pd.isna(sma_slow_val):
            return TREND_NEUTRAL
        if last_price > sma_fast_val > sma_slow_val:
            return TREND_BULLISH
        if last_price < sma_fast_val < sma_slow_val:
            return TREND_BEARISH
        return TREND_NEUTRAL

    @staticmethod
    def _resample_ohlc(
        df: pd.DataFrame,
        rule: str,
        base_minutes: Optional[float] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Resample OHLCV vers le véritable timeframe demandé (`5min`, `15min`, `1h`, `4h`, `1D`).
        - Ne downsample jamais un timeframe supérieur vers un timeframe inférieur.
        - Respecte les frontières temporelles UTC (`closed='left', label='left'`).
        - Exclut toute bougie supérieure incomplète au début ou à la fin (zéro look-ahead).
        """
        if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
            return None

        work_df = df.sort_index() if not df.index.is_monotonic_increasing else df
        inferred_base = base_minutes or SignalEngine._infer_timeframe_minutes(work_df)
        target_minutes = SignalEngine.TIMEFRAME_RULE_MINUTES.get(rule)

        if inferred_base is not None and target_minutes is not None:
            if target_minutes < inferred_base - 1e-6:
                return None
            if abs(target_minutes - inferred_base) <= 1e-6:
                return work_df.copy()

        pandas_rule = SignalEngine.PANDAS_RESAMPLE_RULES.get(target_minutes, rule) if target_minutes else rule
        agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
        if "Volume" in work_df.columns:
            agg["Volume"] = "sum"

        resampled = (
            work_df.resample(pandas_rule, closed="left", label="left")
            .agg(agg)
            .dropna(subset=["Open", "High", "Low", "Close"])
        )
        if resampled.empty:
            return None

        if inferred_base is not None and inferred_base > 0 and target_minutes is not None:
            first_open_ts = work_df.index[0]
            last_close_ts = work_df.index[-1] + pd.Timedelta(minutes=float(inferred_base))
            target_delta = pd.Timedelta(minutes=float(target_minutes))
            expected_bars = max(1, int(round(float(target_minutes) / float(inferred_base))))
            counts = work_df["Close"].resample(pandas_rule, closed="left", label="left").count()
            counts = counts.reindex(resampled.index).fillna(0)
            valid_mask = (
                (resampled.index >= first_open_ts)
                & ((resampled.index + target_delta) <= last_close_ts)
                & (counts >= expected_bars)
            )
            resampled = resampled[valid_mask]

        return resampled if not resampled.empty else None

    @staticmethod
    def _infer_timeframe_minutes(df: pd.DataFrame) -> Optional[float]:
        if not isinstance(df.index, pd.DatetimeIndex) or len(df.index) < 2:
            return None

        deltas = df.index.to_series().diff().dropna().dt.total_seconds() / 60
        deltas = deltas[deltas > 0]
        if deltas.empty:
            return None
        return float(deltas.median())

    @staticmethod
    def _build_mtf_frames(
        df: pd.DataFrame,
        htf_data: Optional[Dict[str, pd.DataFrame]] = None,
        now: Optional[pd.Timestamp] = None,
    ) -> Dict[str, Optional[pd.DataFrame]]:
        """
        Construit les DataFrames multi-timeframes réels :
        - '5m'  est réellement 5m (5 minutes)
        - '15m' est réellement 15m (15 minutes)
        - '1h'  est réellement 1h (60 minutes)
        - '4h'  est réellement 4h (240 minutes)
        - '1d'  est réellement 1d (1440 minutes)
        Aucune série 5m/15m/1h n'est jamais renommée en '4h' ou '1d'.
        """
        frames: Dict[str, Optional[pd.DataFrame]] = {
            "5m": None,
            "15m": None,
            "1h": None,
            "4h": None,
            "1d": None,
        }
        if df is None or df.empty:
            return frames

        closed_df = SignalEngine.filter_closed_candles(df, now=now)
        if closed_df is None or closed_df.empty:
            return frames

        inferred_minutes = SignalEngine._infer_timeframe_minutes(closed_df)
        last_close_ts = None
        if isinstance(closed_df.index, pd.DatetimeIndex) and inferred_minutes is not None and len(closed_df.index) > 0:
            last_close_ts = closed_df.index[-1] + pd.Timedelta(minutes=float(inferred_minutes))

        specs = (
            ("5m", "5min", 5),
            ("15m", "15min", 15),
            ("1h", "1h", 60),
            ("4h", "4h", 240),
            ("1d", "1D", 1440),
        )

        for tf_key, rule, target_min in specs:
            ext_df = None
            if htf_data and tf_key in htf_data and htf_data[tf_key] is not None:
                ext_norm = SignalEngine._normalize_df(htf_data[tf_key])
                ext_closed = SignalEngine.filter_closed_candles(ext_norm, now=now, timeframe_minutes=float(target_min))
                if ext_closed is not None and not ext_closed.empty:
                    if last_close_ts is not None and isinstance(ext_closed.index, pd.DatetimeIndex):
                        if ext_closed.index.tz is None and last_close_ts.tzinfo is not None:
                            cutoff = last_close_ts.tz_convert("UTC").tz_localize(None)
                        elif ext_closed.index.tz is not None and last_close_ts.tzinfo is None:
                            cutoff = last_close_ts.tz_localize(ext_closed.index.tz)
                        else:
                            cutoff = last_close_ts
                        ext_closed = ext_closed[(ext_closed.index + pd.Timedelta(minutes=float(target_min))) <= cutoff]
                    if not ext_closed.empty:
                        ext_df = ext_closed

            if ext_df is not None:
                frames[tf_key] = ext_df
            elif inferred_minutes is not None and inferred_minutes <= target_min + 1e-6:
                frames[tf_key] = SignalEngine._resample_ohlc(closed_df, rule, base_minutes=inferred_minutes)

        return frames

    @staticmethod
    def _compute_timeframe_trends(
        df: pd.DataFrame,
        htf_data: Optional[Dict[str, pd.DataFrame]] = None,
        now: Optional[pd.Timestamp] = None,
    ) -> Dict[str, str]:
        """
        Calcule les tendances sur les véritables timeframes 1h, 4h et 1d.
        - '1h' représente exclusivement des bougies 1h clôturées.
        - '4h' représente exclusivement des bougies 4h clôturées.
        - '1d' représente exclusivement des bougies 1d clôturées.
        """
        inferred_minutes = SignalEngine._infer_timeframe_minutes(df)
        if inferred_minutes is None and not htf_data:
            return {
                "1h": SignalEngine._detect_timeframe_trend(df),
                "4h": TREND_NEUTRAL,
                "1d": TREND_NEUTRAL,
            }

        frames = SignalEngine._build_mtf_frames(df, htf_data=htf_data, now=now)
        return {
            "1h": SignalEngine._detect_timeframe_trend(frames["1h"]),
            "4h": SignalEngine._detect_timeframe_trend(frames["4h"]),
            "1d": SignalEngine._detect_timeframe_trend(frames["1d"]),
        }

    @staticmethod
    def check_tf_alignment(tf_1h, tf_4h, tf_1d):
        trends = [tf_1h, tf_4h, tf_1d]
        bullish_count = trends.count(TREND_BULLISH)
        bearish_count = trends.count(TREND_BEARISH)

        if bullish_count == 3:
            return {"status": "TOTAL", "direction": TREND_BULLISH, "modifier": 15}
        if bearish_count == 3:
            return {"status": "TOTAL", "direction": TREND_BEARISH, "modifier": 15}
        if bullish_count > 0 and bearish_count > 0:
            return {"status": "CONFLICT", "direction": TREND_NEUTRAL, "modifier": -15}
        if bullish_count == 2:
            return {"status": "PARTIAL", "direction": TREND_BULLISH, "modifier": 5}
        if bearish_count == 2:
            return {"status": "PARTIAL", "direction": TREND_BEARISH, "modifier": 5}
        return {"status": "NEUTRAL", "direction": TREND_NEUTRAL, "modifier": 0}

    @staticmethod
    def _apply_tf_alignment_score(score: int, signal: str, tf_alignment: Dict) -> Tuple[int, Dict]:
        alignment = (tf_alignment or {}).copy()
        modifier = int(alignment.get("modifier", 0))
        direction = alignment.get("direction", TREND_NEUTRAL)
        signal_direction = TREND_BULLISH if signal == "BUY" else TREND_BEARISH

        if modifier > 0 and direction != signal_direction:
            modifier = -15
            alignment["status"] = "CONFLICT"
            alignment["modifier"] = modifier

        return SignalEngine._clamp_score(score + modifier), alignment

    @staticmethod
    def _wait(
        lang: str,
        reason_key: str = "signal_insufficient_data",
        indicators: Optional[Dict] = None,
        score_detail: Optional[Dict] = None,
        score: int = 0,
        asset_class: str = "generic",
        params_used: Optional[Dict] = None,
    ) -> Dict:
        """
        Retourne un signal WAIT.

        - reason_key peut être une clé i18n (ex: "signal_insufficient_data")
          ou un texte lisible direct (ex: "RR too low for this style").
        - indicators est conservé pour que le graphique s'affiche même en cas de rejet.
        - score_detail est conservé pour la transparence.
        """
        # Distingue clé i18n vs texte brut
        _KNOWN_REASON_KEYS = {
            "signal_insufficient_data",
            "signal_wait_neutral",
        }
        if reason_key in _KNOWN_REASON_KEYS:
            reason_text = get_text(lang, reason_key)
        else:
            # Texte lisible direct (rejets de filtres)
            reason_text = reason_key

        return {
            "signal": "WAIT",
            "signal_text": get_text(lang, "signal_wait"),
            "reason": reason_text,
            "rejection_reason": reason_text,
            "risk_advice": "",
            "teddy_score": SignalEngine._clamp_score(score),
            "confidence": get_text(lang, "confidence_low"),
            "sl": None,
            "tp": None,
            "tp1": None,
            "tp2": None,
            "rr_ratio": None,
            "indicators": indicators or {},
            "score_detail": score_detail or {},
            "validation_status": "REJECTED",
            "asset_class": asset_class,
            "params_used": params_used or {},
        }

    @staticmethod
    def analyze(
        df: pd.DataFrame,
        lang: str = "en",
        symbol: str = "",
        style: str = "day",
        *,
        htf_data: Optional[Dict[str, pd.DataFrame]] = None,
        now: Optional[pd.Timestamp] = None,
        timeframe_minutes: Optional[float] = None,
    ) -> Dict:
        """
        Point d'entrée principal.

        Args:
            df:     DataFrame OHLC (minimum 60 bougies clôturées).
            lang:   Code langue ("en" ou "fr").
            symbol: Symbole (ex: "BTCUSDT", "ETHUSDT", "XAUUSD").
            style:  Style de trading ("scalping", "scalping_15m", "day", "swing", "position", ou None pour fallback config.py).
            htf_data: Dictionnaire optionnel de DataFrames de timeframes supérieurs {'1h': df_1h, '4h': df_4h, '1d': df_1d}.
            now:    Horodatage de référence pour exclure toute bougie non clôturée.
            timeframe_minutes: Durée en minutes d'une bougie de `df` (inférée automatiquement si absente).

        Returns:
            Dict contenant signal, SL, TP, teddy_score, indicators, score_detail, etc.
        """
        raw_symbol = symbol.upper()
        symbol_nospace = raw_symbol.replace(" ", "").replace("/", "").replace("-", "")
        from config import DOCUMENTED_SYMBOLS
        if symbol_nospace in DOCUMENTED_SYMBOLS:
            symbol = symbol_nospace
        elif raw_symbol in DOCUMENTED_SYMBOLS:
            symbol = raw_symbol
        elif raw_symbol:
            return SignalEngine._wait(lang, f"Symbole non documenté ({raw_symbol})")
        df = SignalEngine._normalize_df(df)
        df = SignalEngine.filter_closed_candles(df, now=now, timeframe_minutes=timeframe_minutes)

        if not SignalEngine._valid_df(df):
            return SignalEngine._wait(lang)

        asset_class, asset_rules = SignalEngine._asset_profile(symbol)
        cfg = SYMBOL_CONFIGS.get(symbol, SYMBOL_CONFIGS["BTCUSDT"]).copy()
        cfg["adx_min"] = max(1, int(cfg["adx_min"] + asset_rules["adx_delta"]))

        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]
        last_price = float(close.iloc[-1])

        # ── Indicateurs ────────────────────────────────────────────────────────
        sma20 = float(sma(close, 20).iloc[-1])
        sma50 = float(sma(close, 50).iloc[-1])

        rsi_val               = float(rsi(close, 14).iloc[-1])
        macd_line, macd_sig, hist = macd(close, 12, 26, 9)
        macd_val              = float(macd_line.iloc[-1])
        macd_sig_val          = float(macd_sig.iloc[-1])
        hist_val              = float(hist.iloc[-1])

        adx_series, plus_di_series, minus_di_series = adx(high, low, close, 14)
        adx_val  = float(adx_series.iloc[-1])
        adx_prev_val = float(adx_series.iloc[-2]) if len(adx_series) >= 2 and not pd.isna(adx_series.iloc[-2]) else adx_val
        plus_di_val  = float(plus_di_series.iloc[-1])
        minus_di_val = float(minus_di_series.iloc[-1])
        atr_val  = float(atr(high, low, close, 14).iloc[-1])

        upper_bb, _, lower_bb = bollinger_bands(close, 20, 2)
        upper_bb = float(upper_bb.iloc[-1])
        lower_bb = float(lower_bb.iloc[-1])

        atr_ratio = atr_val / last_price if last_price else 0

        # Volume
        volume_series = df["Volume"] if "Volume" in df.columns else None
        volume_val = float(volume_series.iloc[-1]) if volume_series is not None and len(volume_series) > 0 else None
        volume_ma20_val = float(sma(volume_series, 20).iloc[-1]) if volume_series is not None and len(volume_series) >= 20 else None

        # ── Support / Résistance (peut retourner None) ─────────────────────────
        sr_result = support_resistance(high, low, 50)
        if sr_result is not None:
            support, resistance = sr_result
        else:
            support, resistance = None, None

        # ── Tendances ──────────────────────────────────────────────────────────
        trend_bull = last_price > sma20 > sma50
        trend_bear = last_price < sma20 < sma50
        timeframe_trends = SignalEngine._compute_timeframe_trends(df, htf_data=htf_data, now=now)
        tf_alignment = SignalEngine.check_tf_alignment(
            timeframe_trends["1h"],
            timeframe_trends["4h"],
            timeframe_trends["1d"],
        )

        # ── Conditions de signal (seuils config.py intacts) ───────────────────
        buy_cond = [
            trend_bull,
            cfg["rsi_buy_low"] <= rsi_val <= cfg["rsi_buy_high"],
            macd_val > macd_sig_val and hist_val > 0,
            adx_val >= cfg["adx_min"],
            atr_ratio <= cfg["atr_max_pct"] / 100,
        ]

        sell_cond = [
            trend_bear,
            cfg["rsi_sell_low"] <= rsi_val <= cfg["rsi_sell_high"],
            macd_val < macd_sig_val and hist_val < 0,
            adx_val >= cfg["adx_min"],
            atr_ratio <= cfg["atr_max_pct"] / 100,
        ]

        # ── Indicators dict (toujours rempli pour le graphique) ───────────────
        indicators = {
            "close_vals": list(close.iloc[-6:]),
            "price":      last_price,
            "rsi":        rsi_val,
            "adx":        adx_val,
            "adx_prev":   adx_prev_val,
            "adx_rising": adx_val > adx_prev_val,
            "sma20":      sma20,
            "sma50":      sma50,
            "atr":        atr_val,
            "plus_di":    plus_di_val,
            "minus_di":   minus_di_val,
            "macd":       macd_val,
            "macd_signal": macd_sig_val,
            "macd_hist":  hist_val,
            "volume":     volume_val,
            "volume_ma20": volume_ma20_val,
            "bb_upper":   upper_bb,
            "bb_lower":   lower_bb,
            "support":    support,
            "resistance": resistance,
            "timeframe_trends": timeframe_trends,
            "tf_alignment": tf_alignment,
            "last_timestamp": str(df.index[-1]) if isinstance(df.index, pd.DatetimeIndex) and len(df.index) > 0 else "",
        }

        return SignalEngine._finalize(
            buy_cond=buy_cond,
            sell_cond=sell_cond,
            price=last_price,
            atr_val=atr_val,
            indicators=indicators,
            lang=lang,
            min_cond=cfg["min_cond"],
            cfg=cfg,
            support=support,
            resistance=resistance,
            rsi_val=rsi_val,
            adx_val=adx_val,
            trend_bull=trend_bull,
            trend_bear=trend_bear,
            style=style,
            symbol=symbol,
            asset_class=asset_class,
            asset_rules=asset_rules,
            tf_alignment=tf_alignment,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTHODES INTERNES
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_sl_tp(
        signal: str,
        price: float,
        atr_val: float,
        style: Optional[str],
        asset_rules: Optional[Dict] = None,
    ) -> Tuple[float, float]:
        """
        Calcule SL et TP bruts selon le style de trading.

        Fallback : ATR_MULTIPLIER_SL / RR_RATIO_TARGET (config.py) si style=None.
        """
        if style and style in STYLE_CONFIG:
            sl_mult = STYLE_CONFIG[style]["sl_mult"]
            tp_mult = STYLE_CONFIG[style]["tp_mult"]
        else:
            sl_mult = ATR_MULTIPLIER_SL
            tp_mult = RR_RATIO_TARGET

        asset_rules = asset_rules or DEFAULT_ASSET_RULE
        sl_mult *= asset_rules.get("sl_factor", 1.0)
        tp_mult *= asset_rules.get("tp_factor", 1.0)

        if signal == "BUY":
            sl  = price - sl_mult * atr_val
            tp1 = price + tp_mult * atr_val
        else:  # SELL
            sl  = price + sl_mult * atr_val
            tp1 = price - tp_mult * atr_val

        return sl, tp1

    @staticmethod
    def _adjust_sl_tp_with_sr(
        signal: str,
        price: float,
        sl: float,
        tp1: float,
        atr_val: float,
        support: Optional[float],
        resistance: Optional[float],
        style: Optional[str],
        min_rr: float = 1.0,
        asset_rules: Optional[Dict] = None,
    ) -> Tuple[float, float]:
        """
        Ajuste SL et TP en fonction des niveaux Support/Résistance.

        Guard : ne dégrade jamais le RR en dessous de min_rr.
        Si l'ajustement casse le RR, retourne les valeurs ATR brutes.
        """
        if support is None and resistance is None:
            return sl, tp1

        # Validation des niveaux S/R : ignorer si trop proches du prix
        min_dist = 0.5 * atr_val
        if support is not None and abs(price - support) < min_dist:
            support = None
        if resistance is not None and abs(price - resistance) < min_dist:
            resistance = None

        asset_rules = asset_rules or DEFAULT_ASSET_RULE
        buffer_base = BUFFER_MULTIPLIERS.get(style, 0.20) if style else 0.20
        buffer = buffer_base * asset_rules.get("sr_buffer_factor", 1.0) * atr_val

        new_sl, new_tp1 = sl, tp1

        if signal == "BUY":
            wider_sl = support - buffer if support is not None and support < price else None
            if wider_sl is not None and wider_sl < sl:
                new_sl = wider_sl
            if resistance is not None and price < resistance < tp1:
                new_tp1 = resistance - buffer

        elif signal == "SELL":
            wider_sl = resistance + buffer if resistance is not None and resistance > price else None
            if wider_sl is not None and wider_sl > sl:
                new_sl = wider_sl
            if support is not None and tp1 < support < price:
                new_tp1 = support + buffer

        # Guard : ne pas dégrader le RR en dessous du seuil
        sl_dist = abs(price - new_sl)
        tp_dist = abs(price - new_tp1)

        if sl_dist > 0:
            new_rr = tp_dist / sl_dist
            if new_rr < min_rr:
                return sl, tp1  # garder les valeurs ATR brutes

        # Sanity check directionnel
        if signal == "BUY" and (new_sl >= price or new_tp1 <= price):
            return sl, tp1
        if signal == "SELL" and (new_sl <= price or new_tp1 >= price):
            return sl, tp1

        return new_sl, new_tp1

    @staticmethod
    def _compute_score(
        signal: str,
        price: float,
        tp1: float,
        rr: Optional[float],
        adx_val: float,
        rsi_val: float,
        trend_bull: bool,
        trend_bear: bool,
        support: Optional[float],
        resistance: Optional[float],
        style: Optional[str],
        indicators: Dict,
    ) -> Tuple[int, Dict]:
        """Nouveau scoring V3 — 8 critères sur 100 points."""
        detail = {"trend": 0, "pullback": 0, "momentum": 0, "adx": 0, "rr": 0, "rsi": 0, "sr": 0, "volume": 0}
        
        if signal == "WAIT":
            return 0, detail

        def clamp(x, low=0.0, high=1.0):
            return max(low, min(high, x))

        close = price
        sma20 = indicators.get("sma20")
        sma50 = indicators.get("sma50")
        bb_mid = indicators.get("bb_mid", (indicators.get("bb_upper", 0) + indicators.get("bb_lower", 0)) / 2 if indicators.get("bb_upper") and indicators.get("bb_lower") else None)
        plus_di = indicators.get("plus_di")
        minus_di = indicators.get("minus_di")
        macd_val = indicators.get("macd")
        macd_sig = indicators.get("macd_signal")
        macd_hist = indicators.get("macd_hist")
        volume = indicators.get("volume")
        volume_ma20 = indicators.get("volume_ma20")

        # ── 1) Trend + Pullback (max 25) ────────────────────────
        trend_score = 0
        if close is not None and sma20 is not None and sma50 is not None:
            sma_aligned = (signal == "BUY" and sma20 > sma50) or (signal == "SELL" and sma20 < sma50)
            price_aligned = (signal == "BUY" and close > sma20) or (signal == "SELL" and close < sma20)
            trend_score = 15 if sma_aligned and price_aligned else (10 if sma_aligned else 5)

        pullback_score = 0
        if close is not None and sma20 is not None and close > 0:
            dist_pct = abs(close - sma20) / close * 100
            if dist_pct <= 0.25:
                pullback_score = 10
            elif dist_pct <= 0.50:
                pullback_score = 8
            elif dist_pct <= 1.00:
                pullback_score = 5
            elif dist_pct <= 1.50:
                pullback_score = 2

        # ── 2) Momentum MACD (max 20) ───────────────────────────
        momentum_score = 0
        if macd_hist is not None:
            hist_ok = (signal == "BUY" and macd_hist > 0) or (signal == "SELL" and macd_hist < 0)
            if macd_val is not None and macd_sig is not None:
                line_ok = (signal == "BUY" and macd_val > macd_sig) or (signal == "SELL" and macd_val < macd_sig)
            else:
                line_ok = hist_ok
            if line_ok:
                momentum_score += 12
            if hist_ok:
                momentum_score += 8

        # ── 3) ADX directionnel (max 15) ────────────────────────
        adx_score = 0
        if adx_val is not None and plus_di is not None and minus_di is not None:
            dir_ok = (signal == "BUY" and plus_di > minus_di) or (signal == "SELL" and minus_di > plus_di)
            if dir_ok:
                adx_score = 5 if adx_val >= 25 else (3 if adx_val >= 20 else 0)
                di_gap = abs(plus_di - minus_di)
                adx_score += 5 if di_gap > 10 else (3 if di_gap > 5 else 0)
                adx_score += 5 if adx_val >= 35 else 0

        # ── 4) RSI directionnel (max 10) ────────────────────────
        rsi_score = 0
        if rsi_val is not None:
            if signal == "BUY":
                if 50 < rsi_val <= 65:
                    rsi_score = 10
                elif 40 < rsi_val <= 50:
                    rsi_score = 5
                elif 65 < rsi_val <= 75:
                    rsi_score = 3
            else:
                if 35 <= rsi_val < 50:
                    rsi_score = 10
                elif 50 <= rsi_val < 60:
                    rsi_score = 5
                elif 25 <= rsi_val < 35:
                    rsi_score = 3

        # ── 5) RR (max 10) ─────────────────────────────────────
        rr_score = 0
        if rr is not None:
            if rr >= 3.0:
                rr_score = 10
            elif rr >= 2.0:
                rr_score = 7
            elif rr >= 1.5:
                rr_score = 4

        # ── 6) S/R (max 15) ────────────────────────────────────
        sr_score = 0
        relevant = support if signal == "BUY" else resistance
        if relevant is not None and close is not None and close > 0:
            dist_pct = abs(close - relevant) / close * 100
            side_ok = (signal == "BUY" and relevant <= close) or (signal == "SELL" and relevant >= close)
            if dist_pct <= 1.0 and side_ok:
                sr_score = 15
            elif dist_pct <= 2.0 and side_ok:
                sr_score = 10
            elif dist_pct <= 3.0:
                sr_score = 5

        # ── 7) Volume bonus (max 5) ────────────────────────────
        volume_score = 0
        if volume is not None and volume_ma20 is not None and volume_ma20 > 0:
            vr = volume / volume_ma20
            if vr >= 1.5:
                volume_score = 5
            elif vr >= 1.2:
                volume_score = 3

        total = trend_score + pullback_score + momentum_score + adx_score + rr_score + rsi_score + sr_score + volume_score
        total = SignalEngine._clamp_score(total)
        detail = {"trend": trend_score, "pullback": pullback_score, "momentum": momentum_score, "adx": adx_score, "rr": rr_score, "rsi": rsi_score, "sr": sr_score, "volume": volume_score}

        return total, detail

    @staticmethod
    def _finalize(
        buy_cond: list,
        sell_cond: list,
        price: float,
        atr_val: float,
        indicators: Dict,
        lang: str,
        min_cond: int = 4,
        cfg: Optional[Dict] = None,
        support: Optional[float] = None,
        resistance: Optional[float] = None,
        rsi_val: float = 50,
        adx_val: float = 20,
        trend_bull: bool = False,
        trend_bear: bool = False,
        style: Optional[str] = "day",
        symbol: str = "",
        asset_class: str = "generic",
        asset_rules: Optional[Dict] = None,
        tf_alignment: Optional[Dict] = None,
    ) -> Dict:
        """
        Finalise le signal : SL/TP, scoring pondéré, filtres de rejet.

        Toutes les étapes sont indépendantes et testables séparément.
        """
        asset_rules = asset_rules or DEFAULT_ASSET_RULE
        buy_count  = sum(buy_cond)
        sell_count = sum(sell_cond)
        params_used = {
            "style": style or "default",
            "asset_class": asset_class,
            "sl_factor": asset_rules.get("sl_factor", 1.0),
            "tp_factor": asset_rules.get("tp_factor", 1.0),
            "adx_min": cfg.get("adx_min") if cfg else None,
            "min_cond": min_cond,
            "pullback_pct": asset_rules.get("pullback_pct"),
        }

        # ── 1. Détermination du signal brut ───────────────────────────────────
        signal = "WAIT"
        if buy_count >= min_cond:
            signal = "BUY"
        elif sell_count >= min_cond:
            signal = "SELL"

        plus_di_val = indicators.get("plus_di", 0.0)
        minus_di_val = indicators.get("minus_di", 0.0)
        adx_prev_val = indicators.get("adx_prev", adx_val)
        adx_rising = bool(indicators.get("adx_rising", True))
        timeframe_trends = indicators.get("timeframe_trends", {})
        sma20 = indicators.get("sma20") or 0.0
        sma50 = indicators.get("sma50") or 0.0
        vol_val = indicators.get("volume")
        vol_ma20 = indicators.get("volume_ma20")
        vol_ratio = (vol_val / vol_ma20) if (vol_val and vol_ma20 and vol_ma20 > 0) else 1.0
        pb_dist_pct = abs(price - sma20) / sma20 * 100.0 if sma20 > 0 else 0.0
        close_vals = indicators.get("close_vals", [])
        ext_atr = abs(price - close_vals[-6]) / atr_val if (len(close_vals) >= 6 and atr_val > 0) else 0.0

        cond_names = ["trend_sma", "rsi_window", "macd_momentum", "adx_min", "atr_max"]
        active_conds = buy_cond if buy_count >= sell_count else sell_cond
        raw_cond_map = {
            cond_names[idx]: bool(active_conds[idx])
            for idx in range(min(len(cond_names), len(active_conds)))
        }
        filters_passed = []
        filters_failed = []

        def _log_and_wait(stage: str, reason_str: str, sc_init: float = 0.0, sc_final: int = 0, sc_thresh: int = 0, sl_v=None, tp_v=None, rr_v=None, sc_det=None):
            rec = SignalDecisionRecord(
                symbol=symbol or "UNKNOWN",
                direction=signal,
                timestamp=indicators.get("last_timestamp") or "",
                timeframe=style or "day",
                style=style or "day",
                strategy_version=STRATEGY_VERSION,
                raw_conditions=raw_cond_map,
                conditions_passed_count=max(buy_count, sell_count),
                min_cond_required=min_cond,
                score_initial=sc_init,
                score_components=sc_det or {},
                score_modifiers={"multi_timeframe": (tf_alignment or {}).get("modifier", 0)},
                score_final=sc_final,
                score_threshold=sc_thresh,
                rsi=rsi_val,
                macd=indicators.get("macd", 0.0) or 0.0,
                macd_signal=indicators.get("macd_signal", 0.0) or 0.0,
                macd_hist=indicators.get("macd_hist", 0.0) or 0.0,
                adx=adx_val,
                adx_prev=adx_prev_val,
                adx_rising=adx_rising,
                plus_di=plus_di_val or 0.0,
                minus_di=minus_di_val or 0.0,
                atr=atr_val,
                atr_pct=(atr_val / price * 100.0) if price > 0 else 0.0,
                price=price,
                sma20=sma20,
                sma50=sma50,
                trend=TREND_BULLISH if trend_bull else (TREND_BEARISH if trend_bear else TREND_NEUTRAL),
                support=support,
                resistance=resistance,
                volume_ratio=vol_ratio,
                pullback_pct=pb_dist_pct,
                extension_atr=ext_atr,
                mtf_alignment=timeframe_trends,
                sl=sl_v,
                tp=tp_v,
                sl_distance_pct=(abs(price - sl_v) / price * 100.0) if (sl_v and price > 0) else 0.0,
                rr_ratio=rr_v or 0.0,
                filters_passed=list(filters_passed),
                filters_failed=list(filters_failed),
                rejection_stage=stage,
                rejection_reason=reason_str,
                final_decision="WAIT" if stage == "CONDITIONS" else "REJECT",
            )
            decision_journal.record(rec, persist=False)
            out = SignalEngine._wait(
                lang,
                reason_key=reason_str,
                indicators=indicators,
                score_detail=sc_det or {},
                score=sc_final,
                asset_class=asset_class,
                params_used=params_used,
            )
            out["decision_record"] = rec.to_dict()
            return out

        # Signal WAIT direct (pas assez de conditions)
        if signal == "WAIT":
            filters_failed.append("min_cond")
            return _log_and_wait("CONDITIONS", "signal_wait_neutral")
        filters_passed.append("min_cond")

        # ── 1.2 Confirmation directionnelle obligatoire (Trend SMA + DI) ──────
        if signal == "BUY" and not (trend_bull and plus_di_val > minus_di_val):
            filters_failed.append("directional_trend_di")
            return _log_and_wait("SIGNAL_FILTER", "Trend/DI mismatch for BUY (requires Close > SMA20 > SMA50 and +DI > -DI)")
        if signal == "SELL" and not (trend_bear and minus_di_val > plus_di_val):
            filters_failed.append("directional_trend_di")
            return _log_and_wait("SIGNAL_FILTER", "Trend/DI mismatch for SELL (requires Close < SMA20 < SMA50 and -DI > +DI)")
        filters_passed.append("directional_trend_di")

        # ── 1.3 Filtre ADX croissant (évite l'essoufflement de tendance) ──────
        if not adx_rising and adx_val < 35.0:
            filters_failed.append("adx_rising")
            return _log_and_wait("SIGNAL_FILTER", f"Trend momentum exhausting — ADX {adx_val:.1f} <= prev {adx_prev_val:.1f}")
        filters_passed.append("adx_rising")

        # ── 1.5 Filtre régime ATR minimal (marché trop plat) ────────────────────
        atr_min_pct = asset_rules.get("atr_min_pct", 0.0)
        if atr_min_pct > 0 and price > 0:
            atr_ratio_now = atr_val / price
            if atr_ratio_now < atr_min_pct:
                filters_failed.append("atr_min_pct")
                return _log_and_wait(
                    "SIGNAL_FILTER",
                    f"Market too flat — ATR {atr_ratio_now*100:.3f}% < {atr_min_pct*100:.3f}% min",
                )
        filters_passed.append("atr_min_pct")

        # ── 1.6 Filtre MTF : alignement 4h obligatoire & non-opposition 1d ────
        tf_4h = timeframe_trends.get("4h", TREND_NEUTRAL)
        tf_1d = timeframe_trends.get("1d", TREND_NEUTRAL)
        if signal == "BUY":
            if tf_4h == TREND_BEARISH or tf_1d == TREND_BEARISH:
                filters_failed.append("mtf_contra_block")
                return _log_and_wait("SIGNAL_FILTER", f"MTF hard block — 4h={tf_4h} 1d={tf_1d} contra BUY")
            if tf_4h != TREND_NEUTRAL and tf_4h != TREND_BULLISH:
                filters_failed.append("mtf_4h_alignment")
                return _log_and_wait("SIGNAL_FILTER", f"MTF 4h not aligned ({tf_4h}) for BUY")
        elif signal == "SELL":
            if tf_4h == TREND_BULLISH or tf_1d == TREND_BULLISH:
                filters_failed.append("mtf_contra_block")
                return _log_and_wait("SIGNAL_FILTER", f"MTF hard block — 4h={tf_4h} 1d={tf_1d} contra SELL")
            if tf_4h != TREND_NEUTRAL and tf_4h != TREND_BEARISH:
                filters_failed.append("mtf_4h_alignment")
                return _log_and_wait("SIGNAL_FILTER", f"MTF 4h not aligned ({tf_4h}) for SELL")
        filters_passed.append("mtf_alignment")

        # ── 1.7 Filtre de sur-extension (anti-chasing) ─────────────────────
        if signal in ("BUY", "SELL") and atr_val > 0:
            if len(close_vals) >= 6:
                close_5_ago = close_vals[-6]
                recent_move = (price - close_5_ago) / atr_val
                thresholds_ext = {"scalping": 1.4, "scalping_15m": 1.6, "day": 2.0, "swing": 2.4, "position": 3.0}
                limit = thresholds_ext.get(style, 2.0) * asset_rules.get("overextension_factor", 0.90)
                if signal == "BUY" and recent_move > limit:
                    filters_failed.append("anti_chasing_extension")
                    return _log_and_wait(
                        "SIGNAL_FILTER",
                        f"Entry too late — price already moved up {recent_move:.1f}xATR (max {limit:.2f})",
                    )
                if signal == "SELL" and recent_move < -limit:
                    filters_failed.append("anti_chasing_extension")
                    return _log_and_wait(
                        "SIGNAL_FILTER",
                        f"Entry too late — price already moved down {abs(recent_move):.1f}xATR (max {limit:.2f})",
                    )
        filters_passed.append("anti_chasing_extension")

        # ── 1.8 Pullback filter souple (par symbole) ──────────────────────
        bb_upper = indicators.get("bb_upper")
        bb_lower = indicators.get("bb_lower")
        if signal in ("BUY", "SELL") and sma20 is not None and sma20 > 0:
            pullback_pct = asset_rules.get("pullback_pct", 0.025)
            if signal == "BUY":
                if price > sma20 * (1 + pullback_pct) or (bb_upper is not None and price > bb_upper):
                    filters_failed.append("pullback_sma20_bb")
                    return _log_and_wait("SIGNAL_FILTER", "Price extended, wait for pullback")
            if signal == "SELL":
                if price < sma20 * (1 - pullback_pct) or (bb_lower is not None and price < bb_lower):
                    filters_failed.append("pullback_sma20_bb")
                    return _log_and_wait("SIGNAL_FILTER", "Price extended, wait for pullback")
        filters_passed.append("pullback_sma20_bb")

        # ── 2. Calcul SL/TP selon le style ────────────────────────────────────
        sl, tp1 = SignalEngine._compute_sl_tp(signal, price, atr_val, style, asset_rules)

        # ── 2.5 Filtre distance SL minimale (anti-bruit / anti-frais) ─────────
        style_min_sl = STYLE_CONFIG.get(style or "day", {}).get("min_sl_pct", 0.0055)
        min_sl_pct = max(style_min_sl, asset_rules.get("min_sl_pct", 0.0050))
        if price > 0 and abs(price - sl) / price < min_sl_pct:
            filters_failed.append("min_sl_distance")
            return _log_and_wait(
                "SIGNAL_FILTER",
                f"Stop-Loss too tight ({abs(price - sl)/price*100:.2f}% < {min_sl_pct*100:.2f}% min) — high fee/noise risk",
                sl_v=sl, tp_v=tp1,
            )
        filters_passed.append("min_sl_distance")

        # ── 3. Ajustement S/R ─────────────────────────────────────────────────
        if atr_val > 0:
            sl, tp1 = SignalEngine._adjust_sl_tp_with_sr(
                signal, price, sl, tp1, atr_val, support, resistance, style,
                min_rr=REJECTION_THRESHOLDS.get(style or "day", REJECTION_THRESHOLDS["day"])["min_rr"],
                asset_rules=asset_rules,
            )

        tp  = tp1
        tp2 = tp1 + (atr_val if signal == "BUY" else -atr_val)

        # ── 4. Ratio RR ───────────────────────────────────────────────────────
        rr: Optional[float] = None
        if sl is not None and tp1 is not None and abs(price - sl) > 0:
            rr = round(abs(tp1 - price) / abs(price - sl), 2)

        # ── 5. Score pondéré ─────────────────────────────────────────────────
        initial_score, score_detail = SignalEngine._compute_score(
            signal=signal,
            price=price,
            tp1=tp1,
            rr=rr,
            adx_val=adx_val,
            rsi_val=rsi_val,
            trend_bull=trend_bull,
            trend_bear=trend_bear,
            support=support,
            resistance=resistance,
            style=style,
            indicators=indicators,
        )
        total_score, tf_alignment = SignalEngine._apply_tf_alignment_score(
            initial_score,
            signal,
            tf_alignment or indicators.get("tf_alignment", {}),
        )
        score_detail["multi_timeframe"] = tf_alignment.get("modifier", 0)
        score_detail["timeframe_alignment"] = tf_alignment.get("status", "NEUTRAL")

        # ── 6. Filtres de rejet (retourne WAIT avec indicateurs conservés) ────
        base_thresholds = REJECTION_THRESHOLDS.get(style or "day", REJECTION_THRESHOLDS["day"])
        thresholds = {
            "min_score": base_thresholds["min_score"] + asset_rules.get("min_score_delta", 0),
            "min_adx": base_thresholds["min_adx"] + asset_rules.get("adx_delta", 0),
            "min_rr": base_thresholds["min_rr"] + asset_rules.get("min_rr_delta", 0.0),
        }
        params_used.update(thresholds)

        if adx_val < thresholds["min_adx"]:
            filters_failed.append("min_adx")
            return _log_and_wait(
                "SCORE_FILTER",
                f"Trend too weak — ADX {adx_val:.1f} < {thresholds['min_adx']}",
                sc_init=initial_score, sc_final=total_score, sc_thresh=thresholds["min_score"],
                sl_v=sl, tp_v=tp, rr_v=rr, sc_det=score_detail,
            )
        filters_passed.append("min_adx")

        if rr is not None and rr < thresholds["min_rr"]:
            filters_failed.append("min_rr")
            return _log_and_wait(
                "SCORE_FILTER",
                f"RR too low — {rr:.2f} < {thresholds['min_rr']} required for {style or 'default'} style",
                sc_init=initial_score, sc_final=total_score, sc_thresh=thresholds["min_score"],
                sl_v=sl, tp_v=tp, rr_v=rr, sc_det=score_detail,
            )
        filters_passed.append("min_rr")

        if total_score < thresholds["min_score"]:
            filters_failed.append("min_score")
            return _log_and_wait(
                "SCORE_FILTER",
                f"Score too low — {total_score}/100 < {thresholds['min_score']} required",
                sc_init=initial_score, sc_final=total_score, sc_thresh=thresholds["min_score"],
                sl_v=sl, tp_v=tp, rr_v=rr, sc_det=score_detail,
            )
        filters_passed.append("min_score")

        # ── 7. Textes i18n ────────────────────────────────────────────────────
        reason   = get_text(lang, f"signal_{signal.lower()}_reason")
        risk     = get_text(lang, f"signal_{signal.lower()}_advice")
        conf_key = (
            "confidence_high"   if total_score >= 75 else
            "confidence_medium" if total_score >= 55 else
            "confidence_low"
        )

        rec = SignalDecisionRecord(
            symbol=symbol or "UNKNOWN",
            direction=signal,
            timestamp=indicators.get("last_timestamp") or "",
            timeframe=style or "day",
            style=style or "day",
            strategy_version=STRATEGY_VERSION,
            raw_conditions=raw_cond_map,
            conditions_passed_count=max(buy_count, sell_count),
            min_cond_required=min_cond,
            score_initial=initial_score,
            score_components=score_detail,
            score_modifiers={"multi_timeframe": tf_alignment.get("modifier", 0)},
            score_final=SignalEngine._clamp_score(total_score),
            score_threshold=thresholds["min_score"],
            rsi=rsi_val,
            macd=indicators.get("macd", 0.0) or 0.0,
            macd_signal=indicators.get("macd_signal", 0.0) or 0.0,
            macd_hist=indicators.get("macd_hist", 0.0) or 0.0,
            adx=adx_val,
            adx_prev=adx_prev_val,
            adx_rising=adx_rising,
            plus_di=plus_di_val or 0.0,
            minus_di=minus_di_val or 0.0,
            atr=atr_val,
            atr_pct=(atr_val / price * 100.0) if price > 0 else 0.0,
            price=price,
            sma20=sma20,
            sma50=sma50,
            trend=TREND_BULLISH if trend_bull else (TREND_BEARISH if trend_bear else TREND_NEUTRAL),
            support=support,
            resistance=resistance,
            volume_ratio=vol_ratio,
            pullback_pct=pb_dist_pct,
            extension_atr=ext_atr,
            mtf_alignment=timeframe_trends,
            sl=sl,
            tp=tp,
            sl_distance_pct=(abs(price - sl) / price * 100.0) if (sl and price > 0) else 0.0,
            rr_ratio=rr or 0.0,
            filters_passed=filters_passed,
            filters_failed=filters_failed,
            rejection_stage=None,
            rejection_reason=None,
            final_decision=signal,
        )
        decision_journal.record(rec, persist=True)

        # ── 8. Retour final ───────────────────────────────────────────────────
        return {
            "signal":      signal,
            "signal_text": get_text(lang, f"signal_{signal.lower()}"),
            "reason":      reason,
            "risk_advice": risk,
            "teddy_score": SignalEngine._clamp_score(total_score),
            "confidence":  get_text(lang, conf_key),
            "sl":          sl,
            "tp":          tp,
            "tp1":         tp1,
            "tp2":         tp2,
            "rr_ratio":    rr,
            "indicators":  indicators,
            "score_detail": score_detail,
            "validation_status": "VALIDATED",
            "rejection_reason": None,
            "asset_class": asset_class,
            "params_used": params_used,
            "decision_record": rec.to_dict(),
        }
