import time
from datetime import datetime
from typing import Dict, List, Optional

from config import (
    FREE_DAILY_REQUESTS,
    ADMIN_ID,
    ADMIN_USERNAME,
    TRIAL_DAYS,
    ACCESS_MODE,
    ALLOW_AUTO_REGISTER,
    MAX_WATCHLIST_SYMBOLS_FREE,
    MAX_WATCHLIST_SYMBOLS_TESTER,
    MAX_WATCHLIST_SYMBOLS_PRO,
)

from i18n import get_text


class UserManager:

    _instance = None

    def __init__(self):
        from database import get_db
        self.conn = get_db()   # database.py gère tout le schéma

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # =========================================================
    # SAFE GET USER
    # =========================================================

    def get_user(self, user_id: int, username: Optional[str] = None) -> Optional[Dict]:
        """Récupère un utilisateur depuis PostgreSQL, ou le crée/rattache son @username si pré-enregistré par l'admin."""
        row = self.conn.execute(
            "SELECT * FROM users WHERE user_id = %s", (user_id,)
        ).fetchone()

        if row:
            user_dict = dict(row)
            role_norm = str(user_dict.get("role") or "tester").strip().lower()
            is_paid_role = role_norm in ("pro", "paid", "premium", "vip", "admin")
            is_app = bool(user_dict.get("approved")) or is_paid_role
            if is_app and (not user_dict.get("approved") or not user_dict.get("terms_accepted")):
                canon_role = "pro" if role_norm in ("pro", "paid", "premium", "vip") else ("admin" if role_norm == "admin" else user_dict.get("role", "tester"))
                try:
                    self.conn.execute(
                        "UPDATE users SET approved = 1, terms_accepted = 1, role = %s WHERE user_id = %s",
                        (canon_role, user_id),
                    )
                    self.conn.commit()
                    user_dict["approved"] = 1
                    user_dict["terms_accepted"] = 1
                    user_dict["role"] = canon_role
                except Exception:
                    pass
            return user_dict

        # Si l'admin avait pré-autorisé ce @username avant que l'utilisateur ne parle au bot
        if username:
            clean_handle = f"@{username.lstrip('@').lower()}"
            try:
                pre_row = self.conn.execute(
                    "SELECT * FROM users WHERE LOWER(TRIM(username)) IN (%s, %s) AND user_id < 0 LIMIT 1",
                    (clean_handle, clean_handle.lstrip("@")),
                ).fetchone()
                if pre_row:
                    pre_dict = dict(pre_row)
                    old_placeholder_id = pre_dict["user_id"]
                    self.conn.execute(
                        "UPDATE users SET user_id = %s, username = %s, approved = 1, terms_accepted = 1 WHERE user_id = %s",
                        (user_id, f"@{username.lstrip('@')}", old_placeholder_id),
                    )
                    self.conn.commit()
                    return self.get_user(user_id)
            except Exception:
                pass

        if not ALLOW_AUTO_REGISTER:
            return None

        now = time.time()
        self.conn.execute(
            """
            INSERT INTO users (user_id, role, lang, timeframe, risk, terms_accepted, trial_start, created_at, approved, username)
            VALUES (%s, 'tester', 'fr', '1h', 'medium', 0, %s, %s, 0, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, now, now, f"@{username.lstrip('@')}" if username else None)
        )
        self.conn.commit()
        row2 = self.conn.execute("SELECT * FROM users WHERE user_id = %s", (user_id,)).fetchone()
        return dict(row2) if row2 else None

    # =========================================================
    # ACCESS
    # =========================================================

    def user_exists(self, user_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM users WHERE user_id = %s", (user_id,)
        ).fetchone()
        return row is not None

    def is_admin(self, user_id: int, username: Optional[str] = None) -> bool:
        if ADMIN_ID and int(user_id) == int(ADMIN_ID):
            return True
        target_handle = (ADMIN_USERNAME or "@btsrteddy").lstrip("@").lower()
        if username and username.lstrip("@").lower() == target_handle:
            return True
        try:
            row = self.conn.execute(
                "SELECT username, role FROM users WHERE user_id = %s", (user_id,)
            ).fetchone()
            if row:
                db_user = (row["username"] or "").lstrip("@").lower()
                role_norm = str(row["role"] or "").strip().lower()
                if db_user == target_handle or role_norm == "admin":
                    return True
        except Exception:
            pass
        return False

    def resolve_user_target(self, target: str, create_if_username: bool = False) -> Optional[int]:
        """Résout un identifiant utilisateur (numérique, @username ou mémo de paiement) en user_id int."""
        if not target:
            return None
        cleaned = target.strip()
        if cleaned.lstrip("-").isdigit():
            return int(cleaned)
        # Vérifier si c'est un mémo de paiement Binance
        memo_uid = self.find_user_by_memo(cleaned.upper())
        if memo_uid is not None:
            return int(memo_uid)
        handle = cleaned.lstrip("@").lower()
        if not handle:
            return None
        try:
            rows = self.conn.execute(
                "SELECT user_id, username FROM users WHERE username IS NOT NULL"
            ).fetchall()
            for r in rows:
                u_str = (r["username"] or "").lstrip("@").lower()
                if u_str == handle:
                    return int(r["user_id"])
        except Exception:
            pass
        if create_if_username:
            # Crée une entrée pré-approuvée avec un ID négatif déterministe qui sera rattachée au vrai user_id dès son 1er message
            import hashlib
            placeholder_id = -int(hashlib.md5(handle.encode()).hexdigest()[:12], 16)
            now = time.time()
            try:
                self.conn.execute(
                    """
                    INSERT INTO users (user_id, role, lang, timeframe, risk, terms_accepted, trial_start, created_at, approved, username)
                    VALUES (%s, 'tester', 'fr', '1h', 'medium', 1, %s, %s, 1, %s)
                    ON CONFLICT (user_id) DO UPDATE SET approved = 1, terms_accepted = 1, username = EXCLUDED.username
                    """,
                    (placeholder_id, now, now, f"@{handle}"),
                )
                self.conn.commit()
                return placeholder_id
            except Exception:
                pass
        return None

    def is_approved(self, user_id: int, username: Optional[str] = None) -> bool:
        if self.is_admin(user_id, username):
            return True
        user = self.get_user(user_id, username=username)
        if not user:
            return False
        role_norm = str(user.get("role") or "").strip().lower()
        if role_norm in ("pro", "paid", "premium", "vip", "admin"):
            return True
        app_val = user.get("approved", 0)
        if isinstance(app_val, str):
            return app_val.strip().lower() in ("1", "true", "yes", "approved", "pro")
        return bool(app_val)

    def can_access_bot(self, user_id: int, username: Optional[str] = None) -> bool:
        if ACCESS_MODE == "open":
            return True
        return self.is_approved(user_id, username=username)

    # =========================================================
    # ROLE
    # =========================================================

    def get_role(self, user_id: int) -> str:
        user = self.get_user(user_id)
        if not user:
            return "blocked"
        raw_role = str(user.get("role") or "tester").strip().lower()
        if raw_role in ("pro", "paid", "premium", "vip"):
            return "pro"
        if raw_role == "admin":
            return "admin"
        return raw_role or "tester"

    def set_role(self, user_id: int, role: str) -> bool:
        """Définit le rôle d'un utilisateur et déverrouille automatiquement son accès (approved=1, terms_accepted=1)."""
        norm_role = str(role or "tester").strip().lower()
        if norm_role in ("pro", "paid", "premium", "vip"):
            norm_role = "pro"
        now = time.time()
        self.get_user(user_id)
        self.conn.execute(
            """
            UPDATE users
            SET role = %s,
                approved = 1,
                terms_accepted = 1,
                trial_start = COALESCE(NULLIF(trial_start, 0), %s)
            WHERE user_id = %s
            """,
            (norm_role, now, user_id),
        )
        self.conn.commit()
        return True

    def get_premium_users(self) -> List[int]:
        """Retourne la liste des user_id ayant un accès PRO ou Admin."""
        try:
            rows = self.conn.execute(
                "SELECT user_id FROM users WHERE LOWER(TRIM(COALESCE(role, ''))) IN ('pro', 'paid', 'premium', 'vip', 'admin') AND user_id > 0"
            ).fetchall()
            return [int(r["user_id"]) for r in rows]
        except Exception:
            return []

    def is_premium(self, user_id: int) -> bool:
        if self.is_admin(user_id):
            return True
        return self.get_role(user_id) in ["pro", "admin"]

    # =========================================================
    # TRIAL
    # =========================================================

    def is_trial_valid(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False
        if self.is_premium(user_id):
            return True
        start = user.get("trial_start", 0)
        try:
            start = float(start or 0)
        except (TypeError, ValueError):
            start = 0.0
        if start <= 0:
            start = time.time()
            self.conn.execute(
                "UPDATE users SET trial_start = %s WHERE user_id = %s",
                (start, user_id)
            )
            self.conn.commit()
        return time.time() < start + (TRIAL_DAYS * 86400)

    def can_use_premium_feature(self, user_id: int) -> bool:
        return self.is_premium(user_id) or self.is_approved(user_id) or self.is_trial_valid(user_id)

    # =========================================================
    # TERMS
    # =========================================================

    def has_accepted_terms(self, user_id: int, username: Optional[str] = None) -> bool:
        user = self.get_user(user_id, username=username)
        if not user:
            return False
        if self.is_approved(user_id, username=username):
            if not user.get("terms_accepted", 0):
                self.accept_terms(user_id)
            return True
        return bool(user.get("terms_accepted", 0))

    def update_username(self, user_id: int, username: str):
        if username:
            self.conn.execute("UPDATE users SET username = %s WHERE user_id = %s", (username, user_id))
            self.conn.commit()

    def accept_terms(self, user_id: int):
        self.conn.execute(
            "UPDATE users SET terms_accepted = 1 WHERE user_id = %s",
            (user_id,)
        )
        self.conn.commit()

    # =========================================================
    # LIMITS
    # =========================================================

    def _get_today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _get_usage(self, user_id: int) -> int:
        today = self._get_today()
        row = self.conn.execute(
            "SELECT count FROM usage WHERE user_id = %s AND date = %s",
            (user_id, today)
        ).fetchone()
        return row["count"] if row else 0

    def _set_usage(self, user_id: int, count: int):
        today = self._get_today()
        self.conn.execute(
            """
            INSERT INTO usage (user_id, date, count) VALUES (%s, %s, %s)
            ON CONFLICT(user_id, date) DO UPDATE SET count = excluded.count
            """,
            (user_id, today, count)
        )
        self.conn.commit()

    def check_limit(self, user_id: int) -> bool:
        if self.is_admin(user_id) or self.is_premium(user_id) or self.is_approved(user_id):
            return True
        used = self._get_usage(user_id)
        return used < FREE_DAILY_REQUESTS

    def increment_usage(self, user_id: int):
        if self.is_admin(user_id) or self.is_premium(user_id) or self.is_approved(user_id):
            return
        used = self._get_usage(user_id)
        self._set_usage(user_id, used + 1)

    def get_remaining_requests(self, user_id: int) -> int:
        if self.is_premium(user_id) or self.is_admin(user_id) or self.is_approved(user_id):
            return -1
        used = self._get_usage(user_id)
        return max(0, FREE_DAILY_REQUESTS - used)

    # =========================================================
    # WATCHLIST
    # =========================================================

    def get_watchlist(self, user_id: int) -> List[str]:
        from config import DOCUMENTED_SYMBOLS
        try:
            self.conn.execute(
                "DELETE FROM watchlist WHERE user_id = %s AND UPPER(symbol) NOT IN ('BTCUSDT', 'ETHUSDT', 'BTCUSD', 'ETHUSD', 'XAUUSD')",
                (user_id,),
            )
            self.conn.commit()
        except Exception:
            pass
        rows = self.conn.execute(
            "SELECT symbol FROM watchlist WHERE user_id = %s",
            (user_id,)
        ).fetchall()
        return [row["symbol"] for row in rows if str(row["symbol"]).upper() in DOCUMENTED_SYMBOLS]

    def get_watchlist_limit(self, user_id: int) -> int:
        role = self.get_role(user_id)
        if role == "pro":
            return MAX_WATCHLIST_SYMBOLS_PRO
        if role == "tester":
            return MAX_WATCHLIST_SYMBOLS_TESTER
        return MAX_WATCHLIST_SYMBOLS_FREE

    def add_to_watchlist(self, user_id: int, symbol: str):
        from config import DOCUMENTED_SYMBOLS
        sym = symbol.upper().strip()
        if sym not in DOCUMENTED_SYMBOLS:
            return False, 0
        current = self.get_watchlist(user_id)
        limit = self.get_watchlist_limit(user_id)
        if len(current) >= limit:
            return False, limit
        try:
            self.conn.execute(
                "INSERT INTO watchlist (user_id, symbol) VALUES (%s, %s) ON CONFLICT (user_id, symbol) DO NOTHING",
                (user_id, sym)
            )
            self.conn.commit()
        except Exception:
            pass  # déjà présent
        return True, limit

    def remove_from_watchlist(self, user_id: int, symbol: str):
        self.conn.execute(
            "DELETE FROM watchlist WHERE user_id = %s AND symbol = %s",
            (user_id, symbol.upper())
        )
        self.conn.commit()

    # =========================================================
    # SETTINGS
    # =========================================================

    def get_setting(self, user_id: int, key: str, default=None):
        row = self.conn.execute(
            "SELECT value FROM settings WHERE user_id = %s AND key = %s",
            (user_id, key)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, user_id: int, key: str, value):
        self.conn.execute(
            """
            INSERT INTO settings (user_id, key, value) VALUES (%s, %s, %s)
            ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
            """,
            (user_id, key, str(value))
        )
        self.conn.commit()

    # =========================================================
    # PROMO
    # =========================================================

    def redeem_promo(self, user_id: int, code: str):
        promos = {"TRADERBURUNDI": {"days": 5}}
        code = code.upper()
        lang = self.get_setting(user_id, "lang", "en")
        if code not in promos:
            return False, get_text(lang, "redeem_invalid")
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        new_trial = user.get("trial_start", time.time()) - promos[code]["days"] * 86400
        self.conn.execute(
            "UPDATE users SET trial_start = %s WHERE user_id = %s",
            (new_trial, user_id)
        )
        self.conn.commit()
        return True, get_text(lang, "redeem_success")

    # =========================================================
    # ADMIN: GET ALL USERS
    # =========================================================

    def get_all_users(self) -> List[int]:
        """Retourne la liste de tous les user_id."""
        rows = self.conn.execute("SELECT user_id FROM users").fetchall()
        return [row["user_id"] for row in rows]

    # =========================================================
    # ADMIN: PENDING BINANCE & CONFIRM PAYMENT
    # =========================================================

    def add_pending_binance(self, user_id: int, memo: str):
        """Enregistre un mémo de paiement Binance en attente pour l'utilisateur."""
        self.get_user(user_id)
        self.conn.execute(
            "UPDATE users SET memo = %s WHERE user_id = %s",
            (memo, user_id),
        )
        self.conn.commit()

    def has_pending_binance_payment(self, user_id: int) -> bool:
        row = self.conn.execute(
            "SELECT memo FROM users WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        return bool(row and row.get("memo"))

    def confirm_binance_payment(self, user_id: int, *, force: bool = False) -> bool:
        """Passe un utilisateur en rôle 'pro', approuvé=1 et terms_accepted=1 après validation admin."""
        user = self.get_user(user_id)
        if not user:
            return False
        if not force and not user.get("memo"):
            return False
        self.conn.execute(
            "UPDATE users SET role = 'pro', approved = 1, terms_accepted = 1, memo = NULL WHERE user_id = %s",
            (user_id,)
        )
        self.conn.commit()
        return True

    # =========================================================
    # ADMIN: APPROVE TESTER
    # =========================================================

    def approve_user(self, user_id: int, role: str = "tester") -> bool:
        """Approuve un utilisateur, valide les CGU (terms_accepted=1) et réinitialise sa période d'essai sans rétrograder un compte PRO."""
        now = time.time()
        user = self.get_user(user_id)
        if not user:
            self.conn.execute(
                """
                INSERT INTO users (user_id, role, lang, timeframe, risk, terms_accepted, trial_start, created_at, approved, username)
                VALUES (%s, %s, 'fr', '1h', 'medium', 1, %s, %s, 1, NULL)
                ON CONFLICT (user_id) DO UPDATE
                SET role = EXCLUDED.role, approved = 1, terms_accepted = 1, trial_start = EXCLUDED.trial_start
                """,
                (user_id, role, now, now),
            )
            self.conn.commit()
            return True
        current_role = str(user.get("role") or "").strip().lower()
        effective_role = role
        if current_role in ("pro", "paid", "premium", "vip") and role == "tester":
            effective_role = "pro"
        elif current_role == "admin":
            effective_role = "admin"
        self.conn.execute(
            "UPDATE users SET role = %s, approved = 1, terms_accepted = 1, trial_start = %s WHERE user_id = %s",
            (effective_role, now, user_id)
        )
        self.conn.commit()
        return True

    # =========================================================
    # ADMIN: FIND USER BY MEMO
    # =========================================================

    def find_user_by_memo(self, memo: str) -> Optional[int]:
        """Retrouve un user_id à partir de son mémo de paiement Binance."""
        row = self.conn.execute(
            "SELECT user_id FROM users WHERE memo = %s",
            (memo,)
        ).fetchone()
        return row["user_id"] if row else None

    # =========================================================
    # ADMIN: DELETE USER
    # =========================================================

    def delete_user(self, user_id: int) -> bool:
        """Supprime un utilisateur et toutes ses données associées."""
        user = self.get_user(user_id)
        if not user:
            return False
        self.conn.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM usage WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM settings WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM watchlist WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM alerts WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM signals WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM paper_positions WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM paper_capitals WHERE user_id = %s", (user_id,))
        self.conn.commit()
        return True
