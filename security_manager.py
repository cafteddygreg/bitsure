"""Code de sécurité utilisateur (PIN 6 caractères) pour les actions de trading sensibles."""

import hashlib
import hmac
import os
import re
import time

from database import get_connection

# Accepte un PIN de 6 chiffres (ex: 123456) ou 4 chiffres + 2 lettres (ex: 1234AB)
CODE_RE = re.compile(r"^(?:\d{6}|\d{4}[A-Za-z]{2})$")
MAX_ATTEMPTS = int(os.getenv("SECURITY_CODE_MAX_ATTEMPTS", "5"))
LOCK_SECONDS = int(os.getenv("SECURITY_CODE_LOCK_SECONDS", "900"))


def _normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def _hash_code(code: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", _normalize_code(code).encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return salt, digest


def _row(user_id: int):
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT code_hash, salt, failed_attempts, locked_until FROM user_security_codes WHERE user_id = %s",
                    (user_id,),
                )
                return cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return None


def has_security_code(user_id: int) -> bool:
    """Retourne True si l'utilisateur a configuré un code PIN dans user_security_codes."""
    row = _row(user_id)
    return bool(row and row[0] and row[1])


def set_initial_code(user_id: int, code: str) -> tuple[bool, str]:
    """Définit le premier code PIN de sécurité (ou l'écrase s'il n'existait pas)."""
    norm = _normalize_code(code)
    if not CODE_RE.match(norm):
        return False, "Format invalide : le code de sécurité doit contenir exactement 6 chiffres (ex: `123456`)."

    existing = _row(user_id)
    if existing and existing[0]:
        return False, "Un code de sécurité existe déjà. Utilise `/setsecurity <ancien_code> <nouveau_code>` pour le modifier."

    salt, digest = _hash_code(norm)
    now = time.time()
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_security_codes (user_id, code_hash, salt, failed_attempts, locked_until, updated_at)
                    VALUES (%s, %s, %s, 0, NULL, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET code_hash = EXCLUDED.code_hash,
                        salt = EXCLUDED.salt,
                        failed_attempts = 0,
                        locked_until = NULL,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, digest, salt, now),
                )
            conn.commit()
        finally:
            conn.close()
        return True, "Code de sécurité (PIN 6 chiffres) enregistré avec succès !"
    except Exception as exc:
        return False, f"Erreur lors de l'enregistrement du code : {exc}"


def verify_code(user_id: int, code: str) -> tuple[bool, str]:
    """Vérifie le code PIN de l'utilisateur avec protection anti-bruteforce."""
    row = _row(user_id)
    if not row or not row[0] or not row[1]:
        return True, ""

    code_hash, salt, failed_attempts, locked_until = row[0], row[1], int(row[2] or 0), row[3]
    now = time.time()
    if locked_until and float(locked_until) > now:
        rem = int(float(locked_until) - now)
        return False, f"Trop de tentatives échouées. Réessaie dans {rem}s."

    norm = _normalize_code(code)
    _, candidate_digest = _hash_code(norm, salt=salt)
    if hmac.compare_digest(candidate_digest, code_hash):
        if failed_attempts > 0 or locked_until:
            try:
                conn = get_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE user_security_codes SET failed_attempts = 0, locked_until = NULL WHERE user_id = %s",
                            (user_id,),
                        )
                    conn.commit()
                finally:
                    conn.close()
            except Exception:
                pass
        return True, "Code validé."

    failed_attempts += 1
    new_lock = (now + LOCK_SECONDS) if failed_attempts >= MAX_ATTEMPTS else None
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE user_security_codes SET failed_attempts = %s, locked_until = %s WHERE user_id = %s",
                    (failed_attempts, new_lock, user_id),
                )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
    except Exception:
        pass

    if new_lock:
        return False, f"Code de sécurité incorrect ({failed_attempts}/{MAX_ATTEMPTS}). Verrouillé pour {LOCK_SECONDS // 60} min."
    return False, f"Code de sécurité incorrect ({failed_attempts}/{MAX_ATTEMPTS})."


def change_code(user_id: int, old_code: str, new_code: str) -> tuple[bool, str]:
    """Modifie un code PIN existant après vérification de l'ancien code."""
    ok, msg = verify_code(user_id, old_code)
    if not ok:
        return False, f"Ancien code invalide : {msg}"

    norm_new = _normalize_code(new_code)
    if not CODE_RE.match(norm_new):
        return False, "Nouveau code invalide : utilise exactement 6 chiffres (ex: `654321`)."

    salt, digest = _hash_code(norm_new)
    now = time.time()
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_security_codes (user_id, code_hash, salt, failed_attempts, locked_until, updated_at)
                    VALUES (%s, %s, %s, 0, NULL, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET code_hash = EXCLUDED.code_hash,
                        salt = EXCLUDED.salt,
                        failed_attempts = 0,
                        locked_until = NULL,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, digest, salt, now),
                )
            conn.commit()
        finally:
            conn.close()
        return True, "Code de sécurité modifié avec succès !"
    except Exception as exc:
        return False, f"Erreur lors de la modification du code : {exc}"

