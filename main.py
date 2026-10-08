#!/usr/bin/env python3
"""
Bitsure Teddy - Main Entry Point
"""

import logging
import os

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from config import TELEGRAM_TOKEN
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

def start_autotrade_scheduler(app):
    global autotrade_scheduler
    if autotrade_scheduler is not None and getattr(autotrade_scheduler, "running", False):
        app.bot_data["autotrade_scheduler"] = autotrade_scheduler
        return
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    autotrade_scheduler = AsyncIOScheduler(timezone="UTC")
    app.bot_data["autotrade_scheduler"] = autotrade_scheduler
    autotrade_scheduler.add_job(
        scheduled_signal_scan, "interval", seconds=20,
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
            scheduled_market_analysis, "interval", minutes=interval,
            kwargs={"context": app, "interval_minutes": interval},
            id=f"market_analysis_{interval}m", replace_existing=True
        )
    autotrade_scheduler.add_job(
        monitor_open_positions, "interval", seconds=15,
        kwargs={"context": app},
        id="monitor_open_positions", replace_existing=True
    )
    autotrade_scheduler.add_job(
        reconcile_all_accounts, "interval", minutes=1,
        kwargs={"context": app},
        id="reconcile_all_accounts", replace_existing=True
    )
    from health_monitor import scheduled_health_check_job, set_active_scheduler
    set_active_scheduler(autotrade_scheduler)
    autotrade_scheduler.add_job(
        scheduled_health_check_job, "interval", minutes=1,
        kwargs={"context": app},
        id="scheduled_health_check", replace_existing=True
    )
    try:
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

# =========================================================
# MAIN
# =========================================================

def main():
    if os.environ.get("DISABLE_EMBEDDED_WEB") != "1" and not os.environ.get("WEBHOOK_URL"):
        try:
            from web_api_server import start_background_web_server
            web_port = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "3000")
            start_background_web_server(host="0.0.0.0", port=web_port)
        except Exception as web_err:
            logger.warning(f"Embedded web server early startup failed: {web_err}")

    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_TOKEN manquant.")

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

        app.run_polling(
            drop_pending_updates=True
        )
# =========================================================
# ENTRYPOINT
# =========================================================

if __name__ == "__main__":
    main()
