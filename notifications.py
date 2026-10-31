"""
Notifications utilisateur indépendantes de Telegram.

Chaque notification (position fermée, alerte de prix, mode sécurité, rapport...) est TOUJOURS enregistrée en base
(`user_notifications`) et visible dans la cloche du site, qu'un bot Telegram soit actif ou non. L'envoi Telegram est un
canal supplémentaire « au mieux » : il n'est tenté que pour les comptes liés à un chat Telegram (user_id > 0) et son
échec ne casse jamais une tâche.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_PER_USER = 200
MAX_TEXT = 2000
_table_ready = False


def _plain(text: str) -> str:
    """Retire le balisage Markdown Telegram (*gras*, `code`) pour l'affichage dans le site."""
    return re.sub(r"[*`]", "", str(text or "")).strip()[:MAX_TEXT]


def _ensure_table(cur) -> None:
    global _table_ready
    if _table_ready:
        return
    cur.execute(
        "CREATE TABLE IF NOT EXISTS user_notifications (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, "
        "created_at DOUBLE PRECISION NOT NULL, kind TEXT NOT NULL DEFAULT 'info', text TEXT NOT NULL, "
        "read_at DOUBLE PRECISION)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_notifications_user ON user_notifications (user_id, id DESC)")
    _table_ready = True


def store_notification(user_id: int, text: str, kind: str = "info") -> bool:
    """Enregistre une notification in-app. Ne lève jamais (retourne False en cas d'échec)."""
    try:
        from database import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                _ensure_table(cur)
                cur.execute(
                    "INSERT INTO user_notifications (user_id, created_at, kind, text) VALUES (%s, %s, %s, %s)",
                    (int(user_id), time.time(), str(kind)[:30], _plain(text)),
                )
                cur.execute(
                    "DELETE FROM user_notifications WHERE user_id = %s AND id NOT IN "
                    "(SELECT id FROM user_notifications WHERE user_id = %s ORDER BY id DESC LIMIT %s)",
                    (int(user_id), int(user_id), MAX_PER_USER),
                )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("notification in-app non enregistrée (user=%s): %s", user_id, exc)
        return False


async def notify_user(context: Any, user_id: int, text: str, kind: str = "info", parse_mode: Optional[str] = None,
                      reply_markup: Any = None) -> None:
    """Enregistre la notification (site) puis tente Telegram si le compte y est lié. Ne lève jamais."""
    try:
        await asyncio.to_thread(store_notification, int(user_id), text, kind)
    except Exception as exc:  # noqa: BLE001
        logger.warning("notify_user: stockage impossible: %s", exc)
    bot = getattr(context, "bot", None) if context is not None else None
    if bot is None or int(user_id) <= 0:
        return  # compte du site sans chat Telegram, ou aucun bot disponible
    kwargs: Dict[str, Any] = {"chat_id": int(user_id), "text": text}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    try:
        await bot.send_message(**kwargs)
    except Exception:  # noqa: BLE001 (ex. Markdown invalide) : nouvel essai en texte brut
        try:
            await bot.send_message(chat_id=int(user_id), text=_plain(text))
        except Exception as exc:  # noqa: BLE001
            logger.warning("notification Telegram ignorée (user=%s): %s", user_id, exc)


def list_notifications(user_id: int, limit: int = 30) -> Dict[str, Any]:
    from database import get_connection

    limit = max(1, min(int(limit or 30), 100))
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _ensure_table(cur)
            cur.execute(
                "SELECT id, created_at, kind, text, read_at FROM user_notifications WHERE user_id = %s "
                "ORDER BY id DESC LIMIT %s", (int(user_id), limit),
            )
            items: List[Dict[str, Any]] = [
                {"id": r[0], "created_at": r[1], "kind": r[2], "text": r[3], "read": r[4] is not None}
                for r in cur.fetchall()
            ]
            cur.execute("SELECT COUNT(*) FROM user_notifications WHERE user_id = %s AND read_at IS NULL", (int(user_id),))
            unread = int(cur.fetchone()[0])
        conn.commit()
        return {"items": items, "unread": unread}
    finally:
        conn.close()


def mark_read(user_id: int, ids: Optional[List[int]] = None) -> int:
    """Marque comme lues les notifications données (ou toutes si `ids` est vide). Retourne le nombre modifié."""
    from database import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _ensure_table(cur)
            if ids:
                clean = [int(i) for i in ids][:200]
                cur.execute(
                    "UPDATE user_notifications SET read_at = %s WHERE user_id = %s AND read_at IS NULL AND id = ANY(%s)",
                    (time.time(), int(user_id), clean),
                )
            else:
                cur.execute("UPDATE user_notifications SET read_at = %s WHERE user_id = %s AND read_at IS NULL",
                            (time.time(), int(user_id)))
            changed = cur.rowcount
        conn.commit()
        return int(changed or 0)
    finally:
        conn.close()
