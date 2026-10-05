"""
health_monitor.py
-----------------
Watchdog et vérificateur de santé automatique pour Bitsure Teddy.
Exécuté toutes les minutes pour surveiller l'état du bot sans interférer
avec le trading ni forcer de faux déblocages de sécurité.
"""

import time
import logging
from typing import Optional, Dict, Any

from database import get_connection
from trading_config import get_config
from trading_logger import get_trading_logger

logger = get_trading_logger("health_monitor")

_last_health_status: Dict[str, Any] = {}
_active_scheduler = None


def set_active_scheduler(scheduler) -> None:
    """Enregistre la référence directe au scheduler actif (évite le piège __main__ vs main)."""
    global _active_scheduler
    _active_scheduler = scheduler


def _resolve_scheduler(context=None):
    """Récupère l'instance d'APScheduler quel que soit le mode de lancement (`python main.py` ou import)."""
    if _active_scheduler is not None:
        return _active_scheduler
    if context is not None:
        bot_data = getattr(context, "bot_data", None)
        if isinstance(bot_data, dict) and bot_data.get("autotrade_scheduler") is not None:
            return bot_data["autotrade_scheduler"]
        app = getattr(context, "application", None)
        if app is not None and isinstance(getattr(app, "bot_data", None), dict):
            if app.bot_data.get("autotrade_scheduler") is not None:
                return app.bot_data["autotrade_scheduler"]
    import sys
    for mod_name in ("__main__", "main"):
        mod = sys.modules.get(mod_name)
        sched = getattr(mod, "autotrade_scheduler", None) if mod else None
        if sched is not None:
            return sched
    return None


def check_db_health() -> bool:
    """Vérifie que la connexion à la base de données PostgreSQL est valide."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
                return bool(row and row[0] == 1)
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[HealthMonitor] Échec connexion Database: {e}")
        return False


def check_binance_health(user_id: int) -> tuple[bool, Optional[str]]:
    """Vérifie la validité des identifiants et de la connexion Binance d'un utilisateur."""
    try:
        from binance_manager import get_binance_credentials, get_price, BinanceClientError
        creds = get_binance_credentials(user_id)
        if not creds or not creds.get("api_key") or not creds.get("api_secret"):
            return True, "Aucune clé configurée"
        if not creds.get("is_valid"):
            return False, "Clés API masquées ou invalidées"
        
        cfg = get_config(user_id)
        # Test léger d'un appel réseau sans ordre (fetch ticker price)
        get_price(user_id, "BTCUSDT", market_type=cfg.market_type)
        return True, "Connexion Binance opérationnelle"
    except Exception as e:
        return False, f"Erreur réseau/client Binance: {e}"


def run_health_check(context=None) -> Dict[str, Any]:
    """
    Exécute l'ensemble des vérifications de santé du bot.
    Peut être appelé manuellement ou automatiquement par APScheduler.
    """
    from execution_engine import get_configured_analysis_intervals, scheduled_market_analysis, scheduled_signal_scan
    from position_manager import monitor_open_positions, reconcile_all_accounts

    global _last_health_status
    report = {
        "timestamp": time.time(),
        "db_ok": False,
        "scheduler_running": False,
        "repaired_jobs": [],
        "user_statuses": {},
        "recent_errors_count": 0,
        "last_analysis_time": None,
        "last_trade_time": None,
    }

    # 1. Connexion Base de données
    report["db_ok"] = check_db_health()
    if not report["db_ok"]:
        logger.critical("[HealthMonitor] DATABASE DOWN !")
        _last_health_status = report
        return report

    # 2. Vérification APScheduler et Restauration si Job Disparu
    autotrade_scheduler = _resolve_scheduler(context)
    if autotrade_scheduler and getattr(autotrade_scheduler, "running", False):
        report["scheduler_running"] = True
        existing_job_ids = {job.id for job in autotrade_scheduler.get_jobs()}

        # Restauration sûre des jobs de base s'ils ont disparu du scheduler sans raison
        required_jobs = {
            "scheduled_signal_scan": (scheduled_signal_scan, {"seconds": 20}),
            "monitor_open_positions": (monitor_open_positions, {"seconds": 15}),
            "reconcile_all_accounts": (reconcile_all_accounts, {"minutes": 1}),
        }

        for job_id, (func, kwargs) in required_jobs.items():
            if job_id not in existing_job_ids:
                logger.warning(f"[HealthMonitor] Job manquant détecté '{job_id}'. Restauration en cours...")
                try:
                    autotrade_scheduler.add_job(
                        func, "interval", **kwargs,
                        kwargs={"context": context},
                        id=job_id, replace_existing=True
                    )
                    report["repaired_jobs"].append(job_id)
                except Exception as e:
                    logger.error(f"[HealthMonitor] Échec restauration job {job_id}: {e}")

        # Restauration des jobs d'analyse périodique configurés
        try:
            intervals = get_configured_analysis_intervals()
            for interval in intervals:
                an_job_id = f"market_analysis_{interval}m"
                if an_job_id not in existing_job_ids:
                    logger.warning(f"[HealthMonitor] Job d'analyse manquant '{an_job_id}'. Restauration...")
                    autotrade_scheduler.add_job(
                        scheduled_market_analysis, "interval", minutes=interval,
                        kwargs={"context": context, "interval_minutes": interval},
                        id=an_job_id, replace_existing=True
                    )
                    report["repaired_jobs"].append(an_job_id)
        except Exception as e:
            logger.error(f"[HealthMonitor] Échec vérification des jobs d'analyse: {e}")
    else:
        report["scheduler_running"] = False
        logger.critical("[HealthMonitor] AUTOTRADE SCHEDULER STOPPED OR NOT INITIALIZED !")

    # 3. Métriques d'activité (dernière analyse & dernier trade) & 4. Liste des utilisateurs
    cur_users = []
    conn = get_connection()
    try:
        try:
            with conn.cursor() as cur:
                # Dernier signal généré (horodatage créé)
                cur.execute("SELECT MAX(created_at) FROM signals")
                row = cur.fetchone()
                if row and row[0]:
                    report["last_analysis_time"] = float(row[0])

                # Dernier trade ouvert ou fermé
                cur.execute("SELECT MAX(opened_at) FROM trades")
                row_tr = cur.fetchone()
                if row_tr and row_tr[0]:
                    report["last_trade_time"] = float(row_tr[0])

                # Erreurs récentes dans les signaux (signaux rejetés dernière heure)
                one_hour_ago = time.time() - 3600
                cur.execute("SELECT COUNT(*) FROM signals WHERE status = 'rejected' AND created_at > %s", (one_hour_ago,))
                row_err = cur.fetchone()
                if row_err:
                    report["recent_errors_count"] = row_err[0]
        except Exception as e:
            logger.error(f"[HealthMonitor] Erreur lecture métriques: {e}")

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT user_id FROM trading_config UNION SELECT user_id FROM users")
                cur_users = [row[0] for row in cur.fetchall() if row[0] is not None]
        except Exception as e:
            logger.error(f"[HealthMonitor] Erreur lecture liste utilisateurs: {e}")
    finally:
        conn.close()

    # 4. Cohérence des états de sécurité & connexions utilisateurs
    try:
        for user_id in cur_users:
            cfg = get_config(user_id)
            binance_ok, binance_msg = check_binance_health(user_id)
            report["user_statuses"][user_id] = {
                "auto_trade": cfg.auto_trade,
                "binance_ok": binance_ok,
                "binance_msg": binance_msg,
            }
    except Exception as e:
        logger.error(f"[HealthMonitor] Erreur vérification configs utilisateurs: {e}")

    _last_health_status = report
    return report


async def scheduled_health_check_job(context=None):
    """Job APScheduler exécuté toutes les minutes."""
    try:
        run_health_check(context=context)
    except Exception as e:
        logger.error(f"[HealthMonitor] Exception non capturée dans le watchdog: {e}")


def get_last_health_status() -> Dict[str, Any]:
    return _last_health_status
