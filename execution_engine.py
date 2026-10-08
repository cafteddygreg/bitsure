"""
execution_engine.py
---------------------
Cœur de la logique d'exécution des signaux : lit les signaux "pending"/"active",
filtre par score/config, puis :
  - mode automatique : ouvre directement la position
  - mode semi-automatique : envoie un message Telegram avec boutons de confirmation

Ce module est appelé par un job APScheduler (voir main_integration.py) et par
les callbacks des boutons "✅ Ouvrir" / "❌ Refuser".
"""

import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_connection
from trading_config import get_config, TradingConfig
from risk_manager import check_can_open_position, calculate_position_size
from binance_manager import (
    open_position, get_price, get_tradable_symbols, get_klines_dataframe,
    make_client_order_id, BinanceClientError, ORDER_CONTEXT_AUTOTRADE,
    ORDER_CONTEXT_MANUAL_AUTHENTICATED,
)
from history_manager import HistoryManager
from signal_engine import SignalEngine
from trading_logger import get_trading_logger, log_trade_opened, log_error
from trading_safety import (
    SafetyError,
    assert_trading_allowed,
    mark_signal_refused,
    reserve_signal_for_execution,
    validate_signal_freshness,
)

logger = get_trading_logger("execution_engine")


def fetch_pending_signals():
    """Récupère uniquement les signaux non encore traités portant sur les symboles documentés du bot."""
    purge_undocumented_signals()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, symbol, direction, entry_price, sl, tp, score,
                       timeframe, signal_type, created_at
                FROM signals
                WHERE (
                        status IN ('pending', 'active')
                        OR (status = 'skipped' AND COALESCE(rejection_reason, '') LIKE 'safe_mode:%%')
                      )
                  AND direction IN ('BUY', 'SELL')
                  AND UPPER(symbol) IN ('BTCUSDT', 'ETHUSDT', 'XAUUSD')
                ORDER BY id ASC
                """
            )
            cols = [
                "id", "user_id", "symbol", "direction", "entry_price", "sl", "tp", "score",
                "timeframe", "signal_type", "created_at",
            ]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def mark_signal_status(signal_id: str, status: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE signals SET status = %s WHERE id = %s", (status, signal_id))
        conn.commit()
    finally:
        conn.close()



def validate_signal_for_execution(user_id: int, signal: dict, config: TradingConfig) -> tuple[bool, str | None]:
    """Applique les garde-fous juste avant toute ouverture de position."""
    try:
        is_manual = str(signal.get("id", "")).startswith("manual-") or signal.get("status") == "awaiting_confirmation"
        require_auto = False if is_manual else bool(config.auto_trade)
        assert_trading_allowed(config, require_auto_trade=require_auto)
        if signal.get("id") and not str(signal["id"]).startswith("manual-"):
            validate_signal_freshness(signal)
    except SafetyError as e:
        return False, str(e)

    if int(signal["user_id"]) != int(user_id):
        return False, "Ce signal ne t'appartient pas."

    if str(signal.get("symbol", "")).upper() not in ALLOWED_DOCUMENTED_SYMBOLS_SET:
        return False, f"Symbole non documenté ({signal.get('symbol')}). Seuls {', '.join(DOCUMENTED_SYMBOLS)} sont autorisés."

    if config.market_type == "spot" and signal["direction"] == "SELL":
        return False, "SELL non supporté en mode Spot standard."

    if signal.get("score") is not None and signal["score"] < config.min_score:
        return False, f"Score insuffisant ({signal['score']} < {config.min_score})."

    if signal.get("entry_price") is not None:
        entry = signal["entry_price"]
        sl = signal.get("sl")
        tp = signal.get("tp")
        if sl is None or tp is None:
            return False, "SL/TP manquants."
        if signal["direction"] == "BUY" and not (sl < entry < tp):
            return False, "SL/TP incohérents avec un signal BUY."
        if signal["direction"] == "SELL" and not (tp < entry < sl):
            return False, "SL/TP incohérents avec un signal SELL."

    risk_check = check_can_open_position(
        user_id,
        config,
        signal["symbol"],
        signal.get("direction"),
        require_auto_trade=require_auto,
    )
    if not risk_check.allowed:
        return False, risk_check.reason or "Règle de risque non respectée."

    return True, None

def insert_trade_row(**fields) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades (signal_id, user_id, symbol, direction, entry_price,
                    sl_price, tp_price, quantity, leverage, market_type, status,
                    opened_at, binance_order_id, binance_client_order_id,
                    sl_order_id, tp_order_id, error_message)
                VALUES (%(signal_id)s, %(user_id)s, %(symbol)s, %(direction)s, %(entry_price)s,
                    %(sl_price)s, %(tp_price)s, %(quantity)s, %(leverage)s, %(market_type)s,
                    %(status)s, %(opened_at)s, %(binance_order_id)s, %(binance_client_order_id)s,
                    %(sl_order_id)s, %(tp_order_id)s, %(error_message)s)
                RETURNING id
                """,
                fields,
            )
            trade_id = cur.fetchone()[0]
        conn.commit()
        return trade_id
    finally:
        conn.close()


def _default_trade_fields(signal: dict, config: TradingConfig) -> dict:
    return {
        "signal_id": signal["id"],
        "user_id": signal["user_id"],
        "symbol": signal["symbol"],
        "direction": signal["direction"],
        "entry_price": signal["entry_price"],
        "sl_price": signal["sl"],
        "tp_price": signal["tp"],
        "quantity": None,
        "leverage": config.leverage,
        "market_type": config.market_type,
        "status": "error",
        "opened_at": time.time(),
        "binance_order_id": None,
        "binance_client_order_id": None,
        "sl_order_id": None,
        "tp_order_id": None,
        "error_message": None,
    }


def execute_signal(signal: dict, config: TradingConfig, execution_context: str | None = None) -> dict:
    """
    Exécute réellement l'ordre sur Binance pour un signal donné, en calculant
    la taille de position, puis enregistre le trade en base.
    Retourne le dict de la ligne insérée (utile pour notifier l'utilisateur).
    """
    if not execution_context:
        if str(signal.get("id", "")).startswith("manual-") or signal.get("status") == "awaiting_confirmation":
            execution_context = ORDER_CONTEXT_MANUAL_AUTHENTICATED
        else:
            execution_context = ORDER_CONTEXT_AUTOTRADE

    user_id = signal["user_id"]
    if signal.get("id") and not str(signal["id"]).startswith("manual-"):
        try:
            allowed_statuses = ("awaiting_confirmation",) if signal.get("status") == "awaiting_confirmation" else ("pending", "active")
            signal = reserve_signal_for_execution(signal["id"], user_id, allowed_statuses)
            allowed, reason = validate_signal_for_execution(user_id, signal, config)
            if not allowed:
                mark_signal_refused(signal["id"], reason or "Validation refusée")
                raise SafetyError(reason or "Validation refusée")
        except SafetyError as e:
            fields = _default_trade_fields(signal, config)
            fields["error_message"] = str(e)
            fields["status"] = "skipped"
            return fields

    symbol = signal["symbol"]
    direction = signal["direction"]
    fields = _default_trade_fields(signal, config)

    try:
        entry_price = signal["entry_price"] or get_price(user_id, symbol, config.market_type)
        quantity = calculate_position_size(
            user_id, config, entry_price, signal["sl"], config.market_type
        )

        result = open_position(
            user_id=user_id,
            symbol=symbol,
            direction=direction,
            quantity=quantity,
            sl_price=signal["sl"],
            tp_price=signal["tp"],
            market_type=config.market_type,
            leverage=config.leverage,
            client_order_id=make_client_order_id("sig", signal["id"]),
            execution_context=execution_context,
        )

        fields.update({
            "status": "open",
            "quantity": result["quantity"],
            "binance_order_id": str(result.get("order_id")),
            "binance_client_order_id": result.get("client_order_id"),
            "sl_order_id": str(result.get("sl_order_id")) if result.get("sl_order_id") else None,
            "tp_order_id": str(result.get("tp_order_id")) if result.get("tp_order_id") else None,
        })
        log_trade_opened(logger, user_id, symbol, direction, result["quantity"], entry_price)
        mark_signal_status(signal["id"], "executed")

    except (BinanceClientError, ValueError) as e:
        fields["error_message"] = str(e)
        log_error(logger, user_id, "execute_signal", str(e))
        mark_signal_status(signal["id"], "error")

    trade_id = insert_trade_row(**fields)
    fields["id"] = trade_id
    return fields


async def process_signal_for_user(context: ContextTypes.DEFAULT_TYPE, signal: dict):
    """Point d'entrée appelé par le job planifié pour chaque signal en attente."""
    user_id = signal["user_id"]
    config = get_config(user_id)

    allowed, reason = validate_signal_for_execution(user_id, signal, config)
    if not allowed:
        mark_signal_refused(signal["id"], reason or "Validation refusée")
        return

    if config.auto_trade:
        trade = execute_signal(signal, config)
        await _notify_trade_result(context, user_id, trade)
    else:
        await _send_confirmation_prompt(context, signal, config)


async def _notify_trade_result(context: ContextTypes.DEFAULT_TYPE, user_id: int, trade: dict):
    if trade["status"] == "open":
        text = (
            f"✅ *Position ouverte automatiquement*\n\n"
            f"Symbole : `{trade['symbol']}`\n"
            f"Direction : {trade['direction']}\n"
            f"Quantité : {trade['quantity']}\n"
            f"SL : {trade['sl_price']}  |  TP : {trade['tp_price']}"
        )
    else:
        text = (
            f"⚠️ *Échec d'ouverture de position*\n\n"
            f"Symbole : `{trade['symbol']}`\n"
            f"Erreur : {trade.get('error_message', 'inconnue')}"
        )
    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")


async def _send_confirmation_prompt(context: ContextTypes.DEFAULT_TYPE, signal: dict, config: TradingConfig):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ouvrir", callback_data=f"trading_open_{signal['id']}"),
            InlineKeyboardButton("❌ Refuser", callback_data=f"trading_reject_{signal['id']}"),
        ],
        [InlineKeyboardButton("⚙️ Modifier SL/TP", callback_data=f"trading_edit_{signal['id']}")],
    ])
    text = (
        f"📡 *Nouveau signal détecté*\n\n"
        f"Symbole : `{signal['symbol']}`\n"
        f"Direction : {signal['direction']}\n"
        f"Prix d'entrée : {signal['entry_price']}\n"
        f"SL : {signal['sl']}  |  TP : {signal['tp']}\n"
        f"Score : {signal['score']}\n\n"
        f"Que veux-tu faire ?"
    )
    await context.bot.send_message(
        chat_id=signal["user_id"], text=text, reply_markup=keyboard, parse_mode="Markdown"
    )
    mark_signal_status(signal["id"], "awaiting_confirmation")


async def scheduled_signal_scan(context: ContextTypes.DEFAULT_TYPE):
    """Job APScheduler : à enregistrer toutes les 15-30s dans main.py."""
    for signal in fetch_pending_signals():
        try:
            await process_signal_for_user(context, signal)
        except Exception as e:
            log_error(logger, signal.get("user_id"), "scheduled_signal_scan", str(e))



def get_configured_analysis_intervals() -> list[int]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT analysis_interval_minutes
                FROM trading_config
                WHERE (auto_trade = TRUE OR periodic_analysis_enabled = TRUE)
                  AND analysis_interval_minutes IS NOT NULL
                  AND analysis_interval_minutes > 0
                """
            )
            intervals = {int(row[0]) for row in cur.fetchall()}
    finally:
        conn.close()

    intervals.update({5, 10})
    return sorted(intervals)


def _get_auto_trade_user_ids(interval_minutes: int) -> list[int]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id
                FROM trading_config
                WHERE (auto_trade = TRUE OR periodic_analysis_enabled = TRUE)
                  AND analysis_interval_minutes = %s
                """,
                (interval_minutes,),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


from config import DOCUMENTED_SYMBOLS

# Uniquement les symboles documentés dans le bot (BTCUSDT, ETHUSDT, XAUUSD).
# Aucun autre symbole ne peut être analysé ni apparaître dans les signaux ou rapports.
ALLOWED_DOCUMENTED_SYMBOLS_SET = frozenset(DOCUMENTED_SYMBOLS)
DEFAULT_PERIODIC_SCAN_SYMBOLS = list(DOCUMENTED_SYMBOLS)


def purge_undocumented_signals() -> int:
    """Supprime ou rejette immédiatement de la table `signals` tout signal portant sur un symbole non documenté."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM signals
                WHERE UPPER(symbol) NOT IN ('BTCUSDT', 'ETHUSDT', 'XAUUSD')
                """
            )
            deleted = cur.rowcount or 0
        conn.commit()
        return deleted
    except Exception:
        return 0
    finally:
        conn.close()


def _resolve_requested_scan_symbols(user_id: int, config: TradingConfig) -> tuple[list[str], str]:
    """
    Retourne UNIQUEMENT les symboles documentés dans le bot (`BTCUSDT`, `ETHUSDT`, `XAUUSD`).
    Tout symbole non documenté éventuellement présent dans une ancienne Whitelist ou Watchlist est strictement filtré.
    """
    # 1. Si une Whitelist explicite AutoTrade contient des symboles documentés :
    if config.symbol_whitelist:
        out: list[str] = []
        for s in config.symbol_whitelist:
            raw = str(s).strip().upper().replace("/", "").replace(" ", "").replace("-", "")
            if raw in ALLOWED_DOCUMENTED_SYMBOLS_SET and raw not in out:
                out.append(raw)
        if out:
            return out, "Whitelist (Symboles documentés)"

    # 2. Si la Watchlist de l'utilisateur contient des symboles documentés :
    try:
        from user_manager import UserManager
        wl = UserManager.get_instance().get_watchlist(user_id) or []
    except Exception:
        wl = []

    if wl:
        out = []
        for s in wl:
            raw = str(s).strip().upper().replace("/", "").replace(" ", "").replace("-", "")
            if raw in ALLOWED_DOCUMENTED_SYMBOLS_SET and raw not in out:
                out.append(raw)
        if out:
            return out, "Watchlist (Symboles documentés)"

    # 3. Par défaut : exactement les 5 symboles documentés dans le bot
    return list(DEFAULT_PERIODIC_SCAN_SYMBOLS), "Symboles documentés du bot"


def _format_market_scan_report(
    config: TradingConfig,
    scanned: int,
    saved: list[tuple[str, dict, str]],
    rejected_by_risk: int,
    errors: int,
    rejected_spot_sell: int = 0,
    read_only_safe_mode: bool = False,
    top_wait_or_low: list[tuple[str, dict]] | None = None,
    symbols_source: str = "",
    requested_symbols: list[str] | None = None,
) -> str:
    title = "📊 *Rapport d'Analyse Périodique*"
    if read_only_safe_mode or config.safety_lock:
        title += " _(lecture seule — Safe Mode)_"
    sym_list_str = ", ".join(requested_symbols) if requested_symbols else "—"
    lines = [
        title,
        "━━━━━━━━━━━━━━━━━━━━━",
        f"• Marché : `{config.market_type.upper()}` | TF : `{config.analysis_timeframe}` | Style : `{config.trading_style}`",
        f"• Périmètre ({symbols_source or 'Sélection'}) : `{sym_list_str}`",
        f"• Paires analysées : *{scanned}* | Signaux retenus (≥ {config.min_score}) : *{len(saved)}*",
    ]
    if rejected_by_risk or errors:
        lines.append(f"• Filtrés (score/risque) : {rejected_by_risk} | Indisponibles : {errors}")
    if read_only_safe_mode or config.safety_lock:
        lines.append("⚠️ _Safe mode actif : aucun ordre automatique ni signal pending créé._")
    if rejected_spot_sell:
        lines.append(f"ℹ️ _SELL ignorés (mode Spot) : {rejected_spot_sell}_")

    if saved:
        lines.append("")
        header = "🎯 *Signaux actionnables détectés :*"
        lines.append(header)
        for symbol, result, signal_id in saved[:8]:
            sig_emoji = "🟢" if result.get("signal") == "BUY" else "🔴"
            price_val = result.get("indicators", {}).get("price", 0)
            sl_val = result.get("sl")
            tp_val = result.get("tp")
            sl_str = f"{float(sl_val):.4f}" if sl_val else "—"
            tp_str = f"{float(tp_val):.4f}" if tp_val else "—"
            lines.append(
                f"{sig_emoji} *{symbol}* `{result['signal']}` @ `{float(price_val):.4f}` "
                f"(Score: *{result['teddy_score']}* | SL: `{sl_str}` | TP: `{tp_str}`)"
            )
    else:
        lines.append("")
        lines.append(f"ℹ️ *Aucun signal BUY/SELL n'atteint le score minimum ({config.min_score}/100) sur ce cycle.*")
        if top_wait_or_low:
            lines.append("\n🔎 *Aperçu des paires scannées (Top scores) :*")
            for symbol, res in top_wait_or_low[:6]:
                sig = res.get("signal", "WAIT")
                sig_emoji = "🟢" if sig == "BUY" else "🔴" if sig == "SELL" else "⚪"
                price_val = res.get("indicators", {}).get("price", 0)
                rsi_val = res.get("indicators", {}).get("rsi", "—")
                score_val = res.get("teddy_score", 0)
                lines.append(
                    f"• {sig_emoji} `{symbol}` : *{sig}* (Score *{score_val}* | Prix `{float(price_val):.4f}` | RSI `{rsi_val}`)"
                )
    return "\n".join(lines)


async def run_market_analysis_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    interval_minutes: int = 5,
    send_telegram: bool = False,
) -> str:
    """
    Exécute un cycle complet d'analyse périodique pour un utilisateur donné
    et retourne le rapport formaté.
    Scanne en priorité sa Whitelist / Watchlist + les 10 paires majeures liquides
    pour répondre en quelques secondes sans jamais bloquer le bot.
    """
    import asyncio
    from trading_config import get_binance_credentials

    history_mgr = HistoryManager.get_instance()
    config = get_config(user_id)
    read_only_safe_mode = bool(config.safety_lock)

    purge_undocumented_signals()

    # Construire strictement la liste des symboles documentés du bot
    symbols, symbols_source = _resolve_requested_scan_symbols(user_id, config)
    symbols = [s for s in symbols if s in ALLOWED_DOCUMENTED_SYMBOLS_SET]

    if config.symbol_blacklist:
        bl_set = {str(b).upper().replace("/", "") for b in config.symbol_blacklist}
        symbols = [s for s in symbols if s not in bl_set]

    creds = get_binance_credentials(user_id, market_type=config.market_type)
    has_valid_keys = bool(creds and creds.get("api_key") and creds.get("is_valid"))

    scanned = 0
    rejected_by_risk = 0
    errors = 0
    rejected_spot_sell = 0
    saved: list[tuple[str, dict, str]] = []
    all_analyzed: list[tuple[str, dict]] = []

    from data_fetcher import DataFetcher
    fetcher_inst = DataFetcher.get_instance()

    for symbol in symbols:
        if symbol not in ALLOWED_DOCUMENTED_SYMBOLS_SET:
            continue
        try:
            if symbol in ("BTCUSDT", "ETHUSDT"):
                df = await asyncio.to_thread(
                    get_klines_dataframe,
                    symbol,
                    config.analysis_timeframe,
                    config.market_type,
                    300,
                )
            else:
                df = await fetcher_inst.get_historical_data(symbol, timeframe=config.analysis_timeframe)
            if df is None or df.empty:
                errors += 1
                continue

            scanned += 1
            result = SignalEngine.analyze(
                df,
                "fr",
                symbol=symbol,
                style=config.trading_style,
            )
            all_analyzed.append((symbol, result))

            price = float(result["indicators"]["price"])
            rsi = result["indicators"].get("rsi", "N/A")
            macd = result["indicators"].get("macd", "N/A")
            score = result.get("teddy_score", 0)
            sig = result.get("signal", "WAIT")

            logger.info(f"[{symbol}] Prix: {price:.4f} | RSI: {rsi} | MACD: {macd} | Score: {score} | Signal: {sig}")

            if sig not in ("BUY", "SELL"):
                continue

            if score < config.min_score:
                rejected_by_risk += 1
                continue

            if config.market_type == "spot" and sig == "SELL":
                rejected_spot_sell += 1
                continue

            if read_only_safe_mode:
                saved.append((symbol, result, "READONLY"))
                continue

            # Si l'utilisateur a des clés Binance valides, on vérifie les règles de risque du compte
            # (sans exiger auto_trade=True si seule l'Analyse Périodique est activée)
            if has_valid_keys:
                risk_check = check_can_open_position(
                    user_id,
                    config,
                    symbol,
                    sig,
                    require_auto_trade=bool(config.auto_trade),
                )
                if not risk_check.allowed:
                    rejected_by_risk += 1
                    continue

            signal_id = history_mgr.add_signal(
                symbol=symbol,
                direction=sig,
                price=price,
                timeframe=config.analysis_timeframe,
                signal_type="market_scan",
                score=score,
                sl=result.get("sl"),
                tp=result.get("tp"),
                user_id=user_id,
                validation_status=result.get("validation_status", "VALIDATED"),
                validation_reason=result.get("reason"),
                rejection_reason=result.get("rejection_reason"),
                rr_ratio=result.get("rr_ratio"),
                asset_class=result.get("asset_class"),
                params_used={
                    **(result.get("params_used") or {}),
                    "market_type": config.market_type,
                    "analysis_interval_minutes": interval_minutes,
                },
            )
            if signal_id:
                saved.append((symbol, result, signal_id))
        except Exception as e:
            errors += 1
            log_error(logger, user_id, f"scheduled_market_analysis.{symbol}", str(e))

    all_analyzed.sort(key=lambda item: float(item[1].get("teddy_score", 0)), reverse=True)

    report = _format_market_scan_report(
        config,
        scanned,
        saved,
        rejected_by_risk,
        errors,
        rejected_spot_sell,
        read_only_safe_mode=read_only_safe_mode,
        top_wait_or_low=all_analyzed,
        symbols_source=symbols_source,
        requested_symbols=symbols,
    )
    logger.info(f"--- Rapport final User {user_id} ---\n{report}")
    if send_telegram and context and hasattr(context, "bot"):
        try:
            await context.bot.send_message(chat_id=user_id, text=report, parse_mode="Markdown")
        except Exception:
            try:
                plain = report.replace("*", "").replace("`", "").replace("_", "")
                await context.bot.send_message(chat_id=user_id, text=plain)
            except Exception as e:
                log_error(logger, user_id, "scheduled_market_analysis.report", str(e))
    return report


async def scheduled_market_analysis(context: ContextTypes.DEFAULT_TYPE, interval_minutes: int):
    """
    Job planifié APScheduler : analyse les paires pour tous les utilisateurs ayant activé
    AutoTrade ou l'Analyse Périodique sur l'intervalle demandé.
    """
    user_ids = _get_auto_trade_user_ids(interval_minutes)
    if not user_ids:
        return

    logger.info(f"=== [ ANALYSE PERIODIQUE ({interval_minutes}m) ] === Démarrage pour {len(user_ids)} utilisateur(s)")

    for user_id in user_ids:
        try:
            await run_market_analysis_for_user(
                context,
                user_id,
                interval_minutes=interval_minutes,
                send_telegram=True,
            )
        except Exception as e:
            log_error(logger, user_id, "scheduled_market_analysis", str(e))
