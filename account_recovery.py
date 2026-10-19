"""
account_recovery.py
-------------------
Récupération de compte INTERNE à Bitsure (sans email, sans service externe) :

  demande -> signaux de confiance -> examen admin -> mot de passe temporaire -> changement obligatoire

Principes :
  - l'authentification existante reste la source de vérité (web_accounts / web_sessions) ;
  - un score ne vaut JAMAIS autorisation : l'administrateur décide, le système ne produit que des signaux ;
  - une IP / un User-Agent / un appareil ne prouvent pas une identité : niveaux « élevé / moyen / faible » uniquement ;
  - le mot de passe temporaire n'est jamais stocké ni journalisé en clair (seul un hash PBKDF2 est conservé) ;
  - aucune énumération : un email inconnu reçoit exactement la même réponse qu'un email connu.

Les fonctions reçoivent un objet `db` compatible get_db() (placeholders %s) afin d'être testables.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import auth_security as authsec

# ---------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------

ST_PENDING = "pending"
ST_REVIEW = "under_review"
ST_NEEDS_INFO = "needs_info"
ST_APPROVED = "approved"
ST_REJECTED = "rejected"
ST_EXPIRED = "expired"
ST_COMPLETED = "completed"

OPEN_STATUSES = (ST_PENDING, ST_REVIEW, ST_NEEDS_INFO)
ALL_STATUSES = OPEN_STATUSES + (ST_APPROVED, ST_REJECTED, ST_EXPIRED, ST_COMPLETED)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "").strip() or default))
    except ValueError:
        return default


REQUEST_TTL_SECONDS = _env_int("RECOVERY_REQUEST_TTL_DAYS", 7) * 86400
TEMP_PASSWORD_TTL_SECONDS = _env_int("RECOVERY_TEMP_TTL_MINUTES", 60) * 60
MAX_MESSAGES_PER_REQUEST = 30
MAX_MESSAGE_LENGTH = 1000
SIGNAL_HISTORY_WINDOW_SECONDS = 30 * 86400

# Alphabet sans caractères ambigus (0/O, 1/l/I) pour faciliter la transmission orale/écrite.
_TEMP_ALPHABET_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"
_TEMP_ALPHABET_DIGITS = "23456789"

# Limiteurs en mémoire (même approche que le limiteur de login existant)
request_ip_limiter = authsec.SlidingWindowLimiter(5, 3600)          # 5 demandes / heure / IP
request_email_limiter = authsec.SlidingWindowLimiter(3, 86400)      # 3 demandes / jour / adresse saisie
request_device_limiter = authsec.SlidingWindowLimiter(5, 86400)     # 5 demandes / jour / appareil
status_ip_limiter = authsec.SlidingWindowLimiter(120, 900)          # consultations du suivi
message_ip_limiter = authsec.SlidingWindowLimiter(20, 3600)

_PROCESS_KEY = secrets.token_bytes(32)


def _hash_key() -> bytes:
    configured = (os.environ.get("RECOVERY_HASH_KEY") or os.environ.get("SESSION_SECRET") or "").strip()
    return configured.encode("utf-8") if configured else _PROCESS_KEY


def hash_network(ip: str) -> str:
    """Empreinte HMAC d'une IP : permet de comparer sans stocker ni afficher l'adresse."""
    if not ip:
        return ""
    return hmac.new(_hash_key(), ("net:" + ip).encode("utf-8"), hashlib.sha256).hexdigest()


def hash_tracking_token(raw: str) -> str:
    return hashlib.sha256(("track:" + (raw or "")).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------

def ensure_schema(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS password_recovery_requests (
            id TEXT PRIMARY KEY,
            user_id BIGINT,
            status TEXT NOT NULL,
            created_at DOUBLE PRECISION DEFAULT 0,
            updated_at DOUBLE PRECISION DEFAULT 0,
            requester_ip_hash TEXT,
            requester_ua TEXT,
            device_hash TEXT,
            matched_session_count INTEGER DEFAULT 0,
            trust_level TEXT,
            trust_signals TEXT,
            note TEXT,
            reviewed_by BIGINT,
            reviewed_at DOUBLE PRECISION DEFAULT 0,
            rejection_reason TEXT,
            temp_hash TEXT,
            temp_expires_at DOUBLE PRECISION DEFAULT 0,
            temp_first_login_at DOUBLE PRECISION DEFAULT 0,
            revoke_sessions INTEGER DEFAULT 1,
            completed_at DOUBLE PRECISION DEFAULT 0
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_recovery_user ON password_recovery_requests (user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_recovery_status ON password_recovery_requests (status)")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS recovery_tracking_tokens (
            token_hash TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            created_at DOUBLE PRECISION DEFAULT 0
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS recovery_messages (
            msg_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at DOUBLE PRECISION DEFAULT 0
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_recovery_msg_req ON recovery_messages (request_id)")
    authsec.ensure_session_columns(db)


# ---------------------------------------------------------------------
# Signaux de confiance (jamais une preuve d'identité)
# ---------------------------------------------------------------------

def analyze_signals(
    db,
    user_id: int,
    ip: str,
    user_agent: str,
    device_hash: str,
    request_session_hash: str,
    now: Optional[float] = None,
) -> Tuple[str, List[Dict[str, str]], int]:
    """Retourne (niveau, signaux, nb_sessions_correspondantes).

    état d'un signal : match | partial | none | negative.
    niveau : high | medium | low — information destinée à l'administrateur, jamais une autorisation.
    """
    now = time.time() if now is None else now
    sessions = db.execute(
        """
        SELECT token_hash, token, ip_address, user_agent, device_hash, created_at, last_activity_at
        FROM web_sessions WHERE user_id = %s
        """,
        (int(user_id),),
    ).fetchall()
    known_devices = {r["device_hash"] for r in sessions if r["device_hash"]}
    try:
        known_devices |= {
            r["device_hash"]
            for r in db.execute("SELECT device_hash FROM web_devices WHERE user_id = %s", (int(user_id),)).fetchall()
        }
    except Exception:
        pass

    req_device, req_browser = authsec.describe_user_agent(user_agent or "")
    hist_pairs = [authsec.describe_user_agent(r["user_agent"] or "") for r in sessions]

    session_match = bool(request_session_hash) and any(
        request_session_hash == (r["token_hash"] or r["token"]) for r in sessions
    )
    device_known = bool(device_hash) and device_hash in known_devices
    full_browser = (req_device, req_browser) in hist_pairs and req_device != "Appareil inconnu"
    partial_browser = (not full_browser) and any(
        (d == req_device and req_device != "Appareil inconnu") or (b == req_browser and req_browser != "Navigateur inconnu")
        for d, b in hist_pairs
    )
    req_net = hash_network(ip)
    ip_match = bool(req_net) and any(hash_network(r["ip_address"] or "") == req_net for r in sessions if r["ip_address"])
    recent = any(
        max(float(r["last_activity_at"] or 0), float(r["created_at"] or 0)) >= now - SIGNAL_HISTORY_WINDOW_SECONDS
        for r in sessions
    )

    signals: List[Dict[str, str]] = [
        {"key": "session", "state": "match" if session_match else "none"},
        {"key": "device", "state": "match" if device_known else "none"},
        {"key": "browser", "state": "match" if full_browser else ("partial" if partial_browser else "none")},
        {"key": "history", "state": "match" if recent else "none"},
        {"key": "network", "state": "partial" if ip_match else "none"},
    ]
    if not (session_match or device_known or full_browser or partial_browser):
        signals.append({"key": "new_device", "state": "negative"})

    if session_match or (device_known and full_browser):
        level = "high"
    elif device_known or full_browser or ip_match:
        level = "medium"
    else:
        level = "low"
    matched = sum(
        1
        for r in sessions
        if (request_session_hash and request_session_hash == (r["token_hash"] or r["token"]))
        or (device_hash and r["device_hash"] == device_hash)
    )
    return level, signals, matched


# ---------------------------------------------------------------------
# Demandes (côté utilisateur)
# ---------------------------------------------------------------------

def _new_request_id(db) -> str:
    for _ in range(10):
        rid = "REQ-" + "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(6))
        if not db.execute("SELECT 1 AS x FROM password_recovery_requests WHERE id = %s", (rid,)).fetchone():
            return rid
    raise RuntimeError("request id generation failed")


def _issue_tracking_token(db, request_id: str, now: float) -> str:
    raw = secrets.token_urlsafe(24)
    db.execute(
        "INSERT INTO recovery_tracking_tokens (token_hash, request_id, created_at) VALUES (%s, %s, %s)",
        (hash_tracking_token(raw), request_id, now),
    )
    return raw


def check_request_allowed(ip: str, email: str, device_hash: str, now: Optional[float] = None) -> Tuple[bool, int]:
    for limiter, key in (
        (request_ip_limiter, f"ip:{ip}"),
        (request_email_limiter, f"em:{email}"),
        (request_device_limiter, f"dev:{device_hash}" if device_hash else None),
    ):
        if key is None:
            continue
        ok, wait = limiter.check_and_record(key, now)
        if not ok:
            return False, wait
    return True, 0


def create_request(
    db,
    email: str,
    ip: str,
    user_agent: str,
    device_hash: str,
    request_session_hash: str,
    note: str = "",
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Crée (ou rattache à une demande ouverte) et retourne un jeton de suivi.

    Un email inconnu produit une demande « orpheline » (user_id NULL) invisible de l'administration :
    la réponse est strictement identique, ce qui empêche l'énumération des comptes.
    """
    now = time.time() if now is None else now
    refresh_expiry(db, now)
    note = (note or "").strip()[:MAX_MESSAGE_LENGTH]
    acct = db.execute("SELECT user_id FROM web_accounts WHERE LOWER(email) = %s", (email,)).fetchone()
    user_id = int(acct["user_id"]) if acct else None

    if user_id is not None:
        existing = db.execute(
            f"SELECT id FROM password_recovery_requests WHERE user_id = %s AND status IN ({','.join(['%s'] * len(OPEN_STATUSES))})",
            (user_id, *OPEN_STATUSES),
        ).fetchone()
        if existing:
            return {"request_id": existing["id"], "tracking_token": _issue_tracking_token(db, existing["id"], now), "created": False}

    level, signals, matched = ("low", [], 0)
    if user_id is not None:
        level, signals, matched = analyze_signals(db, user_id, ip, user_agent, device_hash, request_session_hash, now)
    rid = _new_request_id(db)
    db.execute(
        """
        INSERT INTO password_recovery_requests
            (id, user_id, status, created_at, updated_at, requester_ip_hash, requester_ua, device_hash,
             matched_session_count, trust_level, trust_signals, note, revoke_sessions)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
        """,
        (rid, user_id, ST_PENDING, now, now, hash_network(ip), (user_agent or "")[:200], device_hash or "",
         matched, level, json.dumps(signals), note),
    )
    if note and user_id is not None:
        add_message(db, rid, "user", note, now)
    return {"request_id": rid, "tracking_token": _issue_tracking_token(db, rid, now), "created": True, "orphan": user_id is None,
            "user_id": user_id}


def _request_by_token(db, token: str) -> Optional[Dict[str, Any]]:
    if not token or len(token) > 200:
        return None
    return db.execute(
        """
        SELECT r.* FROM recovery_tracking_tokens t JOIN password_recovery_requests r ON r.id = t.request_id
        WHERE t.token_hash = %s
        """,
        (hash_tracking_token(token),),
    ).fetchone()


def refresh_expiry(db, now: Optional[float] = None) -> int:
    """Expire les demandes ouvertes trop anciennes et les mots de passe temporaires périmés."""
    now = time.time() if now is None else now
    n = 0
    cur = db.execute(
        f"UPDATE password_recovery_requests SET status = %s, updated_at = %s WHERE status IN ({','.join(['%s'] * len(OPEN_STATUSES))}) AND created_at < %s",
        (ST_EXPIRED, now, *OPEN_STATUSES, now - REQUEST_TTL_SECONDS),
    )
    n += int(getattr(cur, "rowcount", 0) or 0)
    cur = db.execute(
        "UPDATE password_recovery_requests SET status = %s, temp_hash = '', updated_at = %s WHERE status = %s AND temp_expires_at > 0 AND temp_expires_at <= %s",
        (ST_EXPIRED, now, ST_APPROVED, now),
    )
    n += int(getattr(cur, "rowcount", 0) or 0)
    return n


def list_messages(db, request_id: str) -> List[Dict[str, Any]]:
    rows = db.execute(
        "SELECT author, body, created_at FROM recovery_messages WHERE request_id = %s ORDER BY created_at ASC",
        (request_id,),
    ).fetchall()
    return [{"author": r["author"], "body": r["body"], "created_at": float(r["created_at"] or 0)} for r in rows]


def get_public_status(db, token: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Vue minimale pour le demandeur : aucun signal, aucune donnée de compte, aucun secret."""
    now = time.time() if now is None else now
    refresh_expiry(db, now)
    row = _request_by_token(db, token)
    if not row:
        return None
    msgs = list_messages(db, row["id"])
    return {
        "request_id": row["id"],
        "status": row["status"],
        "created_at": float(row["created_at"] or 0),
        "updated_at": float(row["updated_at"] or 0),
        "rejection_reason": row["rejection_reason"] if row["status"] == ST_REJECTED else None,
        "temp_expires_at": float(row["temp_expires_at"] or 0) if row["status"] == ST_APPROVED else 0,
        "messages": msgs if row["user_id"] is not None else [m for m in msgs if m["author"] == "user"],
    }


def add_message(db, request_id: str, author: str, body: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    body = (body or "").strip()
    if not body or len(body) > MAX_MESSAGE_LENGTH or author not in ("user", "admin"):
        return False
    count = db.execute("SELECT COUNT(*) AS n FROM recovery_messages WHERE request_id = %s", (request_id,)).fetchone()["n"]
    if int(count) >= MAX_MESSAGES_PER_REQUEST:
        return False
    db.execute(
        "INSERT INTO recovery_messages (msg_id, request_id, author, body, created_at) VALUES (%s, %s, %s, %s, %s)",
        (secrets.token_hex(8), request_id, author, body, now),
    )
    db.execute("UPDATE password_recovery_requests SET updated_at = %s WHERE id = %s", (now, request_id))
    return True


def user_add_message(db, token: str, body: str, now: Optional[float] = None) -> str:
    """ok | not_found | closed | invalid. Un message utilisateur remet une demande « info requise » en attente."""
    now = time.time() if now is None else now
    row = _request_by_token(db, token)
    if not row:
        return "not_found"
    if row["status"] not in OPEN_STATUSES:
        return "closed"
    if row["user_id"] is None:  # demande orpheline : accepté silencieusement, sans effet
        return "ok" if (body or "").strip() else "invalid"
    if not add_message(db, row["id"], "user", body, now):
        return "invalid"
    if row["status"] == ST_NEEDS_INFO:
        db.execute("UPDATE password_recovery_requests SET status = %s, updated_at = %s WHERE id = %s", (ST_PENDING, now, row["id"]))
    return "ok"


# ---------------------------------------------------------------------
# Administration
# ---------------------------------------------------------------------

def list_requests(db, status: str = "", limit: int = 100, now: Optional[float] = None) -> List[Dict[str, Any]]:
    now = time.time() if now is None else now
    refresh_expiry(db, now)
    params: List[Any] = []
    where = "r.user_id IS NOT NULL"  # les demandes orphelines (emails inconnus) ne sont jamais montrées
    if status in ALL_STATUSES:
        where += " AND r.status = %s"
        params.append(status)
    rows = db.execute(
        f"""
        SELECT r.id, r.user_id, r.status, r.created_at, r.updated_at, r.trust_level, r.trust_signals, a.email
        FROM password_recovery_requests r LEFT JOIN web_accounts a ON a.user_id = r.user_id
        WHERE {where} ORDER BY r.created_at DESC LIMIT %s
        """,
        (*params, int(limit)),
    ).fetchall()
    out = []
    for r in rows:
        try:
            signals = json.loads(r["trust_signals"] or "[]")
        except ValueError:
            signals = []
        out.append(
            {
                "id": r["id"], "user_id": int(r["user_id"]), "email": r["email"], "status": r["status"],
                "created_at": float(r["created_at"] or 0), "updated_at": float(r["updated_at"] or 0),
                "trust_level": r["trust_level"] or "low", "signals": signals,
            }
        )
    return out


def get_request_detail(db, request_id: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    now = time.time() if now is None else now
    refresh_expiry(db, now)
    r = db.execute("SELECT * FROM password_recovery_requests WHERE id = %s", (request_id,)).fetchone()
    if not r or r["user_id"] is None:
        return None
    try:
        signals = json.loads(r["trust_signals"] or "[]")
    except ValueError:
        signals = []
    acct = db.execute("SELECT email, user_id, last_login_at FROM web_accounts WHERE user_id = %s", (int(r["user_id"]),)).fetchone()
    sessions = []
    for s in db.execute(
        "SELECT user_agent, device_hash, created_at, last_activity_at, session_type, locked_at FROM web_sessions WHERE user_id = %s ORDER BY created_at DESC",
        (int(r["user_id"]),),
    ).fetchall():
        device, browser = authsec.describe_user_agent(s["user_agent"] or "")
        sessions.append(
            {
                "device": device,
                "browser": browser,
                "last_activity_at": max(float(s["last_activity_at"] or 0), float(s["created_at"] or 0)),
                "type": s["session_type"] or authsec.SESSION_PERSONAL,
                "locked": float(s["locked_at"] or 0) > 0,
                "known": bool(r["device_hash"]) and s["device_hash"] == r["device_hash"],  # même appareil que la demande
            }
        )
    return {
        "id": r["id"],
        "status": r["status"],
        "created_at": float(r["created_at"] or 0),
        "updated_at": float(r["updated_at"] or 0),
        "reviewed_at": float(r["reviewed_at"] or 0),
        "rejection_reason": r["rejection_reason"],
        "temp_expires_at": float(r["temp_expires_at"] or 0),
        "temp_first_login_at": float(r["temp_first_login_at"] or 0),
        "revoke_sessions": bool(r["revoke_sessions"]),
        "trust_level": r["trust_level"] or "low",
        "signals": signals,
        "requester_device": authsec.describe_user_agent(r["requester_ua"] or ""),
        "user": {
            "user_id": int(r["user_id"]),
            "email": acct["email"] if acct else None,
            "last_login_at": float(acct["last_login_at"] or 0) if acct else 0,
        },
        "sessions": sessions,
        "messages": list_messages(db, r["id"]),
    }


def _transition(db, request_id: str, allowed_from: Tuple[str, ...], sets: str, params: Tuple[Any, ...], now: float) -> bool:
    cur = db.execute(
        f"UPDATE password_recovery_requests SET {sets}, updated_at = %s WHERE id = %s AND user_id IS NOT NULL AND status IN ({','.join(['%s'] * len(allowed_from))})",
        (*params, now, request_id, *allowed_from),
    )
    return int(getattr(cur, "rowcount", 0) or 0) == 1


def mark_review(db, request_id: str, admin_id: int, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    return _transition(db, request_id, (ST_PENDING,), "status = %s, reviewed_by = %s, reviewed_at = %s", (ST_REVIEW, admin_id, now), now)


def request_more_info(db, request_id: str, admin_id: int, message: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    if not (message or "").strip():
        return False
    ok = _transition(db, request_id, OPEN_STATUSES, "status = %s, reviewed_by = %s, reviewed_at = %s", (ST_NEEDS_INFO, admin_id, now), now)
    if ok:
        add_message(db, request_id, "admin", message, now)
    return ok


def reject_request(db, request_id: str, admin_id: int, reason: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    return _transition(
        db, request_id, OPEN_STATUSES,
        "status = %s, reviewed_by = %s, reviewed_at = %s, rejection_reason = %s",
        (ST_REJECTED, admin_id, now, (reason or "").strip()[:300]), now,
    )


def generate_temp_password() -> str:
    """Mot de passe temporaire aléatoire (CSPRNG) : 12 caractères, lettres + chiffres, sans caractères ambigus."""
    rng = secrets.SystemRandom()
    chars = [secrets.choice(_TEMP_ALPHABET_LETTERS) for _ in range(8)] + [secrets.choice(_TEMP_ALPHABET_DIGITS) for _ in range(4)]
    rng.shuffle(chars)
    pw = "".join(chars)
    return f"{pw[:4]}-{pw[4:8]}-{pw[8:]}"


def approve_request(
    db,
    request_id: str,
    admin_id: int,
    hash_password: Callable[[str], str],
    revoke_sessions: bool = True,
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Approuve (une seule fois) et retourne {temp_password, expires_at}. Le clair n'est jamais conservé."""
    now = time.time() if now is None else now
    temp = generate_temp_password()
    expires = now + TEMP_PASSWORD_TTL_SECONDS
    ok = _transition(
        db, request_id, OPEN_STATUSES,
        "status = %s, reviewed_by = %s, reviewed_at = %s, temp_hash = %s, temp_expires_at = %s, revoke_sessions = %s",
        (ST_APPROVED, admin_id, now, hash_password(temp), expires, 1 if revoke_sessions else 0), now,
    )
    if not ok:
        return None
    return {"temp_password": temp, "expires_at": expires}


# ---------------------------------------------------------------------
# Connexion avec mot de passe temporaire & changement obligatoire
# ---------------------------------------------------------------------

def verify_temp_login(
    db,
    user_id: int,
    password: str,
    verify_password: Callable[[str, str], bool],
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    now = time.time() if now is None else now
    refresh_expiry(db, now)
    row = db.execute(
        """
        SELECT id, temp_hash, temp_first_login_at FROM password_recovery_requests
        WHERE user_id = %s AND status = %s AND temp_hash IS NOT NULL AND temp_hash <> '' AND temp_expires_at > %s
        ORDER BY reviewed_at DESC LIMIT 1
        """,
        (int(user_id), ST_APPROVED, now),
    ).fetchone()
    if not row or not verify_password(password or "", row["temp_hash"]):
        return None
    if float(row["temp_first_login_at"] or 0) == 0:
        db.execute("UPDATE password_recovery_requests SET temp_first_login_at = %s WHERE id = %s", (now, row["id"]))
    return {"id": row["id"], "first_use": float(row["temp_first_login_at"] or 0) == 0}


def invalidate_temp_for_user(db, user_id: int, now: Optional[float] = None) -> int:
    """Invalide tout mot de passe temporaire en cours (ex. l'utilisateur a changé son mot de passe autrement)."""
    now = time.time() if now is None else now
    cur = db.execute(
        "UPDATE password_recovery_requests SET status = %s, temp_hash = '', completed_at = %s, updated_at = %s WHERE user_id = %s AND status = %s",
        (ST_COMPLETED, now, now, int(user_id), ST_APPROVED),
    )
    return int(getattr(cur, "rowcount", 0) or 0)


def complete_recovery(
    db,
    user_id: int,
    new_password_hash: str,
    current_token_hash: str,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Applique le nouveau mot de passe, invalide le temporaire, lève le flag de changement obligatoire.

    Sessions : la session courante est conservée ; les autres sont révoquées si l'administrateur l'a demandé
    (par défaut oui).
    """
    now = time.time() if now is None else now
    req = db.execute(
        "SELECT id, revoke_sessions FROM password_recovery_requests WHERE user_id = %s AND status = %s ORDER BY reviewed_at DESC LIMIT 1",
        (int(user_id), ST_APPROVED),
    ).fetchone()
    db.execute("UPDATE web_accounts SET password_hash = %s WHERE user_id = %s", (new_password_hash, int(user_id)))
    revoked = 0
    if req:
        db.execute(
            "UPDATE password_recovery_requests SET status = %s, temp_hash = '', completed_at = %s, updated_at = %s WHERE id = %s",
            (ST_COMPLETED, now, now, req["id"]),
        )
        if int(req["revoke_sessions"] or 0):
            revoked = authsec.revoke_all_sessions(db, user_id, except_token_hash=current_token_hash)
    db.execute("UPDATE web_sessions SET must_change_password = 0 WHERE user_id = %s AND COALESCE(token_hash, token) = %s", (int(user_id), current_token_hash))
    return {"request_id": req["id"] if req else None, "revoked_sessions": revoked}
