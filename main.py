#!/usr/bin/env python3
"""
Bitsure Teddy - Main Entry Point
"""

import logging
import os

# =========================================================
# EARLY EMBEDDED WEB SERVER STARTUP (FOR RAILWAY / CLOUD)
# =========================================================
# Bind HTTP server immediately before heavy imports/DB init
# so Railway's proxy healthcheck gets an instant response.
if __name__ == "__main__" and os.environ.get("DISABLE_EMBEDDED_WEB") != "1" and not os.environ.get("WEBHOOK_URL"):
    try:
        from web_api_server import start_background_web_server
        _early_port = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "3000")
        start_background_web_server(host="0.0.0.0", port=_early_port)
    except Exception as _early_web_err:
        print(f"[main] Early web server startup notice: {_early_web_err}", flush=True)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

import engine_lease
from config import ADMIN_ID, TELEGRAM_TOKEN
from data_fetcher import DataFetcher

# Handler /myid accessible à tous sans aucune restriction
async def myid_handler(update, context):
    user = update.effective_user
    username = f"@{user.username}" if user.username else user.first_name
    await update.message.reply_text(
        f"🆔 Your ID: {user.id}\n"
        f"👤 Name: {username}\n\n"
        f"Send this ID to @btsrteddy to get an invitation."
    )

from alert_manager import AlertManager
from database import get_db

# =========================================================
# INIT DATABASE
# =========================================================

get_db()

# =========================================================
# IMPORT HANDLERS - USER
# =========================================================

from bot_handlers import (
    start,
    help_command,
    analyse,
    price,
    alert,
    alerts,
    delalert,
    clearalerts,
    watchlist_command,
    addwatch,
    removewatch,
    scan,
    trend,
    volatility,
    levels,
    settings,
    settimeframe,
    setstyle,
    setlanguage,
    usage,
    upgrade,
    plan_callback,
    pre_checkout,
    successful_payment,
    pay_binance,
    support,
    status_command,
    logs_command,
    historique,
    menu_command,
    menu_callback,
    symbol_callback,
    terms_callback,
    handle_pending_alert_input,
    paper,
    start_weekly_report_scheduler,
    start_signal_monitoring,
)

# =========================================================
# IMPORT HANDLERS - ADMIN
# =========================================================

from admin_handlers import (
    deleteuser,
    exportsignals,
    dbquery,
    cleanwaits,
    stats,
    teddy,
    broadcast,
    switchapi,
    find_memo,
    confirm_payment,
    refreshhistory,
    clearhistory,
    admin_cmd_trading_stats,
    admin_cmd_trades,
    admin_cmd_forceclose,
)

from trading_handlers import (
    cmd_setapikeys,
    cmd_autotrade,
    cmd_config,
    cmd_positions,
    cmd_close,
    cmd_pnl,
    cmd_account,
    cmd_trade_history,
    cmd_setleverage, cmd_setsecurity, cmd_confirmmanual, cmd_periodic_analysis,
    cmd_setrisk,
    cmd_setmaxpos, cmd_setminscore, cmd_setdailymaxloss,
    cmd_setmarket, cmd_settradingstyle, cmd_setanalysistf, cmd_setanalysisinterval, cmd_settrailing,
    cmd_setcooldown, cmd_settestnet, cmd_setdca,
    cmd_whitelist,
    cmd_blacklist,
    cmd_emergency_stop,
    cmd_editsignal,
    cmd_clearsafe,
    cmd_safestatus,
    trading_callback_router,
)
from live_handlers import (
    cmd_live,
    cmd_live_cancel,
    cmd_live_close,
    cmd_live_long,
    cmd_live_short,
    live_callback_router,
)
from execution_engine import (
    get_configured_analysis_intervals, scheduled_market_analysis, scheduled_signal_scan,
)
from position_manager import monitor_open_positions, reconcile_all_accounts

autotrade_scheduler = None


async def scheduled_paper_exits_job(context=None):
    """Job 15s : met à jour les prix des symboles ayant des positions paper ouvertes puis appelle PaperTrader().check_exits()."""
    try:
        from paper_trader import PaperTrader

        pt = PaperTrader.get_instance()
        conn = get_db()
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM paper_positions WHERE status = 'open'"
        ).fetchall()
        symbols = [str(r["symbol"]).upper() for r in rows if r and r.get("symbol")]
        if not symbols:
            return
        fetcher = DataFetcher.get_instance()
        for sym in symbols:
            try:
                price_info = fetcher.get_current_price(sym)
                live_price = float((price_info or {}).get("price") or 0.0)
                if live_price > 0:
                    pt.update_price(sym, live_price)
            except Exception as price_err:
                logger.debug(f"Paper price update skipped for {sym}: {price_err}")
        pt.check_exits()
    except Exception as e:
        logger.warning(f"Paper exits scheduler job failed: {e}")


async def scheduled_subscription_expiry_job(context=None):
    """Job quotidien : rétrograde en 'free' les abonnements expirés et notifie l'utilisateur."""
    try:
        from user_manager import UserManager

        um = UserManager.get_instance()
        expired_uids = um.expire_subscriptions()
        bot = getattr(context, "bot", None) if context else None
        for uid in expired_uids:
            if uid > 0 and bot is not None:
                try:
                    await bot.send_message(
                        chat_id=uid,
                        text="⚠️ Votre abonnement PRO/VIP Bitsure Teddy est arrivé à échéance. Votre compte est repassé en offre Free. Utilisez /upgrade pour renouveler votre accès.",
                    )
                except Exception as notify_err:
                    logger.warning(f"Failed to notify expired user {uid}: {notify_err}")
    except Exception as e:
        logger.warning(f"Subscription expiry job failed: {e}")


def start_autotrade_scheduler(app):
    global autotrade_scheduler
    if autotrade_scheduler is not None and getattr(autotrade_scheduler, "running", False):
        app.bot_data["autotrade_scheduler"] = autotrade_scheduler
        return
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    autotrade_scheduler = AsyncIOScheduler(timezone="UTC")
    app.bot_data["autotrade_scheduler"] = autotrade_scheduler
    autotrade_scheduler.add_job(
        engine_lease.leased(scheduled_signal_scan), "interval", seconds=20,
        kwargs={"context": app},
        id="scheduled_signal_scan", replace_existing=True
    )
    try:
        analysis_intervals = get_configured_analysis_intervals()
    except Exception as e:
        logger.warning(f"Analysis interval discovery failed, using defaults: {e}")
        analysis_intervals = [5, 10]

    for interval in analysis_intervals:
        autotrade_scheduler.add_job(
            engine_lease.leased(scheduled_market_analysis), "interval", minutes=interval,
            kwargs={"context": app, "interval_minutes": interval},
            id=f"market_analysis_{interval}m", replace_existing=True
        )
    autotrade_scheduler.add_job(
        engine_lease.leased(monitor_open_positions), "interval", seconds=15,
        kwargs={"context": app},
        id="monitor_open_positions", replace_existing=True
    )
    autotrade_scheduler.add_job(
        engine_lease.leased(scheduled_paper_exits_job), "interval", seconds=15,
        kwargs={"context": app},
        id="scheduled_paper_exits", replace_existing=True
    )
    autotrade_scheduler.add_job(
        engine_lease.leased(reconcile_all_accounts), "interval", minutes=1,
        kwargs={"context": app},
        id="reconcile_all_accounts", replace_existing=True
    )
    from health_monitor import scheduled_health_check_job, set_active_scheduler
    set_active_scheduler(autotrade_scheduler)
    autotrade_scheduler.add_job(
        engine_lease.leased(scheduled_health_check_job), "interval", minutes=1,
        kwargs={"context": app},
        id="scheduled_health_check", replace_existing=True
    )
    autotrade_scheduler.add_job(
        engine_lease.leased(scheduled_subscription_expiry_job), "interval", hours=24,
        kwargs={"context": app},
        id="scheduled_subscription_expiry", replace_existing=True
    )
    try:
        if engine_lease.wait_decision(5):  # seul le processus qui détient le bail réconcilie au démarrage
            reconcile_all_accounts(context=app, startup_mode=True)
    except Exception as e:
        logger.warning(f"Startup reconciliation failed: {e}")
    autotrade_scheduler.start()


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

from log_doctor import install_log_buffer
install_log_buffer()

logger = logging.getLogger(__name__)
if ADMIN_ID == 0:
    logger.warning("⚠️ ADMIN_ID == 0 : aucun ID Telegram administrateur numérique configuré.")

# =========================================================
# INDÉPENDANCE DU SITE VIS-À-VIS DU BOT
# =========================================================

def _site_can_survive_without_bot() -> bool:
    """Vrai si le site est hébergé dans CE processus et qu'on n'a pas demandé l'ancien comportement
    (BOT_EXIT_ON_FAILURE=1 : quitter si le bot échoue, pour qu'un superviseur relance tout)."""
    return (
        os.environ.get("DISABLE_EMBEDDED_WEB") != "1"
        and not os.environ.get("WEBHOOK_URL")
        and os.environ.get("BOT_EXIT_ON_FAILURE") != "1"
    )


def _keep_website_alive() -> None:
    """Garde le processus en vie pour le site, avec son propre moteur de fond (sans Telegram)."""
    import threading

    try:
        from headless_engine import maybe_start_embedded_engine

        maybe_start_embedded_engine(force=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Moteur du site non démarré: %s", exc)
    threading.Event().wait()


# =========================================================
# MAIN
# =========================================================

def main():
    if ADMIN_ID == 0:
        logger.warning("⚠️ ADMIN_ID == 0 au démarrage : veuillez définir un ADMIN_ID numérique dans l'environnement.")
    if os.environ.get("DISABLE_EMBEDDED_WEB") != "1" and not os.environ.get("WEBHOOK_URL"):
        try:
            from web_api_server import start_background_web_server
            web_port = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "3000")
            start_background_web_server(host="0.0.0.0", port=web_port)
        except Exception as web_err:
            logger.warning(f"Embedded web server early startup failed: {web_err}")

    if not TELEGRAM_TOKEN:
        if _site_can_survive_without_bot():
            logger.error("TELEGRAM_TOKEN manquant : bot Telegram désactivé, le site continue de fonctionner seul.")
            _keep_website_alive()
            return
        raise ValueError("❌ TELEGRAM_TOKEN manquant.")

    # Le bot et le site peuvent chacun exécuter les tâches de fond ; le bail garantit qu'un seul le fait à la fois.
    engine_lease.start("bot")

    logger.info("Initializing services...")

    alert_mgr = AlertManager.get_instance()

    async def post_init(application):
        from telegram import BotCommand
        commands = [
            BotCommand("menu", "Menu principal interactif"),
            BotCommand("help", "Aide et catégories de commandes"),
            BotCommand("analyse", "Menu analyse et signaux"),
            BotCommand("paper", "Menu paper trading"),
            BotCommand("autotrade", "Menu AutoTrade Binance"),
            BotCommand("live", "Menu Live Trading"),
            BotCommand("account", "Menu compte Binance"),
            BotCommand("settings", "Menu paramètres"),
            BotCommand("status", "État des services du bot"),
            BotCommand("upgrade", "Offre PRO"),
            BotCommand("support", "Support & contact"),
            BotCommand("myid", "Mon ID Telegram"),
        ]
        try:
            await application.bot.set_my_commands(commands)
            logger.info("Telegram menu commands updated.")
        except Exception as e:
            logger.warning(f"Failed to set Telegram commands: {e}")

        try:
            start_autotrade_scheduler(application)
        except Exception as e:
            logger.warning(f"Post-init AutoTrade scheduler check failed: {e}")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.bot_data["data_fetcher"] = DataFetcher.get_instance()

    # =====================================================
    # BACKGROUND TASKS
    # =====================================================

    try:
        start_weekly_report_scheduler(app)
        logger.info("Weekly scheduler started.")
    except Exception as e:
        logger.warning(f"Scheduler start failed: {e}")

    try:
        start_signal_monitoring(app)
        logger.info("Signal monitoring started.")
    except Exception as e:
        logger.warning(f"Signal monitoring failed: {e}")

    try:
        alert_mgr.start_monitoring(app)
        logger.info("Alert monitoring started.")
    except Exception as e:
        logger.warning(f"Alert monitoring failed: {e}")

    try:
        start_autotrade_scheduler(app)
        logger.info("AutoTrade scheduler started.")
    except Exception as e:
        logger.warning(f"AutoTrade scheduler failed: {e}")

    # =====================================================
    # COMMANDS
    # =====================================================

    handlers = [

        # ================= USER =================

        ("start", start),
        ("help", help_command),
        ("menu", menu_command),

        ("analyse", analyse),
        ("price", price),
        ("trend", trend),
        ("volatility", volatility),
        ("levels", levels),

        ("alert", alert),
        ("alerts", alerts),
        ("delalert", delalert),
        ("clearalerts", clearalerts),

        ("watchlist", watchlist_command),
        ("addwatch", addwatch),
        ("removewatch", removewatch),
        ("scan", scan),

        ("paper", paper),

        ("settings", settings),
        ("settimeframe", settimeframe),
        ("setstyle", setstyle),
        ("setlanguage", setlanguage),

        ("usage", usage),
        ("upgrade", upgrade),
        ("support", support),
        ("status", status_command),
        ("logs", logs_command),
        ("diag", logs_command),
        ("pay_binance", pay_binance),
        ("historique", historique),

        # ================= AUTOTRADE =================

        ("setapikeys", cmd_setapikeys),
        ("setsecurity", cmd_setsecurity),
        ("pin", cmd_setsecurity),
        ("confirmmanual", cmd_confirmmanual),
        ("autotrade", cmd_autotrade),
        ("periodic_analysis", cmd_periodic_analysis),
        ("config", cmd_config),
        ("positions", cmd_positions),
        ("close", cmd_close),
        ("pnl", cmd_pnl),
        ("account", cmd_account),
        ("balance", cmd_account),
        ("solde", cmd_account),
        ("history_trades", cmd_trade_history),
        ("setleverage", cmd_setleverage),
        ("setrisk", cmd_setrisk),
        ("setmaxpos", cmd_setmaxpos),
        ("setminscore", cmd_setminscore),
        ("setdailymaxloss", cmd_setdailymaxloss),
        ("setmarket", cmd_setmarket),
        ("settradingstyle", cmd_settradingstyle),
        ("setanalysistf", cmd_setanalysistf),
        ("setanalysisinterval", cmd_setanalysisinterval),
        ("settrailing", cmd_settrailing),
        ("setcooldown", cmd_setcooldown),
        ("settestnet", cmd_settestnet),
        ("setdca", cmd_setdca),
        ("whitelist", cmd_whitelist),
        ("blacklist", cmd_blacklist),
        ("emergency_stop", cmd_emergency_stop),
        ("editsignal", cmd_editsignal),
        ("clearsafe", cmd_clearsafe),
        ("safestatus", cmd_safestatus),

        # ================= LIVE TRADING =================

        ("live", cmd_live),
        ("live_long", cmd_live_long),
        ("live_short", cmd_live_short),
        ("live_close", cmd_live_close),
        ("live_cancel", cmd_live_cancel),

        # ================= ADMIN =================

        ("stats", stats),
        ("teddy", teddy),
        ("adduser", teddy),
        ("approve", teddy),
        ("broadcast", broadcast),
        ("switchapi", switchapi),
        ("find_memo", find_memo),
        ("confirm_payment", confirm_payment),
        ("refreshhistory", refreshhistory),
        ("clearhistory", clearhistory),
        ("deleteuser", deleteuser),
        ("exportsignals", exportsignals),
        ("dbquery", dbquery),
        ("cleanwaits", cleanwaits),
        ("trading_stats", admin_cmd_trading_stats),
        ("trades", admin_cmd_trades),
        ("forceclose", admin_cmd_forceclose),
    ]

    # =====================================================
    # REGISTER COMMANDS
    # =====================================================

    seen = set()

    # Handler spécial sans restriction d'accès

    # Handler public accessible sans restriction
    app.add_handler(CommandHandler("myid", myid_handler))

    for cmd, func in handlers:

        if cmd in seen:
            logger.warning(f"Duplicate command skipped: /{cmd}")
            continue

        seen.add(cmd)

        app.add_handler(CommandHandler(cmd, func))

    # =====================================================
    # TEXT INPUTS
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_pending_alert_input
        )
    )

    # =====================================================
    # CALLBACKS
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            menu_callback,
pattern="^(menu_(?!autotrade|live|market_mode|analysis_config|positions|trading_config|leverage|risk|maxpos|minscore|trailing|whitelist|blacklist|pnl|history_trades)|cmd_|paperdir_|clearalerts_)"
        )
    )
    
    app.add_handler(
        CallbackQueryHandler(
            symbol_callback,
            pattern="^(sympage_|symsel_|noop)"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            plan_callback,
            pattern="^plan_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            trading_callback_router,
            pattern="^(menu_autotrade|toggle_autotrade|menu_market_mode|set_market_|menu_analysis_config|toggle_periodic_analysis|run_periodic_analysis_now|set_analysis_|menu_positions|menu_trading_config|trading_open_|trading_reject_|trading_edit_|manual_trade_execute_|manual_trade_cancel_|menu_leverage|set_leverage_|menu_risk|set_risk_|menu_maxpos|set_maxpos_|menu_minscore|set_minscore_|menu_trailing|toggle_trailing|set_trailing_|menu_whitelist|menu_blacklist|menu_pnl|menu_history_trades)"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            live_callback_router,
            pattern="^(menu_live|live_)"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            terms_callback,
            pattern="^terms_"
        )
    )

    # =====================================================
    # PAYMENTS
    # =====================================================

    app.add_handler(PreCheckoutQueryHandler(pre_checkout))

    app.add_handler(
        MessageHandler(
            filters.SUCCESSFUL_PAYMENT,
            successful_payment
        )
    )

    # =====================================================
    # START BOT
    # =====================================================

    logger.info("Bitsure Teddy started successfully.")

    # =====================================================
    # START WEBSOCKET
    # =====================================================

    try:
        DataFetcher.get_instance().start_websocket()
        logger.info("Realtime websocket started.")
    except Exception as e:
        logger.warning(f"Websocket startup failed: {e}")

    # =====================================================
    # WEBHOOK / POLLING
    # =====================================================

    webhook_url = os.environ.get("WEBHOOK_URL")

    if webhook_url:

        logger.info(f"Starting webhook mode: {webhook_url}")

        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", "8443")),
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{webhook_url}/{TELEGRAM_TOKEN}",
        )

    else:
        if os.environ.get("DISABLE_EMBEDDED_WEB") != "1":
            try:
                from web_api_server import start_background_web_server
                web_port = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "3000")
                start_background_web_server(host="0.0.0.0", port=web_port)
            except Exception as web_err:
                logger.warning(f"Embedded web server startup failed: {web_err}")

        logger.info("Starting polling mode.")

        try:
            app.run_polling(
                drop_pending_updates=True
            )
        except Exception as bot_err:
            # Une panne du bot (réseau Telegram, conflit de polling...) ne doit pas emporter le site.
            if not _site_can_survive_without_bot():
                raise
            logger.critical("Le bot Telegram s'est arrêté (%s) : le site continue de fonctionner seul.", bot_err)
            engine_lease.stop()  # libère le bail pour que le moteur du site reprenne les tâches de fond
            _keep_website_alive()
# =========================================================
# ENTRYPOINT
# =========================================================

if __name__ == "__main__":
    main()
