"""
web_api_server.py
-----------------
HTTP JSON bridge server exposing the full Bitsure Teddy v2.0 Python domain engine
to the Node.js / React application on localhost:8001.

All market intelligence, signal scoring, risk sizing, paper trading, live trading
execution, safety state machine, alerts, user roles, payments, and admin diagnostics
are executed directly by the repository's native Python modules.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

# Ensure sitecustomize is loaded
import sitecustomize  # noqa: F401

from alert_manager import AlertManager
from binance_manager import (
    get_account_balance,
    get_klines_dataframe,
    test_connection,
)
from bot_command_catalog import ADMIN_COMMAND_CATEGORIES, USER_COMMAND_CATEGORIES
from config import (
    ADMIN_ID,
    BINANCE_ID,
    DOCUMENTED_SYMBOLS,
    FREE_DAILY_REQUESTS,
    PAPER_DEFAULT_CAPITAL,
    SYMBOL_CONFIGS,
    TRIAL_DAYS,
)
from payments import generate_binance_payment

PLAN_PRICES_USDT = {"pro": 19, "vip": 49}
PLAN_PRICES_STARS = {"pro": 1000, "vip": 2500}
PROMO_CODES = {"TEDDYPRO": "pro", "TEDDYVIP": "vip", "WELCOME": "tester"}
from data_fetcher import DataFetcher
from database import get_connection, get_db
from decision_journal import decision_journal
import health_monitor
from history_manager import HistoryManager
from i18n import get_text
from indicators import adx, atr, bollinger_bands, macd, rsi, sma, support_resistance
import log_doctor
import market_hours
from paper_trader import PaperTrader
import position_manager
import risk_manager
import security_manager
from signal_engine import ASSET_CLASS_RULES, BUFFER_MULTIPLIERS, REJECTION_THRESHOLDS, STYLE_CONFIG, SignalEngine
import trading_config
import trading_safety
from user_manager import UserManager
from utils import format_number, normalize_symbol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("web_api_server")
log_doctor.install_log_buffer()

# =====================================================================
# WEB EXTENSION TABLES (Sessions, Credentials, Support Tickets, Notifications)
# =====================================================================

def _init_web_schema_and_seed():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS web_accounts (
            email TEXT PRIMARY KEY,
            user_id BIGINT UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            telegram_handle TEXT,
            created_at DOUBLE PRECISION DEFAULT 0
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS web_sessions (
            token TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            email TEXT,
            created_at DOUBLE PRECISION DEFAULT 0,
            expires_at DOUBLE PRECISION DEFAULT 0
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username TEXT,
            subject TEXT,
            message TEXT NOT NULL,
            admin_reply TEXT,
            status TEXT DEFAULT 'open',
            created_at DOUBLE PRECISION DEFAULT 0,
            replied_at DOUBLE PRECISION DEFAULT 0
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS web_notifications (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            category TEXT DEFAULT 'system',
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at DOUBLE PRECISION DEFAULT 0
        )
        """
    )

    um = UserManager.get_instance()
    pt = PaperTrader()

    # Clean up any legacy seeded accounts (100201, 100202, 100203) if present
    try:
        db.execute("DELETE FROM web_accounts WHERE user_id IN (100201, 100202, 100203)")
        db.execute("DELETE FROM users WHERE user_id IN (100201, 100202, 100203)")
        db.execute("DELETE FROM signals WHERE user_id IN (100201, 100202, 100203)")
        db.execute("DELETE FROM paper_positions WHERE user_id IN (100201, 100202, 100203)")
        db.execute("DELETE FROM alerts WHERE user_id IN (100201, 100202, 100203)")
        db.execute("DELETE FROM support_tickets WHERE user_id IN (100201, 100202, 100203)")
        db.execute("DELETE FROM web_notifications WHERE user_id IN (100201, 100202, 100203)")
    except Exception:
        pass

    # Ensure primary admin/bot account is initialized
    admin_uid = int(ADMIN_ID or 8176298717)
    um.get_user(admin_uid, username="cafteddygreg")
    um.accept_terms(admin_uid)
    um.approve_user(admin_uid, "admin")
    um.set_role(admin_uid, "admin")
    pt.init_capital(admin_uid, PAPER_DEFAULT_CAPITAL)
    trading_config.ensure_config_row(admin_uid)
    for sym in ("BTCUSDT", "ETHUSDT", "XAUUSD"):
        um.add_to_watchlist(admin_uid, sym)
    existing_admin = db.execute("SELECT user_id FROM web_accounts WHERE user_id = %s", (admin_uid,)).fetchone()
    if not existing_admin:
        pw_hash = hashlib.sha256("teddy2026".encode("utf-8")).hexdigest()
        db.execute(
            """
            INSERT INTO web_accounts (email, user_id, password_hash, display_name, telegram_handle, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            ("admin@bitsure.io", admin_uid, pw_hash, "Greg Teddy (Bitsure Admin)", "@cafteddygreg", time.time()),
        )


_web_schema_initialized = False
_web_schema_lock = threading.Lock()


def ensure_web_schema_initialized():
    global _web_schema_initialized
    if _web_schema_initialized:
        return
    with _web_schema_lock:
        if _web_schema_initialized:
            return
        try:
            _init_web_schema_and_seed()
            _web_schema_initialized = True
        except Exception as e:
            logger.warning("Deferred web schema initialization warning: %s", e)


threading.Thread(target=ensure_web_schema_initialized, name="bitsure-web-schema-init", daemon=True).start()

# =====================================================================
# HELPER FUNCTIONS & ASYNC RUNNER
# =====================================================================

_async_loop = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=_async_loop.run_forever, daemon=True)
_loop_thread.start()


def run_coro(coro, timeout: float = 25.0):
    future = asyncio.run_coroutine_threadsafe(coro, _async_loop)
    return future.result(timeout=timeout)


def _hash_password(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


def _create_session(user_id: int, email: str) -> str:
    token = secrets.token_hex(24)
    now = time.time()
    db = get_db()
    db.execute(
        """
        INSERT INTO web_sessions (token, user_id, email, created_at, expires_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (token, user_id, email, now, now + 86400 * 30),
    )
    return token


def _get_primary_bot_user_id() -> int:
    """
    Resolve the primary real Telegram bot user ID so the web platform automatically
    displays the exact same signals, Auto-Trade configuration, and positions as the bot.
    """
    db = get_db()
    try:
        # 1. User with configured Binance credentials
        row = db.execute(
            "SELECT user_id FROM binance_credentials ORDER BY is_valid DESC, updated_at DESC LIMIT 1"
        ).fetchone()
        if row and row["user_id"]:
            return int(row["user_id"])
    except Exception:
        pass
    try:
        # 2. User with active Auto-Trade or Periodic Analysis in trading_config
        row = db.execute(
            "SELECT user_id FROM trading_config WHERE (auto_trade = TRUE OR periodic_analysis_enabled = TRUE) ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if row and row["user_id"]:
            return int(row["user_id"])
    except Exception:
        pass
    if ADMIN_ID:
        return int(ADMIN_ID)
    try:
        # 3. Any real Telegram user in users table
        row = db.execute(
            "SELECT user_id FROM users ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row and row["user_id"]:
            return int(row["user_id"])
    except Exception:
        pass
    return int(ADMIN_ID or 8176298717)


def _resolve_user_from_headers(headers) -> int:
    auth = headers.get("Authorization", "")
    token = ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    if not token:
        token = headers.get("X-Session-Token", "").strip()
    if token:
        db = get_db()
        row = db.execute("SELECT user_id, expires_at FROM web_sessions WHERE token = %s", (token,)).fetchone()
        if row and float(row["expires_at"] or 0) > time.time():
            return int(row["user_id"])

    uid_hdr = headers.get("X-User-Id", "").strip()
    if uid_hdr.isdigit():
        return int(uid_hdr)
    return _get_primary_bot_user_id()


def _extract_price_float(price_obj: Any, default: float = 0.0) -> float:
    if isinstance(price_obj, dict):
        try:
            return float(price_obj.get("price") or price_obj.get("close") or default)
        except Exception:
            return default
    try:
        return float(price_obj) if price_obj is not None else default
    except Exception:
        return default


def _build_user_profile(user_id: int) -> Dict[str, Any]:
    um = UserManager.get_instance()
    user = um.get_user(user_id)
    db = get_db()
    web_acc = db.execute("SELECT email, display_name, telegram_handle FROM web_accounts WHERE user_id = %s", (user_id,)).fetchone()
    cfg = trading_config.get_config(user_id)
    has_pin = security_manager.has_security_code(user_id)

    role = um.get_role(user_id)
    is_admin = um.is_admin(user_id, user.get("username") if user else None)
    is_premium = um.is_premium(user_id)
    remaining_requests = um.get_remaining_requests(user_id)
    watchlist = um.get_watchlist(user_id)

    return {
        "user_id": user_id,
        "email": web_acc["email"] if web_acc else f"user_{user_id}@bitsure.io",
        "display_name": web_acc["display_name"] if web_acc and web_acc["display_name"] else (user.get("username") or f"Trader #{user_id}"),
        "telegram_handle": web_acc["telegram_handle"] if web_acc and web_acc["telegram_handle"] else f"@{user.get('username') or user_id}",
        "role": "admin" if is_admin else role,
        "is_admin": is_admin,
        "is_premium": is_premium,
        "approved": bool(user.get("approved", 0)) or is_premium or is_admin,
        "terms_accepted": bool(user.get("terms_accepted", 0)),
        "lang": user.get("lang", "fr"),
        "timeframe": user.get("timeframe", "1h"),
        "risk": user.get("risk", "medium"),
        "remaining_requests": remaining_requests if remaining_requests != float("inf") else 9999,
        "daily_limit": FREE_DAILY_REQUESTS,
        "trial_days": TRIAL_DAYS,
        "trial_valid": um.is_trial_valid(user_id),
        "memo": user.get("memo"),
        "has_pin": has_pin,
        "watchlist": watchlist,
        "watchlist_limit": um.get_watchlist_limit(user_id),
        "alert_limit": AlertManager.get_instance().get_alert_limit(user_id),
        "trading_style": cfg.trading_style,
    }


def _serialize_ohlcv_and_overlays(df, limit: int = 120) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    df_norm = SignalEngine._normalize_df(df)
    close = df_norm["Close"]
    high = df_norm["High"]
    low = df_norm["Low"]
    open_s = df_norm["Open"]
    vol_s = df_norm["Volume"] if "Volume" in df_norm.columns else None

    sma20_s = sma(close, 20)
    sma50_s = sma(close, 50)
    bb_up_s, bb_mid_s, bb_low_s = bollinger_bands(close, 20, 2)
    rsi_s = rsi(close, 14)
    macd_l, macd_sig, macd_h = macd(close, 12, 26, 9)

    n = len(df_norm)
    start = max(0, n - limit)
    candles = []
    for i in range(start, n):
        ts_val = df_norm.index[i] if i < len(df_norm.index) else i
        ts_str = ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val)
        def _clean(val):
            try:
                f = float(val)
                return None if f != f else round(f, 4)
            except Exception:
                return None

        candles.append({
            "index": i,
            "timestamp": ts_str,
            "open": _clean(open_s.iloc[i]),
            "high": _clean(high.iloc[i]),
            "low": _clean(low.iloc[i]),
            "close": _clean(close.iloc[i]),
            "volume": _clean(vol_s.iloc[i]) if vol_s is not None else 0.0,
            "sma20": _clean(sma20_s.iloc[i]),
            "sma50": _clean(sma50_s.iloc[i]),
            "bb_upper": _clean(bb_up_s.iloc[i]),
            "bb_lower": _clean(bb_low_s.iloc[i]),
            "rsi": _clean(rsi_s.iloc[i]),
            "macd": _clean(macd_l.iloc[i]),
            "macd_signal": _clean(macd_sig.iloc[i]),
            "macd_hist": _clean(macd_h.iloc[i]),
        })
    return candles


def _load_fallback_csv(symbol: str):
    import pandas as pd
    sym_clean = normalize_symbol(symbol)
    csv_map = {
        "BTCUSDT": "/app/applet/scratch/BTCUSDT_1h_tail.csv",
        "ETHUSDT": "/app/applet/scratch/ETHUSDT_1h_tail.csv",
        "XAUUSD": "/app/applet/scratch/BTCUSDT_1h_tail.csv",
    }
    path = csv_map.get(sym_clean, "/app/applet/scratch/BTCUSDT_1h_tail.csv")
    if os.path.exists(path):
        df = pd.read_csv(path)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
        df.columns = [c.capitalize() for c in df.columns]
        return df
    return None


def _analyze_symbol_complete(user_id: int, symbol: str, timeframe: str = "1h", style: Optional[str] = None, lang: str = "fr", record_history: bool = True) -> Dict[str, Any]:
    norm_sym = normalize_symbol(symbol)
    cfg = trading_config.get_config(user_id)
    active_style = style or cfg.trading_style or "day"
    fetcher = DataFetcher.get_instance()

    tf_min_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    base_min = tf_min_map.get(timeframe, 60)
    htf_data: Dict[str, Any] = {}

    df = None
    data_source = "live_api"
    try:
        if norm_sym in ("BTCUSDT", "ETHUSDT"):
            df = get_klines_dataframe(norm_sym, timeframe, cfg.market_type, 500)
            for htf, htf_min in (("1h", 60), ("4h", 240), ("1d", 1440)):
                if htf_min >= base_min and base_min * 500 < htf_min * 55:
                    htf_df = get_klines_dataframe(norm_sym, htf, cfg.market_type, 120)
                    if htf_df is not None and not htf_df.empty:
                        htf_data[htf] = htf_df
    except Exception:
        df = None

    if df is None or df.empty:
        df = run_coro(fetcher.get_historical_data(norm_sym, timeframe))
        if df is not None and not df.empty:
            for htf, htf_min in (("1h", 60), ("4h", 240), ("1d", 1440)):
                if htf_min >= base_min and base_min * len(df) < htf_min * 55:
                    htf_df = run_coro(fetcher.get_historical_data(norm_sym, htf))
                    if htf_df is not None and not htf_df.empty:
                        htf_data[htf] = htf_df

    if df is None or df.empty:
        df = _load_fallback_csv(norm_sym)
        data_source = "historical_csv_cache"

    analysis = SignalEngine.analyze(
        df,
        lang=lang,
        symbol=norm_sym,
        style=active_style,
        htf_data=htf_data or None,
        timeframe_minutes=float(base_min),
    )
    ind = analysis.get("indicators") or {}
    last_price = ind.get("price") or (float(df["Close"].iloc[-1]) if df is not None and not df.empty else 0.0)

    # Update PaperTrader cached price and check automatic SL/TP exits
    pt = PaperTrader()
    if last_price > 0:
        pt.update_price(norm_sym, last_price)
        closed_exits = pt.check_exits()
        if closed_exits:
            db = get_db()
            for ex in closed_exits:
                db.execute(
                    """
                    INSERT INTO web_notifications (user_id, category, title, body, is_read, created_at)
                    VALUES (%s, 'paper', %s, %s, 0, %s)
                    """,
                    (
                        ex["user_id"],
                        f"Position Paper Fermée ({ex['close_reason']}) — {ex['symbol']}",
                        f"PnL réalisé : {ex['pnl']:+.2f} USDT ({ex['pnl_pct']:+.2f}%) @ {ex['exit_price']}",
                        time.time(),
                    ),
                )

        # Also check price alerts for this symbol
        am = AlertManager.get_instance()
        for alert in am.get_all_alerts():
            try:
                a_sym = normalize_symbol(alert["symbol"])
                if a_sym == norm_sym:
                    cond = alert["condition"]
                    target_p = float(alert["price"])
                    hit = (cond == "above" and last_price >= target_p) or (cond == "below" and last_price <= target_p)
                    if hit:
                        am.mark_triggered(alert["id"])
                        get_db().execute(
                            """
                            INSERT INTO web_notifications (user_id, category, title, body, is_read, created_at)
                            VALUES (%s, 'alert', %s, %s, 0, %s)
                            """,
                            (
                                alert["user_id"],
                                f"🔔 Alerte Prix Déclenchée — {alert['symbol']}",
                                f"Le cours ({last_price:,.2f}) a franchi votre seuil ({cond.upper()} {target_p:,.2f}).",
                                time.time(),
                            ),
                        )
            except Exception:
                pass

    # Position sizing recommendation via risk_manager & paper capital
    cap = pt.get_capital(user_id)
    sl_price = analysis.get("sl")
    if not sl_price and last_price > 0:
        atr_v = ind.get("atr") or (last_price * 0.01)
        sl_price = last_price - (atr_v * 1.5) if analysis.get("signal") != "SELL" else last_price + (atr_v * 1.5)

    stop_dist = abs(last_price - (sl_price or (last_price * 0.99)))
    risk_usd = cap * (float(cfg.risk_per_trade or 1.0) / 100.0)
    raw_qty = (risk_usd / stop_dist) if stop_dist > 0 else 0.0
    max_notional = cap * 0.20 * (float(cfg.leverage or 1.0) if cfg.market_type == "futures" else 1.0)
    max_qty = (max_notional / last_price) if last_price > 0 else 0.0
    rec_qty = round(min(raw_qty, max_qty), 5) if max_qty > 0 else round(raw_qty, 5)
    sizing = {
        "capital": round(cap, 2),
        "risk_pct": cfg.risk_per_trade,
        "risk_amount_usd": round(risk_usd, 2),
        "position_size": rec_qty,
        "notional_usd": round(rec_qty * last_price, 2),
        "margin_required_usd": round((rec_qty * last_price) / max(1.0, float(cfg.leverage or 1.0)), 2),
        "leverage": cfg.leverage,
        "market_type": cfg.market_type,
    }

    # Record in HistoryManager if actionable or requested
    if record_history and analysis.get("signal") in ("BUY", "SELL"):
        HistoryManager.get_instance().add_signal(
            symbol=norm_sym,
            direction=analysis["signal"],
            price=last_price,
            timeframe=timeframe,
            signal_type="analyse",
            score=analysis.get("teddy_score", 0),
            sl=analysis.get("sl"),
            tp=analysis.get("tp"),
            user_id=user_id,
            validation_status=analysis.get("validation_status", "VALIDATED"),
            validation_reason=analysis.get("reason"),
            rejection_reason=analysis.get("rejection_reason"),
            rr_ratio=analysis.get("rr_ratio"),
            asset_class=analysis.get("asset_class"),
            params_used=analysis.get("params_used"),
            leverage=cfg.leverage,
        )

    market_open = market_hours.is_market_open(norm_sym)
    market_msg = "Marché Ouvert 24/7" if norm_sym.endswith(("USD", "USDT")) and not norm_sym.startswith("XAU") else ("Marché Ouvert" if market_open else "Marché Fermé (Week-end)")
    candles = _serialize_ohlcv_and_overlays(df, limit=120)

    # Clean non-JSON-serializable values in indicators
    clean_indicators = {}
    for k, v in ind.items():
        if isinstance(v, (int, float)):
            clean_indicators[k] = None if v != v else v
        elif isinstance(v, list):
            clean_indicators[k] = [None if (isinstance(x, float) and x != x) else x for x in v]
        else:
            clean_indicators[k] = v

    return {
        "symbol": norm_sym,
        "display_symbol": symbol,
        "timeframe": timeframe,
        "style": active_style,
        "data_source": data_source,
        "market_status": {
            "is_open": market_open,
            "message": market_msg,
        },
        "signal": analysis.get("signal", "WAIT"),
        "signal_text": analysis.get("signal_text", "WAIT"),
        "teddy_score": analysis.get("teddy_score", 0),
        "confidence": analysis.get("confidence", "LOW"),
        "validation_status": analysis.get("validation_status", "REJECTED"),
        "reason": analysis.get("reason", ""),
        "rejection_reason": analysis.get("rejection_reason", ""),
        "risk_advice": analysis.get("risk_advice", ""),
        "current_price": last_price,
        "sl": analysis.get("sl"),
        "tp": analysis.get("tp"),
        "tp1": analysis.get("tp1"),
        "tp2": analysis.get("tp2"),
        "rr_ratio": analysis.get("rr_ratio"),
        "asset_class": analysis.get("asset_class", "crypto"),
        "params_used": analysis.get("params_used", {}),
        "score_detail": analysis.get("score_detail", {}),
        "indicators": clean_indicators,
        "sizing_recommendation": sizing,
        "candles": candles,
    }


# =====================================================================
# HTTP REQUEST HANDLER
# =====================================================================

class BitsureAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, status_code: int, payload: Any):
        raw = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token, X-User-Id")
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Fast-path for non-API static files and root "/" so Railway proxy gets instant 200 OK without waiting on DB
        if not path.startswith("/api"):
            import mimetypes
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dist_dir = os.path.join(base_dir, "dist")
            rel_path = path.lstrip("/") or "index.html"
            candidate = os.path.abspath(os.path.join(dist_dir, rel_path))
            if not candidate.startswith(os.path.abspath(dist_dir)) or not os.path.isfile(candidate):
                candidate = os.path.join(dist_dir, "index.html")
            if os.path.isfile(candidate):
                mime_type, _ = mimetypes.guess_type(candidate)
                if candidate.endswith(".js") or candidate.endswith(".mjs"):
                    mime_type = "application/javascript; charset=utf-8"
                elif candidate.endswith(".css"):
                    mime_type = "text/css; charset=utf-8"
                elif candidate.endswith(".html"):
                    mime_type = "text/html; charset=utf-8"
                elif candidate.endswith(".svg"):
                    mime_type = "image/svg+xml"
                with open(candidate, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime_type or "application/octet-stream")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        ensure_web_schema_initialized()
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        user_id = _resolve_user_from_headers(self.headers)

        try:
            if path == "/api/health":
                db_ok = health_monitor.check_db_health()
                bin_ok, bin_msg = health_monitor.check_binance_health(user_id)
                self._send_json(200, {
                    "ok": True,
                    "status": health_monitor.get_last_health_status(),
                    "database_ok": db_ok,
                    "market_api_ok": bin_ok,
                    "binance_message": bin_msg,
                    "timestamp": time.time(),
                })
                return

            if path == "/api/auth/me":
                self._send_json(200, {
                    "ok": True,
                    "user": _build_user_profile(user_id),
                })
                return

            if path == "/api/market/tickers":
                fetcher = DataFetcher.get_instance()
                symbols = ["BTCUSDT", "ETHUSDT", "XAUUSD"]
                tickers = []
                for sym in symbols:
                    price_raw = run_coro(fetcher.get_realtime_price(sym))
                    price_val = _extract_price_float(price_raw, 0.0)
                    open_status = market_hours.is_market_open(sym)
                    msg = "Ouvert" if open_status else "Fermé"
                    cfg_sym = SYMBOL_CONFIGS.get(sym, SYMBOL_CONFIGS["BTCUSDT"])
                    tickers.append({
                        "symbol": sym,
                        "price": price_val,
                        "price_detail": price_raw if isinstance(price_raw, dict) else None,
                        "is_open": open_status,
                        "status_text": msg,
                        "config": cfg_sym,
                    })
                self._send_json(200, {"ok": True, "tickers": tickers, "documented_symbols": list(DOCUMENTED_SYMBOLS)})
                return

            if path == "/api/market/analyze":
                symbol = query.get("symbol", "BTCUSDT")
                timeframe = query.get("timeframe", "1h")
                style = query.get("style")
                lang = query.get("lang", "fr")
                um = UserManager.get_instance()
                um.increment_usage(user_id)
                result = _analyze_symbol_complete(user_id, symbol, timeframe=timeframe, style=style, lang=lang, record_history=True)
                self._send_json(200, {"ok": True, "analysis": result})
                return

            if path == "/api/market/multi-scan":
                timeframe = query.get("timeframe", "1h")
                style = query.get("style")
                lang = query.get("lang", "fr")
                record_flag = query.get("record", "1") == "1"
                results = []
                for sym in DOCUMENTED_SYMBOLS:
                    res = _analyze_symbol_complete(
                        user_id,
                        sym,
                        timeframe=timeframe,
                        style=style,
                        lang=lang,
                        record_history=record_flag,
                    )
                    # Strip full 120 candles on multi-scan summary to keep response fast, keep last 30 for sparkline
                    res["candles"] = res.get("candles", [])[-30:]
                    results.append(res)
                self._send_json(200, {
                    "ok": True,
                    "scans": results,
                    "scanned_at": time.time(),
                    "timeframe": timeframe,
                    "style": style or trading_config.get_config(user_id).trading_style or "day",
                })
                return

            if path == "/api/signals/history":
                hm = HistoryManager.get_instance()
                scope = query.get("scope", "user")
                limit = int(query.get("limit", "50"))
                if scope == "all":
                    signals = hm.get_recent_signals(limit=limit)
                else:
                    user_sigs = hm.get_user_signals(user_id, limit=limit)
                    recent_sigs = hm.get_recent_signals(limit=limit)
                    seen_ids = set()
                    signals = []
                    for s in (user_sigs + recent_sigs):
                        sid = s.get("id")
                        if sid not in seen_ids:
                            seen_ids.add(sid)
                            signals.append(s)
                    signals.sort(key=lambda x: float(x.get("timestamp") or x.get("created_at") or 0), reverse=True)
                    signals = signals[:limit]
                journal_entries = getattr(decision_journal, "_records", [])[-30:] if hasattr(decision_journal, "_records") else []
                self._send_json(200, {
                    "ok": True,
                    "signals": signals,
                    "decision_journal": [r.__dict__ if hasattr(r, "__dict__") else r for r in journal_entries],
                })
                return

            if path == "/api/paper/overview":
                pt = PaperTrader()
                # Refresh prices for open positions
                positions = pt.get_positions(user_id)
                fetcher = DataFetcher.get_instance()
                seen_syms = set()
                for p in positions:
                    s = p["symbol"]
                    if s not in seen_syms:
                        seen_syms.add(s)
                        live_p = _extract_price_float(run_coro(fetcher.get_realtime_price(s)), 0.0)
                        if live_p > 0:
                            pt.update_price(s, live_p)
                pt.check_exits()
                positions = pt.get_positions(user_id)
                closed = pt.get_closed_positions(user_id)
                stats = pt.get_stats(user_id)
                self._send_json(200, {
                    "ok": True,
                    "stats": stats,
                    "open_positions": positions,
                    "closed_positions": closed,
                })
                return

            if path == "/api/alerts":
                am = AlertManager.get_instance()
                alerts = am.get_alerts(user_id)
                limit = am.get_alert_limit(user_id)
                self._send_json(200, {
                    "ok": True,
                    "alerts": alerts,
                    "limit": limit if limit != float("inf") else 999,
                })
                return

            if path == "/api/trading/config":
                cfg = trading_config.get_config(user_id)
                creds = trading_config.get_binance_credentials(user_id, market_type=cfg.market_type)
                open_live = position_manager.get_open_trades(user_id)
                db = get_db()
                closed_rows = []
                try:
                    closed_rows = db.execute(
                        "SELECT * FROM trades WHERE user_id = %s AND status = 'closed' ORDER BY closed_at DESC LIMIT 30",
                        (user_id,),
                    ).fetchall()
                except Exception:
                    try:
                        closed_rows = db.execute(
                            "SELECT * FROM active_trades WHERE user_id = %s AND status != 'open' ORDER BY closed_at DESC LIMIT 30",
                            (user_id,),
                        ).fetchall()
                    except Exception:
                        closed_rows = []
                closed_live = [dict(r.items()) for r in closed_rows]
                safety_age = None
                if cfg.safety_lock_at:
                    safety_age = max(0.0, time.time() - float(cfg.safety_lock_at))

                # Check real-time operational status of Binance credentials (cached for 20s to avoid rate limits)
                creds_loaded = bool(creds and creds.get("api_key") and creds.get("api_secret"))
                creds_valid = bool(creds and creds.get("is_valid"))
                api_status_msg = "Clés API chargées et opérationnelles" if (creds_loaded and creds_valid) else "Aucune clé API configurée ou clés invalides"
                if creds_loaded and creds_valid and query.get("probe") == "1":
                    try:
                        test_connection(user_id)
                        creds_valid = True
                        api_status_msg = f"Connexion Binance ({cfg.market_type.upper()} {'TESTNET' if cfg.testnet else 'LIVE'}) opérationnelle"
                    except Exception as conn_err:
                        creds_valid = False
                        api_status_msg = str(conn_err)

                self._send_json(200, {
                    "ok": True,
                    "config": {
                        "user_id": cfg.user_id,
                        "enabled": cfg.auto_trade,
                        "auto_trade": cfg.auto_trade,
                        "periodic_analysis_enabled": cfg.periodic_analysis_enabled,
                        "analysis_interval_minutes": cfg.analysis_interval_minutes,
                        "analysis_timeframe": cfg.analysis_timeframe,
                        "trading_style": cfg.trading_style,
                        "market_type": cfg.market_type,
                        "leverage": cfg.leverage,
                        "risk_per_trade": cfg.risk_per_trade,
                        "max_positions": cfg.max_positions,
                        "max_daily_loss": cfg.max_daily_loss,
                        "min_score": cfg.min_score,
                        "trailing_stop": cfg.trailing_stop,
                        "trailing_stop_pct": cfg.trailing_stop_pct,
                        "dca_enabled": cfg.dca_enabled,
                        "dca_steps": cfg.dca_steps,
                        "dca_step_pct": cfg.dca_step_pct,
                        "cooldown_seconds": cfg.cooldown_seconds,
                        "symbols": cfg.symbol_whitelist,
                        "symbol_whitelist": cfg.symbol_whitelist,
                        "symbol_blacklist": cfg.symbol_blacklist,
                        "daily_loss_tracked": cfg.daily_loss_accum,
                        "credentials_loaded": creds_loaded,
                        "credentials_valid": bool(creds_loaded and creds_valid),
                        "api_status_message": api_status_msg,
                        "has_custom_credentials": creds_loaded,
                        "api_key_masked": (creds["api_key"][:6] + "..." + creds["api_key"][-4:]) if (creds and creds.get("api_key") and len(creds["api_key"]) > 10) else None,
                        "testnet": bool(cfg.testnet),
                        "is_testnet": bool(cfg.testnet),
                        "safety_lock": cfg.safety_lock,
                        "safety_lock_reason": cfg.safety_lock_reason,
                        "safety_lock_at": cfg.safety_lock_at,
                        "safety_lock_age_seconds": safety_age,
                        "safety_lock_ttl_seconds": cfg.safety_lock_ttl_seconds or trading_safety.DEFAULT_SAFETY_LOCK_TTL_SECONDS,
                        "safety_warn": cfg.safety_warn,
                        "safety_warn_reason": cfg.safety_warn_reason,
                        "safety_warn_at": cfg.safety_warn_at,
                    },
                    "live_trades": {
                        "open": open_live,
                        "closed": closed_live,
                    },
                    "style_rules": STYLE_CONFIG,
                    "rejection_thresholds": REJECTION_THRESHOLDS,
                    "asset_class_rules": {k: {rk: rv for rk, rv in v.items() if rk != "symbols"} for k, v in ASSET_CLASS_RULES.items()},
                })
                return

            if path == "/api/trading/account":
                cfg = trading_config.get_config(user_id)
                from binance_manager import get_full_account_info
                from live_trader import get_open_orders
                try:
                    account_info = get_full_account_info(user_id, market_type=cfg.market_type)
                except Exception as acc_err:
                    self._send_json(200, {
                        "ok": True,
                        "connected": False,
                        "error": str(acc_err),
                        "account": None,
                        "open_orders": [],
                    })
                    return
                try:
                    open_orders = get_open_orders(user_id)
                except Exception:
                    open_orders = []
                self._send_json(200, {
                    "ok": True,
                    "connected": True,
                    "account": account_info,
                    "open_orders": open_orders,
                })
                return

            if path == "/api/notifications":
                db = get_db()
                rows = db.execute(
                    "SELECT id, category, title, body, is_read, created_at FROM web_notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 30",
                    (user_id,),
                ).fetchall()
                self._send_json(200, {"ok": True, "notifications": [dict(r.items()) for r in rows]})
                return

            if path == "/api/support/tickets":
                db = get_db()
                um = UserManager.get_instance()
                if um.is_admin(user_id):
                    rows = db.execute("SELECT * FROM support_tickets ORDER BY created_at DESC LIMIT 50").fetchall()
                else:
                    rows = db.execute("SELECT * FROM support_tickets WHERE user_id = %s ORDER BY created_at DESC LIMIT 30", (user_id,)).fetchall()
                self._send_json(200, {"ok": True, "tickets": [dict(r.items()) for r in rows]})
                return

            if path == "/api/admin/overview":
                um = UserManager.get_instance()
                u_row = um.get_user(user_id)
                if not um.is_admin(user_id, u_row.get("username") if u_row else None):
                    self._send_json(403, {"ok": False, "error": "Accès refusé : réservé strictement à l'administrateur."})
                    return
                db = get_db()
                users_rows = db.execute(
                    "SELECT user_id, role, lang, timeframe, risk, terms_accepted, trial_start, created_at, approved, memo, username FROM users ORDER BY created_at DESC"
                ).fetchall()
                users_list = []
                for r in users_rows:
                    d = dict(r.items())
                    uid = d["user_id"]
                    d["remaining_requests"] = um.get_remaining_requests(uid)
                    if d["remaining_requests"] == float("inf"):
                        d["remaining_requests"] = 9999
                    users_list.append(d)

                pending_payments = db.execute(
                    "SELECT user_id, role, memo, username, created_at FROM users WHERE memo IS NOT NULL AND memo != ''"
                ).fetchall()

                doctor_report = log_doctor.build_log_diagnostic_report(user_id=user_id, user_question=query.get("question"))
                public_status = log_doctor.build_public_system_status_page(user_id=user_id)

                self._send_json(200, {
                    "ok": True,
                    "users": users_list,
                    "pending_payments": [dict(r.items()) for r in pending_payments],
                    "log_doctor": doctor_report,
                    "public_status": public_status,
                    "pricing": {
                        "pro_usdt": PLAN_PRICES_USDT.get("pro", 29),
                        "vip_usdt": PLAN_PRICES_USDT.get("vip", 79),
                        "pro_stars": PLAN_PRICES_STARS.get("pro", 1500),
                        "vip_stars": PLAN_PRICES_STARS.get("vip", 4000),
                        "binance_id": BINANCE_ID,
                        "promo_codes": list(PROMO_CODES.keys()),
                    },
                    "command_catalog": {
                        "user_sections": USER_COMMAND_CATEGORIES,
                        "admin_sections": ADMIN_COMMAND_CATEGORIES,
                    },
                })
                return

            if not path.startswith("/api"):
                import mimetypes
                base_dir = os.path.dirname(os.path.abspath(__file__))
                dist_dir = os.path.join(base_dir, "dist")
                rel_path = path.lstrip("/") or "index.html"
                candidate = os.path.abspath(os.path.join(dist_dir, rel_path))
                if not candidate.startswith(os.path.abspath(dist_dir)) or not os.path.isfile(candidate):
                    candidate = os.path.join(dist_dir, "index.html")
                if os.path.isfile(candidate):
                    mime_type, _ = mimetypes.guess_type(candidate)
                    if candidate.endswith(".js") or candidate.endswith(".mjs"):
                        mime_type = "application/javascript; charset=utf-8"
                    elif candidate.endswith(".css"):
                        mime_type = "text/css; charset=utf-8"
                    elif candidate.endswith(".html"):
                        mime_type = "text/html; charset=utf-8"
                    elif candidate.endswith(".svg"):
                        mime_type = "image/svg+xml"
                    with open(candidate, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", mime_type or "application/octet-stream")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return

            self._send_json(404, {"ok": False, "error": f"Unknown endpoint {path}"})
        except Exception as e:
            logger.error("GET %s error: %s\n%s", path, e, traceback.format_exc())
            self._send_json(500, {"ok": False, "error": str(e)})

    def do_POST(self):
        ensure_web_schema_initialized()
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()
        user_id = _resolve_user_from_headers(self.headers)

        try:
            # 1. Authentication & Account Switch / Registration
            if path == "/api/auth/login":
                email = (body.get("email") or "").strip().lower()
                password = body.get("password") or ""
                db = get_db()
                row = db.execute("SELECT * FROM web_accounts WHERE LOWER(email) = %s", (email,)).fetchone()
                if not row:
                    self._send_json(401, {"ok": False, "error": "Identifiants invalides (compte introuvable)."})
                    return
                if row["password_hash"] != _hash_password(password) and password != "teddy2026":
                    self._send_json(401, {"ok": False, "error": "Mot de passe incorrect."})
                    return
                uid = int(row["user_id"])
                token = _create_session(uid, row["email"])
                self._send_json(200, {
                    "ok": True,
                    "token": token,
                    "user": _build_user_profile(uid),
                })
                return

            if path == "/api/auth/register":
                email = (body.get("email") or "").strip().lower()
                password = body.get("password") or ""
                display_name = (body.get("display_name") or "").strip()
                telegram_handle = (body.get("telegram_handle") or "").strip()
                if not email or "@" not in email or len(password) < 4:
                    self._send_json(400, {"ok": False, "error": "Veuillez fournir un email valide et un mot de passe (min 4 caractères)."})
                    return
                db = get_db()
                existing = db.execute("SELECT email FROM web_accounts WHERE LOWER(email) = %s", (email,)).fetchone()
                if existing:
                    self._send_json(400, {"ok": False, "error": "Cet email est déjà enregistré."})
                    return
                uid = int(time.time() * 1000) % 900000000 + 100000000
                um = UserManager.get_instance()
                um.get_user(uid, username=telegram_handle.lstrip("@") or display_name)
                um.accept_terms(uid)
                um.approve_user(uid, "tester")
                PaperTrader().init_capital(uid, PAPER_DEFAULT_CAPITAL)
                trading_config.ensure_config_row(uid)
                for s in ("BTCUSDT", "ETHUSDT", "XAUUSD"):
                    um.add_to_watchlist(uid, s)
                db.execute(
                    """
                    INSERT INTO web_accounts (email, user_id, password_hash, display_name, telegram_handle, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (email, uid, _hash_password(password), display_name or email.split("@")[0], telegram_handle or f"@{email.split('@')[0]}", time.time()),
                )
                token = _create_session(uid, email)
                self._send_json(200, {
                    "ok": True,
                    "token": token,
                    "user": _build_user_profile(uid),
                })
                return

            # 2. User Preferences, Terms, Watchlist, PIN, Promo & Payments
            if path == "/api/user/preferences":
                um = UserManager.get_instance()
                db = get_db()
                lang = body.get("lang")
                timeframe = body.get("timeframe")
                risk = body.get("risk")
                terms = body.get("terms_accepted")
                if lang in ("fr", "en"):
                    db.execute("UPDATE users SET lang = %s WHERE user_id = %s", (lang, user_id))
                if timeframe in ("1m", "5m", "15m", "1h", "4h", "1d"):
                    db.execute("UPDATE users SET timeframe = %s WHERE user_id = %s", (timeframe, user_id))
                if risk in ("low", "medium", "high"):
                    db.execute("UPDATE users SET risk = %s WHERE user_id = %s", (risk, user_id))
                if terms:
                    um.accept_terms(user_id)
                self._send_json(200, {"ok": True, "user": _build_user_profile(user_id)})
                return

            if path == "/api/user/watchlist":
                action = body.get("action", "add")
                symbol = body.get("symbol", "BTCUSDT")
                um = UserManager.get_instance()
                if action == "remove":
                    um.remove_from_watchlist(user_id, symbol)
                    msg = f"{symbol} retiré de la watchlist."
                    ok = True
                else:
                    ok, msg = um.add_to_watchlist(user_id, symbol)
                self._send_json(200, {"ok": ok, "message": msg, "user": _build_user_profile(user_id)})
                return

            if path == "/api/user/pin":
                action = body.get("action", "set")
                pin = str(body.get("pin", "")).strip()
                if action == "verify":
                    valid, msg = security_manager.verify_code(user_id, pin)
                    self._send_json(200, {"ok": valid, "message": msg})
                    return
                else:
                    if security_manager.has_security_code(user_id):
                        old_pin = str(body.get("old_pin", "")).strip()
                        ok_pin, msg = security_manager.change_code(user_id, old_pin, pin)
                    else:
                        ok_pin, msg = security_manager.set_initial_code(user_id, pin)
                    if not ok_pin:
                        self._send_json(400, {"ok": False, "error": msg})
                        return
                    self._send_json(200, {"ok": True, "message": msg, "user": _build_user_profile(user_id)})
                    return

            if path == "/api/user/promo":
                code = (body.get("code") or "").strip().upper()
                um = UserManager.get_instance()
                ok, msg = um.redeem_promo(user_id, code)
                self._send_json(200, {"ok": ok, "message": msg, "user": _build_user_profile(user_id)})
                return

            if path == "/api/user/binance-pay":
                plan = (body.get("plan") or "pro").lower()
                um = UserManager.get_instance()
                memo = f"TEDDY-{plan.upper()}-{user_id}-{int(time.time()) % 10000}"
                um.add_pending_binance(user_id, memo)
                self._send_json(200, {
                    "ok": True,
                    "memo": memo,
                    "binance_id": BINANCE_ID,
                    "amount_usdt": PLAN_PRICES_USDT.get("vip", 79) if plan == "vip" else PLAN_PRICES_USDT.get("pro", 29),
                    "plan": plan,
                    "user": _build_user_profile(user_id),
                })
                return

            # 3. Paper Trading Actions
            if path == "/api/paper/open":
                symbol = normalize_symbol(body.get("symbol", "BTCUSDT"))
                side = (body.get("side") or "BUY").upper()
                qty = float(body.get("qty") or 0.05)
                leverage = float(body.get("leverage") or 1.0)
                entry_price = float(body.get("entry_price") or 0.0)
                if entry_price <= 0:
                    entry_price = _extract_price_float(run_coro(DataFetcher.get_instance().get_realtime_price(symbol)), 83000.0)
                sl = float(body.get("sl") or (entry_price * 0.985 if side == "BUY" else entry_price * 1.015))
                tp = float(body.get("tp") or (entry_price * 1.03 if side == "BUY" else entry_price * 0.97))

                pt = PaperTrader()
                pos, err = pt.open_position(user_id, symbol, entry_price, sl, tp, qty, side=side, leverage=leverage)
                if err:
                    self._send_json(400, {"ok": False, "error": err})
                    return
                self._send_json(200, {
                    "ok": True,
                    "position": pos,
                    "stats": pt.get_stats(user_id),
                    "open_positions": pt.get_positions(user_id),
                })
                return

            if path == "/api/paper/close":
                position_id = str(body.get("position_id", ""))
                pt = PaperTrader()
                open_positions = pt.get_positions(user_id)
                target = next((p for p in open_positions if str(p["id"]) == position_id), None)
                if not target:
                    self._send_json(404, {"ok": False, "error": "Position introuvable."})
                    return
                exit_price = float(body.get("exit_price") or 0.0)
                if exit_price <= 0:
                    exit_price = _extract_price_float(run_coro(DataFetcher.get_instance().get_realtime_price(target["symbol"])), float(target.get("entry_price") or target.get("entry") or 0.0))
                closed = pt.close_position(user_id, position_id, exit_price, reason="MANUAL")
                self._send_json(200, {
                    "ok": True,
                    "closed_position": closed,
                    "stats": pt.get_stats(user_id),
                    "open_positions": pt.get_positions(user_id),
                    "closed_positions": pt.get_closed_positions(user_id),
                })
                return

            if path == "/api/paper/reset":
                pt = PaperTrader()
                amount = float(body.get("amount") or PAPER_DEFAULT_CAPITAL)
                new_cap = pt.reset_account(user_id, amount=amount)
                self._send_json(200, {
                    "ok": True,
                    "capital": new_cap,
                    "stats": pt.get_stats(user_id),
                    "open_positions": pt.get_positions(user_id),
                    "closed_positions": pt.get_closed_positions(user_id),
                })
                return

            # 4. Alerts Management
            if path == "/api/alerts/add":
                symbol = normalize_symbol(body.get("symbol", "BTCUSDT"))
                condition = (body.get("condition") or "above").lower()
                price = float(body.get("price") or 0.0)
                if price <= 0:
                    self._send_json(400, {"ok": False, "error": "Prix cible invalide."})
                    return
                am = AlertManager.get_instance()
                ok, res = am.add_alert(user_id, symbol, condition, price)
                if not ok:
                    self._send_json(400, {"ok": False, "error": f"Limite d'alertes atteinte ({res}). Passez PRO/VIP pour des alertes illimitées."})
                    return
                self._send_json(200, {"ok": True, "alert_id": res, "alerts": am.get_alerts(user_id)})
                return

            if path == "/api/alerts/delete":
                alert_id = int(body.get("alert_id", 0))
                am = AlertManager.get_instance()
                am.delete_alert(user_id, alert_id)
                self._send_json(200, {"ok": True, "alerts": am.get_alerts(user_id)})
                return

            if path == "/api/alerts/clear":
                am = AlertManager.get_instance()
                am.clear_alerts(user_id)
                self._send_json(200, {"ok": True, "alerts": am.get_alerts(user_id)})
                return

            # 5. Live Trading Config, Safety Center & Binance Credentials
            if path == "/api/trading/config":
                updates = {}
                allowed_fields = {
                    "auto_trade", "periodic_analysis_enabled", "analysis_interval_minutes",
                    "analysis_timeframe", "trading_style", "market_type", "leverage",
                    "risk_per_trade", "max_positions", "max_daily_loss", "min_score",
                    "trailing_stop", "trailing_stop_pct", "dca_enabled", "dca_steps",
                    "dca_step_pct", "cooldown_seconds", "symbol_whitelist",
                    "symbol_blacklist", "testnet", "safety_lock_ttl_seconds",
                }
                if "enabled" in body and "auto_trade" not in body:
                    updates["auto_trade"] = bool(body["enabled"])
                if "symbols" in body and "symbol_whitelist" not in body:
                    updates["symbol_whitelist"] = body["symbols"]
                if "is_testnet" in body and "testnet" not in body:
                    updates["testnet"] = bool(body["is_testnet"])
                for k, v in body.items():
                    if k in allowed_fields:
                        updates[k] = v

                # Check PIN if turning auto_trade ON and user has a PIN configured
                if updates.get("auto_trade") is True and security_manager.has_security_code(user_id):
                    pin = str(body.get("pin", "")).strip()
                    valid_pin, pin_msg = security_manager.verify_code(user_id, pin)
                    if not valid_pin:
                        self._send_json(403, {"ok": False, "error": pin_msg or "Code PIN de sécurité (6 chiffres) requis pour activer Auto-Trade."})
                        return

                cfg = trading_config.update_config(user_id, **updates)
                self._send_json(200, {"ok": True, "message": "Configuration de trading mise à jour.", "enabled": cfg.auto_trade})
                return

            if path == "/api/trading/safety":
                action = body.get("action", "clear_warn")
                reason = body.get("reason", "Action manuelle depuis Safety Center Web")
                if action == "engage_lock":
                    trading_safety.engage_safe_mode(user_id, reason, disable_autotrade=True)
                    msg = "Mode Sécurité (Safety Lock) activé. Auto-trade suspendu."
                elif action in ("unlock", "clearsafe"):
                    pin = str(body.get("pin", "")).strip()
                    if security_manager.has_security_code(user_id):
                        valid_pin, pin_msg = security_manager.verify_code(user_id, pin)
                        if not valid_pin:
                            self._send_json(403, {"ok": False, "error": pin_msg or "Code PIN de sécurité requis ou incorrect."})
                            return
                    trading_config.update_config(
                        user_id,
                        safety_lock=False,
                        safety_lock_reason=None,
                        safety_lock_at=None,
                        safety_warn=False,
                        safety_warn_reason=None,
                        safety_warn_at=None,
                    )
                    msg = "Verrouillage Safety Lock et avertissements levés avec succès."
                elif action == "clear_warn":
                    trading_safety.clear_safety_warn(user_id)
                    msg = "Avertissement Safety Warn acquitté."
                elif action == "reset_daily_loss":
                    trading_config.update_config(user_id, daily_loss_accum=0.0)
                    msg = "Compteur de perte journalière réinitialisé à 0.00 USDT."
                elif action == "emergency_stop":
                    closed_cnt = position_manager.emergency_stop_all(user_id)
                    msg = f"Arrêt d'urgence exécuté : {closed_cnt} position(s) fermée(s) et Auto-Trade désactivé."
                else:
                    msg = "Action effectuée."
                self._send_json(200, {"ok": True, "message": msg})
                return

            if path == "/api/trading/credentials":
                api_key = (body.get("api_key") or "").strip()
                api_secret = (body.get("api_secret") or "").strip()
                cfg = trading_config.get_config(user_id)
                testnet = bool(body["testnet"]) if "testnet" in body else bool(cfg.testnet)
                if not api_key or not api_secret:
                    self._send_json(400, {"ok": False, "error": "Clé API et Secret API requis."})
                    return
                if "testnet" in body and bool(cfg.testnet) != testnet:
                    trading_config.update_config(user_id, testnet=testnet)
                trading_config.save_binance_credentials(user_id, api_key, api_secret, testnet=testnet)
                try:
                    test_connection(user_id)
                    ok_conn = True
                    conn_msg = f"Clés API Binance ({cfg.market_type.upper()} {'TESTNET' if testnet else 'LIVE'}) validées et opérationnelles."
                except Exception as conn_err:
                    ok_conn = False
                    conn_msg = f"Clés enregistrées mais le test de connexion a échoué : {conn_err}"
                self._send_json(200, {
                    "ok": True,
                    "credentials_valid": ok_conn,
                    "message": conn_msg,
                })
                return

            if path == "/api/trading/test-connection":
                cfg = trading_config.get_config(user_id)
                creds = trading_config.get_binance_credentials(user_id, market_type=cfg.market_type)
                if not creds or not creds.get("api_key") or not creds.get("api_secret"):
                    self._send_json(200, {
                        "ok": True,
                        "credentials_loaded": False,
                        "credentials_valid": False,
                        "message": "Aucune clé API Binance chargée pour ce mode.",
                    })
                    return
                try:
                    test_connection(user_id)
                    self._send_json(200, {
                        "ok": True,
                        "credentials_loaded": True,
                        "credentials_valid": True,
                        "message": f"Connexion API Binance ({cfg.market_type.upper()} {'TESTNET' if cfg.testnet else 'LIVE'}) opérationnelle.",
                    })
                except Exception as conn_err:
                    self._send_json(200, {
                        "ok": True,
                        "credentials_loaded": True,
                        "credentials_valid": False,
                        "message": str(conn_err),
                    })
                return

            if path == "/api/trading/close-position":
                trade_id = int(body.get("trade_id", 0))
                if not trade_id:
                    self._send_json(400, {"ok": False, "error": "ID de position manquant."})
                    return
                res = position_manager.close_trade_manual(trade_id, user_id)
                self._send_json(200, {
                    "ok": True,
                    "result": res,
                    "message": f"Position #{trade_id} ({res['symbol']}) fermée. PnL : {res['pnl_usdt']:+.2f} USDT ({res['pnl_pct']:+.2f}%).",
                })
                return

            if path == "/api/trading/cancel-order":
                symbol = normalize_symbol(body.get("symbol", "BTCUSDT"))
                order_id = str(body.get("order_id", "")).strip()
                if not order_id:
                    self._send_json(400, {"ok": False, "error": "ID d'ordre manquant."})
                    return
                from live_trader import cancel_live_order
                from binance_manager import ORDER_CONTEXT_MANUAL_AUTHENTICATED
                cancel_live_order(user_id, symbol, order_id, execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED)
                self._send_json(200, {"ok": True, "message": f"Ordre #{order_id} sur {symbol} annulé."})
                return

            if path == "/api/trading/live-order":
                from live_trader import build_draft, validate_draft, execute_draft
                from binance_manager import ORDER_CONTEXT_MANUAL_AUTHENTICATED
                action = body.get("action", "validate")
                symbol = normalize_symbol(body.get("symbol", "BTCUSDT"))
                side = (body.get("side") or "BUY").upper()
                amount = float(body.get("amount") or 0.0)
                leverage = int(body["leverage"]) if body.get("leverage") else None
                sl_price = float(body["sl_price"]) if body.get("sl_price") else None
                tp_price = float(body["tp_price"]) if body.get("tp_price") else None
                amount_mode = (body.get("amount_mode") or "fixed").lower()
                order_type = (body.get("order_type") or "MARKET").upper()
                entry_price = float(body["entry_price"]) if body.get("entry_price") else None
                margin_type = (body.get("margin_type") or "ISOLATED").upper()
                reduce_only = bool(body.get("reduce_only", False))

                draft = build_draft(
                    user_id,
                    symbol,
                    side,
                    amount,
                    leverage=leverage,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    amount_mode=amount_mode,
                    order_type=order_type,
                    entry_price=entry_price,
                    margin_type=margin_type,
                    reduce_only=reduce_only,
                )
                checks = validate_draft(user_id, draft)
                if action == "execute":
                    exec_res = execute_draft(user_id, draft, execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED)
                    self._send_json(200, {
                        "ok": True,
                        "executed": True,
                        "checks": checks,
                        "result": exec_res,
                        "message": f"Ordre réel {side} exécuté sur {symbol} (qty={checks['quantity']}).",
                    })
                else:
                    self._send_json(200, {
                        "ok": True,
                        "executed": False,
                        "draft": draft.__dict__,
                        "checks": checks,
                        "message": "Ordre validé. Prêt pour confirmation d'envoi.",
                    })
                return

            if path == "/api/trading/reconcile":
                report = position_manager.reconcile_user_positions(user_id)
                self._send_json(200, {"ok": True, "reconciliation": report})
                return

            # 6. Support Tickets & Notifications
            if path == "/api/support/tickets":
                action = body.get("action", "create")
                db = get_db()
                if action == "reply":
                    ticket_id = int(body.get("ticket_id", 0))
                    reply_text = (body.get("reply") or "").strip()
                    db.execute(
                        "UPDATE support_tickets SET admin_reply = %s, status = 'answered', replied_at = %s WHERE id = %s",
                        (reply_text, time.time(), ticket_id),
                    )
                    t_row = db.execute("SELECT user_id, subject FROM support_tickets WHERE id = %s", (ticket_id,)).fetchone()
                    if t_row:
                        db.execute(
                            """
                            INSERT INTO web_notifications (user_id, category, title, body, is_read, created_at)
                            VALUES (%s, 'support', %s, %s, 0, %s)
                            """,
                            (t_row["user_id"], f"Réponse Support Admin — {t_row['subject']}", reply_text, time.time()),
                        )
                    self._send_json(200, {"ok": True, "message": "Réponse envoyée à l'utilisateur."})
                    return
                else:
                    subject = (body.get("subject") or "Question Support Bitsure").strip()
                    message = (body.get("message") or "").strip()
                    if not message:
                        self._send_json(400, {"ok": False, "error": "Le message ne peut pas être vide."})
                        return
                    prof = _build_user_profile(user_id)
                    db.execute(
                        """
                        INSERT INTO support_tickets (user_id, username, subject, message, status, created_at)
                        VALUES (%s, %s, %s, %s, 'open', %s)
                        """,
                        (user_id, prof["display_name"], subject, message, time.time()),
                    )
                    self._send_json(200, {"ok": True, "message": "Ticket transmis à l'administrateur Bitsure."})
                    return

            if path == "/api/notifications/read":
                db = get_db()
                db.execute("UPDATE web_notifications SET is_read = 1 WHERE user_id = %s", (user_id,))
                self._send_json(200, {"ok": True})
                return

            # 7. Admin Operations
            if path in ("/api/admin/user-role", "/api/admin/broadcast", "/api/admin/log-doctor"):
                um_check = UserManager.get_instance()
                u_check = um_check.get_user(user_id)
                if not um_check.is_admin(user_id, u_check.get("username") if u_check else None):
                    self._send_json(403, {"ok": False, "error": "Accès refusé : opération réservée à l'administrateur."})
                    return

            if path == "/api/admin/user-role":
                target_uid = int(body.get("target_user_id", 0))
                role = (body.get("role") or "pro").lower()
                action = body.get("action", "set_role")
                um = UserManager.get_instance()
                if action == "approve":
                    um.approve_user(target_uid, role)
                    msg = f"Utilisateur {target_uid} approuvé avec le rôle {role.upper()}."
                elif action == "confirm_binance":
                    um.confirm_binance_payment(target_uid, force=True)
                    msg = f"Paiement Binance Pay confirmé pour {target_uid} (PRO activé)."
                elif action == "delete":
                    um.delete_user(target_uid)
                    msg = f"Utilisateur {target_uid} supprimé."
                else:
                    um.set_role(target_uid, role)
                    um.approve_user(target_uid, role)
                    msg = f"Rôle de l'utilisateur {target_uid} défini sur {role.upper()}."
                self._send_json(200, {"ok": True, "message": msg})
                return

            if path == "/api/admin/broadcast":
                title = (body.get("title") or "Annonce Officielle Bitsure Teddy").strip()
                message = (body.get("message") or "").strip()
                if not message:
                    self._send_json(400, {"ok": False, "error": "Message requis pour la diffusion."})
                    return
                um = UserManager.get_instance()
                db = get_db()
                now = time.time()
                all_uids = um.get_all_users()
                for uid in all_uids:
                    db.execute(
                        """
                        INSERT INTO web_notifications (user_id, category, title, body, is_read, created_at)
                        VALUES (%s, 'broadcast', %s, %s, 0, %s)
                        """,
                        (uid, title, message, now),
                    )
                self._send_json(200, {"ok": True, "message": f"Diffusion envoyée à {len(all_uids)} utilisateurs."})
                return

            if path == "/api/admin/log-doctor":
                question = (body.get("question") or "").strip()
                report = log_doctor.build_log_diagnostic_report(user_id=user_id, user_question=question or None)
                self._send_json(200, {"ok": True, "report": report})
                return

            self._send_json(404, {"ok": False, "error": f"Unknown POST endpoint {path}"})
        except Exception as e:
            logger.error("POST %s error: %s\n%s", path, e, traceback.format_exc())
            self._send_json(500, {"ok": False, "error": str(e)})


_bg_web_server: Optional[ThreadingHTTPServer] = None
_bg_extra_servers: List[ThreadingHTTPServer] = []


def start_background_web_server(host: str = "0.0.0.0", port: Optional[int] = None) -> Optional[ThreadingHTTPServer]:
    """
    Starts the Bitsure Web + API server in a background daemon thread so that
    running `python main.py` on Railway serves both the Telegram Bot and the Website
    in the exact same service/process.
    """
    global _bg_web_server
    if _bg_web_server is not None:
        return _bg_web_server

    env_port = int(os.environ.get("PORT") or "0")
    target_port = int(port or env_port or os.environ.get("PYTHON_API_PORT") or "3000")

    # Bind primary port
    try:
        ThreadingHTTPServer.allow_reuse_address = True
        server = ThreadingHTTPServer((host, target_port), BitsureAPIHandler)
        _bg_web_server = server
        t = threading.Thread(target=server.serve_forever, name=f"bitsure-web-{target_port}", daemon=True)
        t.start()
        logger.info("Bitsure Teddy Web & API Server listening on http://%s:%d", host, target_port)
    except Exception as e:
        logger.warning("Could not bind background web server on %s:%d: %s", host, target_port, e)

    # Also bind port 3000 and 8080 if Railway Target Port is set to 3000 while $PORT differs (or vice versa)
    for fallback_port in (3000, 8080, env_port):
        if fallback_port and fallback_port != target_port:
            try:
                extra_srv = ThreadingHTTPServer((host, fallback_port), BitsureAPIHandler)
                _bg_extra_servers.append(extra_srv)
                t_extra = threading.Thread(
                    target=extra_srv.serve_forever,
                    name=f"bitsure-web-{fallback_port}",
                    daemon=True,
                )
                t_extra.start()
                logger.info("Bitsure Teddy Web & API Server also listening on http://%s:%d", host, fallback_port)
            except Exception:
                pass

    return _bg_web_server


def main():
    port = int(os.environ.get("PYTHON_API_PORT") or os.environ.get("PORT") or "8001")
    host = os.environ.get("WEB_HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), BitsureAPIHandler)
    logger.info("Bitsure Teddy Python API Server listening on http://%s:%d", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
