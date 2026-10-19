"""
auth_security.py
----------------
Logique de sécurité d'authentification de Bitsure :
  - politique de mot de passe (changement et récupération) ;
  - politique de sessions (appareil personnel vs partagé/public, verrouillage d'inactivité) ;
  - liste / révocation des sessions.

Ce module ne dépend PAS du serveur HTTP : toutes les fonctions reçoivent un objet `db`
(compatible `get_db()` : `db.execute(sql, params)` avec placeholders `%s`) afin d'être testables.
Il réutilise les tables existantes (`web_accounts`, `web_sessions`, `security_events`) et n'ajoute que `web_devices`. Le hashing des mots de passe reste celui de web_api_server
(PBKDF2) : il est injecté par l'appelant, jamais dupliqué ici.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------
# Constantes de politique (surchargeables par variables d'environnement)
# ---------------------------------------------------------------------

def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, "").strip() or default))
    except ValueError:
        return default


PERSONAL_SESSION_SECONDS = _env_int("PERSONAL_SESSION_DAYS", 7) * 86400
PUBLIC_SESSION_MAX_SECONDS = _env_int("PUBLIC_SESSION_MAX_HOURS", 12) * 3600
PUBLIC_IDLE_TIMEOUT_SECONDS = _env_int("PUBLIC_IDLE_TIMEOUT_MINUTES", 30) * 60
ACTIVITY_TOUCH_INTERVAL_SECONDS = 60  # évite une écriture DB à chaque requête

SESSION_PERSONAL = "personal"
SESSION_PUBLIC = "public"
SESSION_PENDING = "pending"  # appareil non reconnu, choix pas encore fait : politique stricte par défaut

DEVICE_COOKIE_NAME = "bitsure_device"

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


# ---------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------

def _add_column(db, table: str, column_def: str) -> None:
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_def}")
    except Exception:
        try:  # moteurs sans IF NOT EXISTS (tests) : l'erreur « colonne existante » est ignorée
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        except Exception:
            pass


def ensure_schema(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS web_devices (
            user_id BIGINT NOT NULL,
            device_hash TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at DOUBLE PRECISION DEFAULT 0,
            last_seen_at DOUBLE PRECISION DEFAULT 0,
            PRIMARY KEY (user_id, device_hash)
        )
        """
    )
    ensure_session_columns(db)


def ensure_session_columns(db) -> None:
    """Colonnes ajoutées à web_sessions (idempotent ; aussi appelé à la création de session, comme token_hash)."""
    _add_column(db, "web_sessions", "session_type TEXT")
    _add_column(db, "web_sessions", "device_hash TEXT")
    _add_column(db, "web_sessions", "last_activity_at DOUBLE PRECISION DEFAULT 0")
    _add_column(db, "web_sessions", "locked_at DOUBLE PRECISION DEFAULT 0")
    _add_column(db, "web_sessions", "must_change_password INTEGER DEFAULT 0")


# ---------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------

def validate_password(password: str, email: str = "") -> List[str]:
    """Retourne la liste des codes de règles non respectées (vide = valide).

    Règles : 8–128 caractères, au moins une lettre et un chiffre, différent de l'adresse email.
    (L'inscription existante n'exige que 8 caractères : elle n'est volontairement pas modifiée.)
    """
    errors: List[str] = []
    pw = password or ""
    if len(pw) < PASSWORD_MIN_LENGTH:
        errors.append("TOO_SHORT")
    if len(pw) > PASSWORD_MAX_LENGTH:
        errors.append("TOO_LONG")
    if not re.search(r"[A-Za-z]", pw):
        errors.append("NEEDS_LETTER")
    if not re.search(r"\d", pw):
        errors.append("NEEDS_DIGIT")
    if email and pw.strip().lower() == email.strip().lower():
        errors.append("SAME_AS_EMAIL")
    return errors


PASSWORD_ERROR_MESSAGES = {
    "TOO_SHORT": f"Au moins {PASSWORD_MIN_LENGTH} caractères.",
    "TOO_LONG": f"Au plus {PASSWORD_MAX_LENGTH} caractères.",
    "NEEDS_LETTER": "Au moins une lettre.",
    "NEEDS_DIGIT": "Au moins un chiffre.",
    "SAME_AS_EMAIL": "Le mot de passe ne doit pas être votre adresse email.",
}


# ---------------------------------------------------------------------
# Rate limiting (en mémoire, même approche que le limiteur de login existant)
# ---------------------------------------------------------------------

class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: int):
        self.max_events = max_events
        self.window = window_seconds
        self._lock = threading.Lock()
        self._events: Dict[str, List[float]] = {}

    def _prune(self, key: str, now: float) -> List[float]:
        ts = [t for t in self._events.get(key, []) if t > now - self.window]
        if ts:
            self._events[key] = ts
        else:
            self._events.pop(key, None)
        return ts

    def check_and_record(self, key: str, now: Optional[float] = None) -> Tuple[bool, int]:
        """Enregistre l'événement si autorisé. Retourne (autorisé, secondes_avant_nouvel_essai)."""
        now = time.time() if now is None else now
        with self._lock:
            ts = self._prune(key, now)
            if len(ts) >= self.max_events:
                return False, max(1, int(ts[0] + self.window - now))
            ts.append(now)
            self._events[key] = ts
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


# ---------------------------------------------------------------------
# Appareils et sessions
# ---------------------------------------------------------------------

def hash_device_id(raw: str) -> str:
    return hashlib.sha256(("device:" + (raw or "")).encode("utf-8")).hexdigest()


def new_device_id() -> str:
    return secrets.token_hex(24)


def get_device_kind(db, user_id: int, device_hash: str) -> Optional[str]:
    if not device_hash:
        return None
    row = db.execute(
        "SELECT kind FROM web_devices WHERE user_id = %s AND device_hash = %s", (int(user_id), device_hash)
    ).fetchone()
    return str(row["kind"]) if row else None


def set_device_kind(db, user_id: int, device_hash: str, kind: str, now: Optional[float] = None) -> None:
    if kind not in (SESSION_PERSONAL, SESSION_PUBLIC):
        raise ValueError("kind invalide")
    now = time.time() if now is None else now
    updated = db.execute(
        "UPDATE web_devices SET kind = %s, last_seen_at = %s WHERE user_id = %s AND device_hash = %s",
        (kind, now, int(user_id), device_hash),
    )
    if int(getattr(updated, "rowcount", 0) or 0) == 0:
        db.execute(
            "INSERT INTO web_devices (user_id, device_hash, kind, created_at, last_seen_at) VALUES (%s, %s, %s, %s, %s)",
            (int(user_id), device_hash, kind, now, now),
        )


def session_lifetime_seconds(session_type: str) -> int:
    return PERSONAL_SESSION_SECONDS if session_type == SESSION_PERSONAL else PUBLIC_SESSION_MAX_SECONDS


def apply_session_type(db, token_hash: str, session_type: str, created_at: float) -> None:
    """Change le type d'une session existante et recalcule son expiration (depuis sa création)."""
    db.execute(
        "UPDATE web_sessions SET session_type = %s, expires_at = %s WHERE token_hash = %s",
        (session_type, float(created_at) + session_lifetime_seconds(session_type), token_hash),
    )


def evaluate_session(row: Dict[str, Any], now: Optional[float] = None) -> str:
    """ok | expired | locked | idle_lock (verrouillage à persister par l'appelant).

    Les sessions antérieures à cette fonctionnalité (session_type NULL) sont traitées comme personnelles
    et gardent leur expiration d'origine : personne n'est déconnecté par la mise à jour.
    """
    now = time.time() if now is None else now
    if float(row.get("expires_at") or 0) <= now:
        return "expired"
    if float(row.get("locked_at") or 0) > 0:
        return "locked"
    stype = row.get("session_type") or SESSION_PERSONAL
    if stype in (SESSION_PUBLIC, SESSION_PENDING):
        last = float(row.get("last_activity_at") or 0) or float(row.get("created_at") or 0)
        if now - last > PUBLIC_IDLE_TIMEOUT_SECONDS:
            return "idle_lock"
    return "ok"


def lock_session(db, token_hash: str, now: Optional[float] = None) -> None:
    db.execute(
        "UPDATE web_sessions SET locked_at = %s WHERE token_hash = %s AND (locked_at IS NULL OR locked_at = 0)",
        (time.time() if now is None else now, token_hash),
    )


def touch_session(db, row: Dict[str, Any], token_hash: str, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    last = float(row.get("last_activity_at") or 0)
    if now - last >= ACTIVITY_TOUCH_INTERVAL_SECONDS:
        db.execute("UPDATE web_sessions SET last_activity_at = %s WHERE token_hash = %s", (now, token_hash))


def purge_locked_sessions_for_device(db, user_id: int, device_hash: str) -> None:
    if device_hash:
        db.execute(
            "DELETE FROM web_sessions WHERE user_id = %s AND device_hash = %s AND locked_at > 0",
            (int(user_id), device_hash),
        )


_UA_OS = [
    (r"iPhone", "iPhone"),
    (r"iPad", "iPad"),
    (r"Android", "Android"),
    (r"Windows", "Windows"),
    (r"Macintosh|Mac OS X", "Mac"),
    (r"CrOS", "ChromeOS"),
    (r"Linux", "Linux"),
]
_UA_BROWSER = [
    (r"Edg(e|A|iOS)?/", "Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"Firefox/|FxiOS/", "Firefox"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"Chrome/|CriOS/", "Chrome"),
    (r"Safari/", "Safari"),
]


def describe_user_agent(user_agent: str) -> Tuple[str, str]:
    """(appareil, navigateur) en libellés simples. Pas de fingerprinting : uniquement le User-Agent déjà envoyé."""
    ua = user_agent or ""
    device = next((label for pat, label in _UA_OS if re.search(pat, ua)), "Appareil inconnu")
    browser = next((label for pat, label in _UA_BROWSER if re.search(pat, ua)), "Navigateur inconnu")
    return device, browser


def public_session_id(token_hash: str) -> str:
    """Identifiant exposé au client : préfixe du hash (ne permet pas de forger un token)."""
    return (token_hash or "")[:16]


def list_sessions(db, user_id: int, current_token_hash: str, now: Optional[float] = None) -> List[Dict[str, Any]]:
    now = time.time() if now is None else now
    rows = db.execute(
        """
        SELECT token_hash, token, user_agent, created_at, expires_at, session_type, last_activity_at, locked_at
        FROM web_sessions WHERE user_id = %s AND expires_at > %s ORDER BY created_at DESC
        """,
        (int(user_id), now),
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        th = r["token_hash"] or r["token"]
        device, browser = describe_user_agent(r["user_agent"] or "")
        last = float(r["last_activity_at"] or 0) or float(r["created_at"] or 0)
        out.append(
            {
                "id": public_session_id(th),
                "device": device,
                "browser": browser,
                "type": r["session_type"] or SESSION_PERSONAL,
                "created_at": float(r["created_at"] or 0),
                "last_activity_at": last,
                "expires_at": float(r["expires_at"] or 0),
                "locked": float(r["locked_at"] or 0) > 0,
                "current": hmac.compare_digest(str(th), str(current_token_hash or "")),
            }
        )
    return out


def revoke_session_by_public_id(db, user_id: int, public_id: str, current_token_hash: str) -> str:
    """Retourne : revoked | current | not_found. La session courante se révoque via /logout, pas ici."""
    if not public_id or len(public_id) < 8:
        return "not_found"
    rows = db.execute("SELECT token_hash, token FROM web_sessions WHERE user_id = %s", (int(user_id),)).fetchall()
    matches = [(r["token_hash"] or r["token"]) for r in rows if public_session_id(r["token_hash"] or r["token"]) == public_id]
    if len(matches) != 1:
        return "not_found"
    if hmac.compare_digest(str(matches[0]), str(current_token_hash or "")):
        return "current"
    db.execute("DELETE FROM web_sessions WHERE user_id = %s AND token_hash = %s", (int(user_id), matches[0]))
    return "revoked"


def revoke_all_sessions(db, user_id: int, except_token_hash: Optional[str] = None) -> int:
    if except_token_hash:
        cur = db.execute(
            "DELETE FROM web_sessions WHERE user_id = %s AND COALESCE(token_hash, token) <> %s", (int(user_id), except_token_hash)
        )
    else:
        cur = db.execute("DELETE FROM web_sessions WHERE user_id = %s", (int(user_id),))
    return int(getattr(cur, "rowcount", 0) or 0)
