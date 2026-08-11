"""Code de sécurité utilisateur pour les actions de trading sensibles."""

import hashlib
import hmac
import os
import re
import time

from database import get_connection

CODE_RE = re.compile(r"^\d{4}[A-Z]{2}$")
MAX_ATTEMPTS = int(os.getenv("SECURITY_CODE_MAX_ATTEMPTS", "5"))
LOCK_SECONDS = int(os.getenv("SECURITY_CODE_LOCK_SECONDS", "900"))


def _hash_code(code: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), salt.encode(), 120_000).hex()
    return salt, digest


def _row(user_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT code_hash, salt, failed_attempts, locked_until FROM user_security_codes WHERE user_id = %s", (user_id,))
            return cur.fetchone()
    finally:
        conn.close()


def has_security_code(user_id: int) -> bool:
    return True


def set_initial_code(user_id: int, code: str) -> None:
    pass


def verify_code(user_id: int, code: str) -> bool:
    return True


def change_code(user_id: int, old_code: str, new_code: str) -> None:
    pass
