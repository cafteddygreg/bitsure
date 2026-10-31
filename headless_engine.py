"""Moteur Auto-Trade « embarqué » pour le service web (sans polling Telegram).

Pourquoi : activer Auto-Trade depuis le site ne fait qu'écrire `auto_trade = TRUE` en base.
Ce sont les tâches planifiées (scan des signaux, analyse, suivi des positions...) qui passent
réellement les ordres. Historiquement elles ne tournaient que dans le processus du bot
Telegram (main.py). Si ce processus n'existe pas, le site affiche « ON » mais rien ne se passe.

Activation (opt-in, car ce moteur peut passer de vrais ordres) :
    AUTOTRADE_EMBEDDED=1   sur le service qui exécute web_api_server.py / server.ts

Sécurité contre un double moteur : on lit le « battement de cœur » écrit par le scan des signaux.
Si un autre moteur (le bot) tourne déjà, celui-ci ne démarre pas ; s'il tombe, celui-ci prend le relais.
Les ouvertures d'ordres restent protégées par la réservation atomique des signaux en base.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

import engine_lease

logger = logging.getLogger("headless_engine")

_STARTED = False
_LOCK = threading.Lock()

# Délai avant de décider qu'aucun autre moteur ne tourne (laisse le temps au bot de démarrer).
GRACE_SECONDS = int(os.environ.get("AUTOTRADE_EMBEDDED_GRACE", "45") or 45)
# Un moteur est considéré hors ligne au-delà de ce délai sans battement de cœur.
STALE_SECONDS = 120
WATCH_INTERVAL_SECONDS = 60


class _SafeBot:
    """Enveloppe un telegram.Bot : une notification qui échoue ne doit jamais casser une tâche
    (ex. utilisateurs du site sans chat Telegram, user_id < 0, ou token absent)."""

    def __init__(self, bot=None):
        self._bot = bot

    def __getattr__(self, name):
        real = getattr(self._bot, name, None) if self._bot is not None else None

        async def _call(*args, **kwargs):
            if real is None:
                logger.debug("Telegram indisponible, appel ignoré: %s", name)
                return None
            try:
                return await real(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Notification Telegram ignorée (%s): %s", name, exc)
                return None

        return _call


class HeadlessContext:
    """Imite l'objet `Application` de python-telegram-bot utilisé comme `context` par les tâches."""

    def __init__(self, bot=None):
        self.bot = _SafeBot(bot)
        self.bot_data: dict = {}
        self.job_queue = None
        self.application = self


async def _paper_exits_job(context=None):
    try:
        from data_fetcher import DataFetcher
        from database import get_db
        from paper_trader import PaperTrader

        pt = PaperTrader.get_instance()
        rows = get_db().execute("SELECT DISTINCT symbol FROM paper_positions WHERE status = 'open'").fetchall()
        symbols = [str(r["symbol"]).upper() for r in rows if r and r.get("symbol")]
        if not symbols:
            return
        fetcher = DataFetcher.get_instance()
        for sym in symbols:
            try:
                info = fetcher.get_current_price(sym)
                price = float((info or {}).get("price") or 0.0)
                if price > 0:
                    pt.update_price(sym, price)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Paper price update skipped for %s: %s", sym, exc)
        pt.check_exits()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Paper exits job failed: %s", exc)


async def _subscription_expiry_job(context=None):
    try:
        from user_manager import UserManager

        UserManager.get_instance().expire_subscriptions()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Subscription expiry job failed: %s", exc)


def _build_bot():
    token = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    try:
        from telegram import Bot

        return Bot(token)  # simple client HTTP : pas de polling, donc pas de conflit avec le bot
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram.Bot indisponible, notifications désactivées: %s", exc)
        return None


def _run_engine() -> None:
    """Crée une boucle asyncio dédiée et y enregistre les mêmes tâches que main.start_autotrade_scheduler."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from execution_engine import (
        get_configured_analysis_intervals,
        scheduled_market_analysis,
        scheduled_signal_scan,
    )
    from health_monitor import scheduled_health_check_job, set_active_scheduler
    from position_manager import monitor_open_positions, reconcile_all_accounts

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ctx = HeadlessContext(_build_bot())

    # Un seul processus (site ou bot) exécute les tâches de fond : celui qui détient le bail (engine_lease.py).
    engine_lease.start("web")
    leased = engine_lease.leased

    try:
        if engine_lease.wait_decision(8):
            reconcile_all_accounts(context=ctx, startup_mode=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Réconciliation initiale échouée: %s", exc)

    # Prix temps réel (flux websocket) et alertes de prix : jusqu'ici démarrés uniquement par le bot.
    try:
        from data_fetcher import DataFetcher

        DataFetcher.get_instance().start_websocket()
    except Exception as exc:  # noqa: BLE001
        logger.info("Flux temps réel indisponible (repli REST): %s", exc)
    try:
        from alert_manager import AlertManager

        AlertManager.get_instance().start_monitoring(ctx)  # la boucle ne travaille que si ce processus a le bail
    except Exception as exc:  # noqa: BLE001
        logger.warning("Surveillance des alertes non démarrée: %s", exc)
    scheduler = AsyncIOScheduler(timezone="UTC", event_loop=loop)
    scheduler.add_job(leased(scheduled_signal_scan), "interval", seconds=20, kwargs={"context": ctx},
                      id="scheduled_signal_scan", replace_existing=True)
    try:
        intervals = get_configured_analysis_intervals()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Intervalles d'analyse par défaut (%s)", exc)
        intervals = [5, 10]
    for minutes in intervals:
        scheduler.add_job(leased(scheduled_market_analysis), "interval", minutes=minutes,
                          kwargs={"context": ctx, "interval_minutes": minutes},
                          id=f"market_analysis_{minutes}m", replace_existing=True)
    scheduler.add_job(leased(monitor_open_positions), "interval", seconds=15, kwargs={"context": ctx},
                      id="monitor_open_positions", replace_existing=True)
    scheduler.add_job(leased(_paper_exits_job), "interval", seconds=15, kwargs={"context": ctx},
                      id="scheduled_paper_exits", replace_existing=True)
    scheduler.add_job(leased(reconcile_all_accounts), "interval", minutes=1, kwargs={"context": ctx},
                      id="reconcile_all_accounts", replace_existing=True)
    set_active_scheduler(scheduler)
    scheduler.add_job(leased(scheduled_health_check_job), "interval", minutes=1, kwargs={"context": ctx},
                      id="scheduled_health_check", replace_existing=True)
    scheduler.add_job(leased(_subscription_expiry_job), "interval", hours=24, kwargs={"context": ctx},
                      id="scheduled_subscription_expiry", replace_existing=True)
    try:
        # Résultats (gagné/perdu) des signaux émis : alimente l'historique du site, comme dans le bot.
        from bot_handlers import check_signal_outcomes

        scheduler.add_job(leased(check_signal_outcomes), "interval", minutes=15, kwargs={"bot": ctx.bot},
                          id="signal_monitor", replace_existing=True)
    except Exception as exc:  # noqa: BLE001
        logger.info("Suivi des résultats de signaux indisponible dans le moteur du site: %s", exc)

    scheduler.start()
    logger.info("✅ Moteur Auto-Trade embarqué démarré (intervalles d'analyse: %s min)", intervals)
    loop.run_forever()


def _another_engine_alive() -> bool:
    try:
        from execution_engine import get_engine_heartbeat_age

        age = get_engine_heartbeat_age()
        return age is not None and age <= STALE_SECONDS
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lecture du battement de cœur impossible: %s", exc)
        return False


def _watchdog() -> None:
    global _STARTED
    time.sleep(GRACE_SECONDS)
    while True:
        try:
            if not _STARTED and not _another_engine_alive():
                with _LOCK:
                    if not _STARTED:
                        _STARTED = True
                        threading.Thread(target=_run_engine, name="autotrade-engine", daemon=True).start()
                        logger.info("Aucun moteur Auto-Trade détecté : démarrage du moteur embarqué.")
            elif not _STARTED:
                logger.info("Un moteur Auto-Trade externe est déjà actif : moteur embarqué en veille.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Watchdog moteur embarqué: %s", exc)
        time.sleep(WATCH_INTERVAL_SECONDS)


def maybe_start_embedded_engine(force: bool = False) -> bool:
    """À appeler au démarrage du serveur web.

    Le site héberge désormais son propre moteur PAR DÉFAUT (il ne dépend plus du bot) : désactivable avec
    AUTOTRADE_EMBEDDED=0. Le bail (engine_lease.py) garantit qu'un seul processus exécute les tâches, que le bot
    tourne ou non. `force=True` démarre sans délai de grâce (le bot vient d'échouer ou n'existe pas).
    """
    if str(os.environ.get("AUTOTRADE_EMBEDDED", "1")).strip().lower() in ("0", "false", "no", "off"):
        return False
    global GRACE_SECONDS
    if force:
        GRACE_SECONDS = 0
    threading.Thread(target=_watchdog, name="autotrade-watchdog", daemon=True).start()
    logger.info("AUTOTRADE_EMBEDDED activé : surveillance du moteur (délai de grâce %ss).", GRACE_SECONDS)
    return True
