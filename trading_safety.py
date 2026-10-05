"""Safety-first guards for real trading actions.

This module centralizes checks that must run before sending orders to Binance.
It separates critical lock (`safety_lock`) from temporary warnings (`safety_warn`),
supports TTL auto-downgrade from critical lock to warning, and queues or sends
user Telegram notifications.
"""

import asyncio
import os
import time
from collections import deque
from contextlib import contextmanager
from typing import Optional

from config import SIGNAL_VALIDITY_SECONDS, DEFAULT_SAFETY_LOCK_TTL_SECONDS
from database import get_connection
from trading_config import TradingConfig, update_config
from trading_logger import get_trading_logger

logger = get_trading_logger("trading_safety")

# File asynchrone de notifications lorsque context.bot n'est pas disponible immédiatement
_pending_safety_notifications: deque[tuple[int, str]] = deque(maxlen=500)


class SafetyError(Exception):
    """Raised when a critical action must be refused for safety."""


def _dispatch_or_queue_notification(user_id: int, text: str, context=None) -> None:
    """Envoie la notification Telegram via context.bot si disponible, sinon l'empile."""
    bot = getattr(context, "bot", None) if context is not None else None
    if bot is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(bot.send_message(chat_id=user_id, text=text))
            return
        except RuntimeError:
            pass
        except Exception as exc:
            logger.warning("Failed to schedule safety notification for user=%s: %s", user_id, exc)
    _pending_safety_notifications.append((int(user_id), text))


async def flush_safety_notifications(context) -> int:
    """Vide la file de notifications safety en attente (appelable par un job scheduler)."""
    bot = getattr(context, "bot", None) if context is not None else None
    if bot is None:
        return 0
    sent = 0
    while _pending_safety_notifications:
        uid, text = _pending_safety_notifications.popleft()
        try:
            await bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception as exc:
            logger.warning("Failed to send queued safety notification user=%s: %s", uid, exc)
    return sent


def engage_safe_mode(user_id: int, reason: str, context=None) -> TradingConfig:
    """Active le verrouillage critique (safety_lock) sans détruire les signaux en base.

    Désactive AutoTrade, conserve l'analyse en lecture seule, journalise l'incident
    sans faire d'UPDATE destructif sur `signals`, et notifie l'utilisateur.
    """
    now = time.time()
    logger.critical(
        "SAFE_MODE_ENGAGED user=%s reason=%s (pending signals preserved, protected by assert_trading_allowed)",
        user_id,
        reason,
    )
    cfg = update_config(
        user_id,
        auto_trade=False,
        safety_lock=True,
        safety_lock_reason=reason,
        safety_lock_at=now,
    )
    msg = (
        "🚨 ALERTE SÉCURITÉ — SAFE MODE ACTIVÉ (Verrouillage Critique)\n\n"
        f"• Raison : {reason}\n"
        "• Impact : AutoTrade désactivé, ouverture d'ordres bloquée, analyse périodique maintenue en lecture seule.\n"
        "• Résolution :\n"
        "  1. Vérifie l'état détaillé avec /safestatus\n"
        "  2. Déverrouille manuellement avec /clearsafe <code_securite>"
    )
    _dispatch_or_queue_notification(user_id, msg, context=context)
    return cfg


def engage_safety_warn(user_id: int, reason: str, context=None) -> TradingConfig:
    """Active un avertissement temporaire (safety_warn) auto-effacé au prochain succès."""
    now = time.time()
    logger.warning("SAFETY_WARN_ENGAGED user=%s reason=%s", user_id, reason)
    cfg = update_config(
        user_id,
        safety_warn=True,
        safety_warn_reason=reason,
        safety_warn_at=now,
    )
    msg = (
        "⚠️ AVERTISSEMENT SÉCURITÉ TEMPORAIRE (safety_warn)\n\n"
        f"• Raison : {reason}\n"
        "• Impact : Surveillance accrue suite à un incident transitoire (réseau / rate-limit / ordre protecteur). "
        "Sera levé automatiquement au prochain cycle réussi.\n"
        "• Étapes : Consulte /safestatus ou utilise /clearsafe <code_securite> pour acquitter immédiatement."
    )
    _dispatch_or_queue_notification(user_id, msg, context=context)
    return cfg


def clear_safety_warn(user_id: int) -> Optional[TradingConfig]:
    """Efface automatiquement safety_warn après une opération nominale réussie."""
    try:
        return update_config(
            user_id,
            safety_warn=False,
            safety_warn_reason=None,
            safety_warn_at=None,
        )
    except Exception as exc:
        logger.debug("clear_safety_warn ignored user=%s: %s", user_id, exc)
        return None


def assert_trading_allowed(config: TradingConfig, *, require_auto_trade: bool = False) -> None:
    """Vérifie si le trading est autorisé, avec gestion du TTL sur safety_lock."""
    now = time.time()
    if config.safety_lock:
        ttl = int(getattr(config, "safety_lock_ttl_seconds", DEFAULT_SAFETY_LOCK_TTL_SECONDS) or 0)
        lock_at = float(config.safety_lock_at or 0.0)
        if ttl > 0 and lock_at > 0.0 and now > (lock_at + ttl):
            downgrade_reason = f"Downgrade auto après expiration TTL ({ttl}s): {config.safety_lock_reason or 'safe_mode'}"
            logger.warning(
                "SAFE_MODE_TTL_EXPIRED user=%s lock_at=%s ttl=%s -> downgrading to safety_warn",
                config.user_id,
                lock_at,
                ttl,
            )
            config.safety_lock = False
            config.safety_warn = True
            config.safety_warn_reason = downgrade_reason
            config.safety_warn_at = now
            try:
                update_config(
                    config.user_id,
                    safety_lock=False,
                    safety_lock_reason=None,
                    safety_lock_at=None,
                    safety_warn=True,
                    safety_warn_reason=downgrade_reason,
                    safety_warn_at=now,
                )
            except Exception as exc:
                logger.warning("Failed to persist TTL downgrade for user=%s: %s", config.user_id, exc)
        else:
            reason_str = config.safety_lock_reason or "anomalie critique détectée"
            raise SafetyError(f"Safe mode actif ({reason_str}). Utilise /safestatus ou /clearsafe <code>.")

    if require_auto_trade and not config.auto_trade:
        raise SafetyError("AutoTrade est désactivé.")


def signal_age_seconds(signal: dict) -> Optional[float]:
    created_at = signal.get("created_at")
    if created_at in (None, ""):
        return None
    try:
        return time.time() - float(created_at)
    except (TypeError, ValueError):
        return None


def validate_signal_freshness(signal: dict, *, max_age_seconds: int = SIGNAL_VALIDITY_SECONDS) -> None:
    age = signal_age_seconds(signal)
    if age is None:
        raise SafetyError("Signal sans horodatage fiable.")
    if age < -5:
        raise SafetyError("Signal horodaté dans le futur.")
    if age > max_age_seconds:
        raise SafetyError(f"Signal obsolète ({int(age)}s > {max_age_seconds}s).")


@contextmanager
def user_trading_lock(user_id: int):
    """PostgreSQL advisory lock serializing critical trading operations per user."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (int(user_id),))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reserve_signal_for_execution(signal_id: str, user_id: int, allowed_statuses: tuple[str, ...]) -> dict:
    """Atomically move a signal to processing and return its current row.

    Accepts 'skipped' in re-entry when a signal was previously skipped due to safe_mode
    and the safe mode has since been lifted.
    """
    effective_statuses = set(allowed_statuses)
    effective_statuses.add("skipped")

    with user_trading_lock(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE signals
                SET status = 'processing'
                WHERE id = %s
                  AND user_id = %s
                  AND (
                        status = ANY(%s)
                        OR (status = 'skipped' AND COALESCE(rejection_reason, '') LIKE 'safe_mode:%%')
                      )
                RETURNING id, user_id, symbol, direction, entry_price, sl, tp, score,
                          status, timeframe, signal_type, created_at
                """,
                (signal_id, user_id, list(effective_statuses)),
            )
            row = cur.fetchone()
            if not row:
                raise SafetyError("Signal déjà traité, expiré ou dans un état non exécutable.")
            cols = [
                "id", "user_id", "symbol", "direction", "entry_price", "sl", "tp", "score",
                "status", "timeframe", "signal_type", "created_at",
            ]
            return dict(zip(cols, row))


def mark_signal_refused(signal_id: str, reason: str) -> None:
    """Marque un signal bloqué avec status='skipped' (réversible si safe_mode)."""
    normalized_reason = reason or "Validation refusée"
    if "safe mode" in normalized_reason.lower() and not normalized_reason.lower().startswith("safe_mode:"):
        normalized_reason = f"safe_mode: {normalized_reason}"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE signals SET status = 'skipped', rejection_reason = %s WHERE id = %s",
                (normalized_reason, signal_id),
            )
        conn.commit()
    finally:
        conn.close()
