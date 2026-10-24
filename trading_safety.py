"""Safety-first guards for real trading actions.

This module centralizes checks that must run before sending orders to Binance.
It separates critical lock (`safety_lock`) from temporary warnings (`safety_warn`),
sends a one-time reminder when a critical lock persists beyond the TTL, and queues
or sends user Telegram notifications.
"""

import asyncio
import os
import re
import threading
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


def engage_safe_mode(
    user_id: int,
    reason: str,
    context=None,
    *,
    disable_autotrade: bool = True,
    **_kwargs,
) -> TradingConfig:
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
    updates = {
        "safety_lock": True,
        "safety_lock_reason": reason,
        "safety_lock_at": now,
        "safety_lock_reminded": False,
    }
    if disable_autotrade:
        updates["auto_trade"] = False
    cfg = update_config(user_id, **updates)
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


# ── Anti-spam des avertissements temporaires (notification uniquement) ────────────────────────
# Un même problème ne doit produire qu'un message Telegram par fenêtre, même si le texte d'erreur varie
# ou si un autre cycle réussi efface le flag persistant entre-temps.
SAFETY_WARN_NOTIFY_COOLDOWN_SECONDS = int(os.getenv("SAFETY_WARN_NOTIFY_COOLDOWN_SECONDS", "1800"))   # 30 min
SAFETY_WARN_LOCK_COOLDOWN_SECONDS = int(os.getenv("SAFETY_WARN_LOCK_COOLDOWN_SECONDS", "21600"))      # 6 h (verrou manuel déjà connu)
_warn_notify_state: dict[tuple[int, str], dict] = {}
_warn_notify_lock = threading.Lock()


def _classify_warn(reason: str) -> tuple[str, str, Optional[str]]:
    """Retourne (clé_de_déduplication, type, symbole) à partir du texte de raison."""
    text = reason or ""
    m = re.search(r"\(([A-Z0-9]{5,20})\)", text)
    symbol = m.group(1) if m else None
    low = text.lower()
    if "safe mode actif" in low or "safe mode" in low and "refusé" in low:
        kind = "lock_blocked"
    elif "déplacement sl" in low or "mise à jour sl" in low:
        kind = "sl_move_failed"
    elif "absent côté binance" in low or "ordre protecteur" in low:
        kind = "protective_missing"
    elif "réseau" in low or "api" in low or "rate" in low or "timeout" in low:
        kind = "network"
    else:
        kind = "other"
    if kind == "other":
        # Sans catégorie connue : on neutralise les chiffres variables pour ne pas contourner la déduplication.
        key = "other:" + re.sub(r"[0-9.]+", "#", low)[:120]
    else:
        key = f"{kind}:{symbol or '*'}"
    return key, kind, symbol


def _should_notify_warn(user_id: int, key: str, kind: str) -> tuple[bool, int]:
    """(envoyer ?, nombre d'avertissements identiques supprimés depuis le dernier envoi)."""
    now = time.time()
    cooldown = SAFETY_WARN_LOCK_COOLDOWN_SECONDS if kind == "lock_blocked" else SAFETY_WARN_NOTIFY_COOLDOWN_SECONDS
    with _warn_notify_lock:
        st = _warn_notify_state.get((int(user_id), key))
        if st is not None and (now - st["sent_at"]) < cooldown:
            st["suppressed"] += 1
            return False, 0
        suppressed = st["suppressed"] if st else 0
        _warn_notify_state[(int(user_id), key)] = {"sent_at": now, "suppressed": 0}
        if len(_warn_notify_state) > 500:   # borne mémoire
            for k in sorted(_warn_notify_state, key=lambda k: _warn_notify_state[k]["sent_at"])[:100]:
                _warn_notify_state.pop(k, None)
        return True, suppressed


def _build_warn_message(kind: str, symbol: Optional[str], reason: str, suppressed: int) -> str:
    """Message en 3 blocs : ce qui s'est passé / conséquence / action concrète."""
    sym = f" sur {symbol}" if symbol else ""
    if kind == "lock_blocked":
        what = f"Le stop-loss{sym} n'a pas pu être déplacé : le Safe Mode est actif (verrouillage manuel)."
        impact = ("Aucun ordre n'a été envoyé à Binance. Les ordres déjà placés ne sont pas modifiés, "
                  "mais le stop-loss ne suit plus le prix tant que le verrou reste actif.")
        action = ("Rien à faire si le verrou est voulu. Pour reprendre la gestion automatique : "
                  "/clearsafe <code_securite>. État détaillé : /safestatus. "
                  "Ce message n'est plus répété pendant 6 h.")
    elif kind == "sl_move_failed":
        what = f"Le déplacement du stop-loss{sym} a échoué côté Binance."
        impact = "L'ancien stop-loss reste en place. Nouvelle tentative automatique au prochain cycle."
        action = "Aucune action immédiate. Si cela persiste, vérifie /safestatus. Ce message n'est pas répété avant 30 min."
    elif kind == "protective_missing":
        what = f"Un ordre protecteur (SL/TP){sym} est introuvable sur Binance."
        impact = "La position peut être insuffisamment protégée. Le bot tente de le reposer au prochain cycle."
        action = "Vérifie la position dans Binance et /safestatus. Ce message n'est pas répété avant 30 min."
    elif kind == "network":
        what = "Erreur réseau ou limite d'appels (rate-limit) avec l'API Binance."
        impact = "Incident généralement passager. Nouvelle tentative automatique au prochain cycle."
        action = "Aucune action nécessaire. Si cela dure, consulte /safestatus. Ce message n'est pas répété avant 30 min."
    else:
        what = "Un incident temporaire a été détecté par la surveillance."
        impact = "Surveillance accrue. L'avertissement est levé automatiquement au prochain cycle réussi."
        action = "Consulte /safestatus ou acquitte avec /clearsafe <code_securite>. Ce message n'est pas répété avant 30 min."
    extra = f"\n\n({suppressed} avertissement(s) identique(s) regroupé(s) depuis le dernier message.)" if suppressed else ""
    return (
        "⚠️ AVERTISSEMENT SÉCURITÉ TEMPORAIRE\n\n"
        f"• Quoi : {what}\n"
        f"• Conséquence : {impact}\n"
        f"• Action : {action}\n\n"
        f"Détail technique : {reason[:300]}"
        f"{extra}"
    )


def engage_safety_warn(user_id: int, reason: str, context=None) -> TradingConfig:
    """Active un avertissement temporaire (safety_warn) auto-effacé au prochain succès.

    L'état persistant (safety_warn, raison, horodatage) est inchangé. Seule la notification Telegram est
    dédupliquée par (utilisateur, type de problème, symbole) avec un délai de grâce, pour éviter les rafales.
    """
    now = time.time()
    logger.warning("SAFETY_WARN_ENGAGED user=%s reason=%s", user_id, reason)
    current_cfg = None
    try:
        from trading_config import get_config
        current_cfg = get_config(user_id)
    except Exception:
        pass
    already_active_same = bool(
        current_cfg is not None
        and getattr(current_cfg, "safety_warn", False)
        and getattr(current_cfg, "safety_warn_reason", None) == reason
        and (now - float(getattr(current_cfg, "safety_warn_at", 0.0) or 0.0)) < 900
    )

    cfg = update_config(
        user_id,
        safety_warn=True,
        safety_warn_reason=reason,
        safety_warn_at=(
            (getattr(current_cfg, "safety_warn_at", now) or now) if already_active_same else now
        ),
    )

    key, kind, symbol = _classify_warn(reason)
    send, suppressed = _should_notify_warn(user_id, key, kind)
    if send:
        _dispatch_or_queue_notification(user_id, _build_warn_message(kind, symbol, reason, suppressed), context=context)
    else:
        logger.info("SAFETY_WARN_NOTIFY_SUPPRESSED user=%s key=%s", user_id, key)
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
    """Vérifie si le trading est autorisé. Tant que safety_lock=True, lève SafetyError."""
    now = time.time()
    if config.safety_lock:
        ttl = int(getattr(config, "safety_lock_ttl_seconds", DEFAULT_SAFETY_LOCK_TTL_SECONDS) or 0)
        lock_at = float(config.safety_lock_at or 0.0)
        reminded = bool(getattr(config, "safety_lock_reminded", False))
        if ttl > 0 and lock_at > 0.0 and now > (lock_at + ttl) and not reminded:
            config.safety_lock_reminded = True
            try:
                update_config(config.user_id, safety_lock_reminded=True)
            except Exception as exc:
                logger.warning("Failed to persist safety_lock_reminded for user=%s: %s", config.user_id, exc)
            reason_str = config.safety_lock_reason or "anomalie critique détectée"
            reminder_msg = (
                "🔔 RAPPEL SÉCURITÉ — SAFE MODE TOUJOURS ACTIF\n\n"
                f"• Raison : {reason_str}\n"
                f"• Durée écoulée : > {ttl}s\n"
                "• Action requise : Le verrouillage critique reste actif jusqu'à intervention manuelle via /clearsafe <code_securite>."
            )
            _dispatch_or_queue_notification(config.user_id, reminder_msg)
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
