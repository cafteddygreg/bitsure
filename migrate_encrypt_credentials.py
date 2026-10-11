"""
migrate_encrypt_credentials.py
------------------------------
Script de migration idempotent pour chiffrer au repos les clés Binance existantes
(`binance_credentials`) qui ne possèdent pas encore le préfixe `enc:v1:`.
Par défaut en mode dry-run ; passer `--apply` pour écrire en base.
"""

from __future__ import annotations

import argparse
import logging
from typing import Dict

import crypto_utils
from database import get_connection

logger = logging.getLogger("migrate_encrypt_credentials")


def migrate_credentials(apply: bool = False) -> Dict[str, int]:
    conn = get_connection()
    scanned = 0
    already_encrypted = 0
    migrated = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, api_key, api_secret FROM binance_credentials")
            rows = cur.fetchall() or []
            for row in rows:
                scanned += 1
                user_id = row[0] if not isinstance(row, dict) else row["user_id"]
                api_key = (row[1] if not isinstance(row, dict) else row["api_key"]) or ""
                api_secret = (row[2] if not isinstance(row, dict) else row["api_secret"]) or ""

                key_encrypted = str(api_key).startswith(crypto_utils.ENCRYPTION_PREFIX)
                secret_encrypted = str(api_secret).startswith(crypto_utils.ENCRYPTION_PREFIX)

                if key_encrypted and secret_encrypted:
                    already_encrypted += 1
                    continue

                migrated += 1
                if apply:
                    new_key = api_key if key_encrypted else crypto_utils.encrypt(str(api_key))
                    new_secret = api_secret if secret_encrypted else crypto_utils.encrypt(str(api_secret))
                    cur.execute(
                        """
                        UPDATE binance_credentials
                        SET api_key = %s,
                            api_secret = %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (new_key, new_secret, user_id),
                    )
        if apply and migrated > 0:
            conn.commit()
    finally:
        conn.close()

    return {
        "scanned": scanned,
        "already_encrypted": already_encrypted,
        "to_migrate": migrated if not apply else 0,
        "migrated": migrated if apply else 0,
        "applied": int(bool(apply)),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Chiffre les clés Binance non préfixées par enc:v1:")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Appliquer réellement les modifications en base (dry-run par défaut).",
    )
    args = parser.parse_args()
    stats = migrate_credentials(apply=args.apply)
    mode_label = "APPLY" if args.apply else "DRY-RUN"
    logger.info(
        "[%s] Scannées=%d | Déjà chiffrées=%d | Chiffrées=%d | À chiffrer=%d",
        mode_label,
        stats["scanned"],
        stats["already_encrypted"],
        stats["migrated"],
        stats["to_migrate"],
    )


if __name__ == "__main__":
    main()
