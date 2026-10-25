import time
from datetime import datetime
from typing import Dict, List, Optional

from config import (
    FREE_DAILY_REQUESTS,
    ADMIN_ID,
    ADMIN_USERNAME,
    TRIAL_DAYS,
    PLAN_DURATION_DAYS,
    PLAN_PRICES_USDT,
    PROMO_CODES,
    ACCESS_MODE,
    ALLOW_AUTO_REGISTER,
    MAX_WATCHLIST_SYMBOLS_FREE,
    MAX_WATCHLIST_SYMBOLS_TESTER,
    MAX_WATCHLIST_SYMBOLS_PRO,
    MAX_ALERTS_FREE,
    MAX_ALERTS_TESTER,
    MAX_ALERTS_PRO,
    DEFAULT_DAILY_ANALYSIS_LIMIT,
    DEFAULT_DAILY_SCAN_LIMIT,
    DEFAULT_MAX_ALERTS_LIMIT,
    DEFAULT_MAX_PAPER_TRADES_LIMIT,
    DOCUMENTED_SYMBOLS_SQL,
)

from i18n import get_text

ACCOUNT_STATUS_PENDING = "PENDING_APPROVAL"
ACCOUNT_STATUS_APPROVED = "APPROVED"
ACCOUNT_STATUS_REJECTED = "REJECTED"
ACCOUNT_STATUS_SUSPENDED = "SUSPENDED"
VALID_ACCOUNT_STATUSES = (
    ACCOUNT_STATUS_PENDING,
    ACCOUNT_STATUS_APPROVED,
    ACCOUNT_STATUS_REJECTED,
    ACCOUNT_STATUS_SUSPENDED,
)


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
            raw_status = str(user_dict.get("account_status") or "").strip().upper()
            if raw_status in (ACCOUNT_STATUS_REJECTED, ACCOUNT_STATUS_SUSPENDED):
                user_dict["account_status"] = raw_status
                user_dict["approved"] = 0
                return user_dict

            is_paid_role = role_norm in ("pro", "paid", "premium", "vip", "admin")
            is_app = bool(user_dict.get("approved")) or is_paid_role or (raw_status == ACCOUNT_STATUS_APPROVED)
            if is_app and (not user_dict.get("approved") or not user_dict.get("terms_accepted") or raw_status != ACCOUNT_STATUS_APPROVED):
                if role_norm == "vip":
                    canon_role = "vip"
                elif role_norm in ("pro", "paid", "premium"):
                    canon_role = "pro"
                elif role_norm == "admin":
                    canon_role = "admin"
                else:
                    canon_role = user_dict.get("role", "tester")
                try:
                    self.conn.execute(
                        "UPDATE users SET approved = 1, terms_accepted = 1, account_status = %s, role = %s WHERE user_id = %s",
                        (ACCOUNT_STATUS_APPROVED, canon_role, user_id),
                    )
                    self.conn.commit()
                    user_dict["approved"] = 1
                    user_dict["terms_accepted"] = 1
                    user_dict["account_status"] = ACCOUNT_STATUS_APPROVED
                    user_dict["role"] = canon_role
                except Exception:
                    pass
            elif not is_app and not raw_status:
                user_dict["account_status"] = ACCOUNT_STATUS_PENDING
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
                        "UPDATE users SET user_id = %s, username = %s, approved = 1, terms_accepted = 1, account_status = %s WHERE user_id = %s",
                        (user_id, f"@{username.lstrip('@')}", ACCOUNT_STATUS_APPROVED, old_placeholder_id),
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
            INSERT INTO users (
                user_id, role, lang, timeframe, risk, terms_accepted,
                trial_start, created_at, approved, account_status, username,
                quota_daily_analyses, quota_daily_scans, quota_max_alerts, quota_max_paper_trades
            )
            VALUES (%s, 'tester', 'fr', '1h', 'medium', 0, %s, %s, 0, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (
                user_id,
                0.0,  # trial_start: la période d'essai démarre à l'approbation, pas à l'inscription
                now,
                ACCOUNT_STATUS_PENDING,
                f"@{username.lstrip('@')}" if username else None,
                DEFAULT_DAILY_ANALYSIS_LIMIT,
                DEFAULT_DAILY_SCAN_LIMIT,
                DEFAULT_MAX_ALERTS_LIMIT,
                DEFAULT_MAX_PAPER_TRADES_LIMIT,
            )
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
        try:
            uid_int = int(user_id)
        except (TypeError, ValueError):
            return False
        if ADMIN_ID and int(ADMIN_ID) != 0 and uid_int == int(ADMIN_ID):
            return True
        try:
            row = self.conn.execute(
                "SELECT role FROM users WHERE user_id = %s", (uid_int,)
            ).fetchone()
            if row:
                role_norm = str(row["role"] or "").strip().lower()
                if role_norm == "admin":
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

    def get_account_status(self, user_id: int, username: Optional[str] = None) -> str:
        if self.is_admin(user_id, username):
            return ACCOUNT_STATUS_APPROVED
        user = self.get_user(user_id, username=username)
        if not user:
            return ACCOUNT_STATUS_PENDING
        raw = str(user.get("account_status") or "").strip().upper()
        if raw in VALID_ACCOUNT_STATUSES:
            return raw
        role_norm = str(user.get("role") or "").strip().lower()
        if role_norm in ("pro", "paid", "premium", "vip", "admin"):
            return ACCOUNT_STATUS_APPROVED
        app_val = user.get("approved", 0)
        if isinstance(app_val, str):
            is_app = app_val.strip().lower() in ("1", "true", "yes", "approved", "pro")
        else:
            is_app = bool(app_val)
        return ACCOUNT_STATUS_APPROVED if is_app else ACCOUNT_STATUS_PENDING

    def set_account_status(self, user_id: int, status: str) -> bool:
        norm = str(status or ACCOUNT_STATUS_PENDING).strip().upper()
        if norm not in VALID_ACCOUNT_STATUSES:
            return False
        self.get_user(user_id)
        approved_int = 1 if norm == ACCOUNT_STATUS_APPROVED else 0
        # À l'approbation, l'essai démarre maintenant s'il n'a jamais démarré (jamais de remise à zéro d'un essai en cours).
        self.conn.execute(
            """
            UPDATE users
            SET account_status = %s,
                approved = %s,
                terms_accepted = CASE WHEN %s = 1 THEN 1 ELSE terms_accepted END,
                trial_start = CASE WHEN %s = 1 THEN COALESCE(NULLIF(trial_start, 0), %s) ELSE trial_start END
            WHERE user_id = %s
            """,
            (norm, approved_int, approved_int, approved_int, time.time(), int(user_id)),
        )
        self.conn.commit()
        return True

    def is_approved(self, user_id: int, username: Optional[str] = None) -> bool:
        if self.is_admin(user_id, username):
            return True
        return self.get_account_status(user_id, username=username) == ACCOUNT_STATUS_APPROVED

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
        if raw_role == "vip":
            return "vip"
        if raw_role in ("pro", "paid", "premium"):
            return "pro"
        if raw_role == "admin":
            return "admin"
        return raw_role or "tester"

    def set_role(self, user_id: int, role: str, *, duration_days: Optional[int] = None) -> bool:
        """Définit le rôle d'un utilisateur et déverrouille automatiquement son accès (approved=1, terms_accepted=1)."""
        norm_role = str(role or "tester").strip().lower()
        if norm_role in ("pro", "paid", "premium"):
            norm_role = "pro"
        elif norm_role == "vip":
            norm_role = "vip"
        now = time.time()
        user = self.get_user(user_id) or {}
        if norm_role in ("pro", "vip"):
            days = int(duration_days if duration_days is not None else PLAN_DURATION_DAYS)
            current_exp = 0.0
            try:
                current_exp = float(user.get("plan_expires_at") or 0.0)
            except (TypeError, ValueError):
                current_exp = 0.0
            new_exp = max(now, current_exp) + (days * 86400)
            self.conn.execute(
                """
                UPDATE users
                SET role = %s,
                    approved = 1,
                    account_status = %s,
                    terms_accepted = 1,
                    trial_start = COALESCE(NULLIF(trial_start, 0), %s),
                    plan_expires_at = %s
                WHERE user_id = %s
                """,
                (norm_role, ACCOUNT_STATUS_APPROVED, now, new_exp, user_id),
            )
        else:
            self.conn.execute(
                """
                UPDATE users
                SET role = %s,
                    approved = 1,
                    account_status = %s,
                    terms_accepted = 1,
                    trial_start = COALESCE(NULLIF(trial_start, 0), %s)
                WHERE user_id = %s
                """,
                (norm_role, ACCOUNT_STATUS_APPROVED, now, user_id),
            )
        self.conn.commit()
        return True

    def _is_user_plan_active(self, user: Dict, now: Optional[float] = None) -> bool:
        now_ts = float(now if now is not None else time.time())
        raw_role = str(user.get("role") or "").strip().lower()
        if raw_role == "admin":
            return True
        if raw_role not in ("pro", "paid", "premium", "vip"):
            return False
        raw_exp = user.get("plan_expires_at")
        if raw_exp is None:
            # Rétrocompatibilité pour les lignes de test/legacy créées sans colonne plan_expires_at
            return True
        try:
            exp_val = float(raw_exp)
        except (TypeError, ValueError):
            exp_val = 0.0
        return exp_val > now_ts

    def get_premium_users(self) -> List[int]:
        """Retourne la liste des user_id ayant un accès PRO, VIP ou Admin actif (non expiré)."""
        try:
            now_ts = time.time()
            rows = self.conn.execute(
                "SELECT * FROM users WHERE LOWER(TRIM(COALESCE(role, ''))) IN ('pro', 'paid', 'premium', 'vip', 'admin') AND user_id > 0"
            ).fetchall()
            result: List[int] = []
            for r in rows:
                r_dict = dict(r)
                uid = int(r_dict["user_id"])
                if self.is_admin(uid) or self._is_user_plan_active(r_dict, now=now_ts):
                    result.append(uid)
            return result
        except Exception:
            return []

    def is_premium(self, user_id: int) -> bool:
        if self.is_admin(user_id):
            return True
        user = self.get_user(user_id)
        if not user:
            return False
        role = self.get_role(user_id)
        if role == "admin":
            return True
        if role not in ("pro", "vip"):
            return False
        return self._is_user_plan_active(user)

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
            # Essai pas encore démarré : tant que le compte n'est pas approuvé, aucun jour n'est décompté.
            if not self.is_approved(user_id):
                return False
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
    # WEB FEATURE QUOTAS (ANALYSES, SCANS, ALERTS, PAPER TRADES)
    # =========================================================

    def get_user_quotas(self, user_id: int) -> Dict[str, int]:
        user = self.get_user(user_id) or {}
        if self.is_admin(user_id):
            return {
                "daily_analyses": 999999,
                "daily_scans": 999999,
                "max_alerts": 999999,
                "max_paper_trades": 999999,
            }
        role = self.get_role(user_id)
        is_paid = role in ("pro", "vip")
        default_analyses = 200 if is_paid else DEFAULT_DAILY_ANALYSIS_LIMIT
        default_scans = 100 if is_paid else DEFAULT_DAILY_SCAN_LIMIT
        default_alerts = MAX_ALERTS_PRO if is_paid else DEFAULT_MAX_ALERTS_LIMIT
        default_paper = 100 if is_paid else DEFAULT_MAX_PAPER_TRADES_LIMIT

        def _val(col: str, fallback: int) -> int:
            raw = user.get(col)
            if raw is None:
                return fallback
            try:
                v = int(raw)
                return v if v >= 0 else fallback
            except Exception:
                return fallback

        return {
            "daily_analyses": _val("quota_daily_analyses", default_analyses),
            "daily_scans": _val("quota_daily_scans", default_scans),
            "max_alerts": _val("quota_max_alerts", default_alerts),
            "max_paper_trades": _val("quota_max_paper_trades", default_paper),
        }

    def set_user_quotas(
        self,
        user_id: int,
        daily_analyses: Optional[int] = None,
        daily_scans: Optional[int] = None,
        max_alerts: Optional[int] = None,
        max_paper_trades: Optional[int] = None,
    ) -> Dict[str, int]:
        self.get_user(user_id)
        current = self.get_user_quotas(user_id)
        q_a = max(0, int(daily_analyses)) if daily_analyses is not None else current["daily_analyses"]
        q_s = max(0, int(daily_scans)) if daily_scans is not None else current["daily_scans"]
        q_al = max(0, int(max_alerts)) if max_alerts is not None else current["max_alerts"]
        q_pt = max(0, int(max_paper_trades)) if max_paper_trades is not None else current["max_paper_trades"]
        self.conn.execute(
            """
            UPDATE users
            SET quota_daily_analyses = %s,
                quota_daily_scans = %s,
                quota_max_alerts = %s,
                quota_max_paper_trades = %s
            WHERE user_id = %s
            """,
            (q_a, q_s, q_al, q_pt, int(user_id)),
        )
        self.conn.commit()
        return self.get_user_quotas(user_id)

    def get_feature_usage_today(self, user_id: int, feature: str) -> int:
        today = self._get_today()
        row = self.conn.execute(
            "SELECT count FROM user_feature_usage WHERE user_id = %s AND date = %s AND feature = %s",
            (int(user_id), today, feature),
        ).fetchone()
        return int(row["count"]) if row and row["count"] is not None else 0

    def get_all_feature_usage_today(self, user_id: int) -> Dict[str, int]:
        return {
            "analyses_used": self.get_feature_usage_today(user_id, "analysis"),
            "scans_used": self.get_feature_usage_today(user_id, "scan"),
            "paper_trades_used": self.get_feature_usage_today(user_id, "paper_trade"),
        }

    def check_and_consume_feature_quota(self, user_id: int, feature: str, consume: bool = True) -> tuple[bool, int, int]:
        """
        Vérifie et consomme un quota journalier pour `feature` ('analysis', 'scan', 'paper_trade').
        Retourne (autorisé: bool, utilisé: int, limite: int).
        """
        if self.is_admin(user_id):
            used = self.get_feature_usage_today(user_id, feature)
            return True, used, 999999

        quotas = self.get_user_quotas(user_id)
        limit_map = {
            "analysis": quotas["daily_analyses"],
            "scan": quotas["daily_scans"],
            "paper_trade": quotas["max_paper_trades"],
        }
        limit = limit_map.get(feature, DEFAULT_DAILY_ANALYSIS_LIMIT)
        used = self.get_feature_usage_today(user_id, feature)
        if used >= limit:
            return False, used, limit

        if consume:
            today = self._get_today()
            new_count = used + 1
            self.conn.execute(
                """
                INSERT INTO user_feature_usage (user_id, date, feature, count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, date, feature) DO UPDATE SET count = EXCLUDED.count
                """,
                (int(user_id), today, feature, new_count),
            )
            self.conn.commit()
            return True, new_count, limit

        return True, used, limit

    # =========================================================
    # WATCHLIST
    # =========================================================

    def get_watchlist(self, user_id: int) -> List[str]:
        from config import DOCUMENTED_SYMBOLS
        try:
            # Migration de l'ancien symbole « XAUUSD » vers XAUUSDT (sans doublon) avant le nettoyage ci-dessous.
            self.conn.execute(
                "INSERT INTO watchlist (user_id, symbol) SELECT user_id, 'XAUUSDT' FROM watchlist "
                "WHERE user_id = %s AND UPPER(symbol) = 'XAUUSD' ON CONFLICT DO NOTHING",
                (user_id,),
            )
            self.conn.execute(
                f"DELETE FROM watchlist WHERE user_id = %s AND UPPER(symbol) NOT IN ({DOCUMENTED_SYMBOLS_SQL})",
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
        if role in ("pro", "vip"):
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
        code = str(code or "").strip().upper()
        lang = self.get_setting(user_id, "lang", "en")
        promo_cfg = PROMO_CODES.get(code)
        if not promo_cfg:
            return False, get_text(lang, "redeem_invalid")
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"

        now = time.time()
        try:
            existing = self.conn.execute(
                "SELECT 1 FROM promo_redemptions WHERE user_id = %s AND code = %s",
                (user_id, code),
            ).fetchone()
            if existing:
                return False, "Ce code promotionnel a déjà été utilisé sur votre compte."
            cur = self.conn.execute(
                """
                INSERT INTO promo_redemptions (user_id, code, redeemed_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, code) DO NOTHING
                """,
                (user_id, code, now),
            )
            if getattr(cur, "rowcount", 1) == 0:
                return False, "Ce code promotionnel a déjà été utilisé sur votre compte."
        except Exception:
            return False, "Ce code promotionnel a déjà été utilisé sur votre compte."

        days = int(promo_cfg.get("days", 5) if isinstance(promo_cfg, dict) else 5)
        new_trial = float(user.get("trial_start") or now) - days * 86400
        self.conn.execute(
            "UPDATE users SET trial_start = %s WHERE user_id = %s",
            (new_trial, user_id),
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

    def record_payment(
        self,
        user_id: int,
        plan: str,
        amount: float,
        method: str,
        confirmed_by: Optional[int] = None,
    ) -> None:
        """Trace un paiement confirmé dans payment_log."""
        try:
            self.conn.execute(
                """
                INSERT INTO payment_log (user_id, plan, amount, method, confirmed_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (int(user_id), str(plan), float(amount), str(method), confirmed_by, time.time()),
            )
            self.conn.commit()
        except Exception:
            pass

    def confirm_binance_payment(
        self,
        user_id: int,
        *,
        force: bool = False,
        plan: Optional[str] = None,
        confirmed_by: Optional[int] = None,
        method: str = "binance_pay",
        amount: Optional[float] = None,
    ) -> bool:
        """Passe un utilisateur en rôle 'pro' ou 'vip', prolonge plan_expires_at (+30j) et trace dans payment_log."""
        user = self.get_user(user_id)
        if not user:
            return False
        memo_str = str(user.get("memo") or "").upper()
        if not force and not memo_str:
            return False

        if plan:
            target_plan = "vip" if str(plan).strip().lower() == "vip" else "pro"
        elif "VIP" in memo_str:
            target_plan = "vip"
        else:
            target_plan = "pro"

        now = time.time()
        current_exp = 0.0
        try:
            current_exp = float(user.get("plan_expires_at") or 0.0)
        except (TypeError, ValueError):
            current_exp = 0.0
        new_expires_at = max(now, current_exp) + (PLAN_DURATION_DAYS * 86400)
        paid_amount = float(amount if amount is not None else PLAN_PRICES_USDT.get(target_plan, 19.0))

        self.conn.execute(
            """
            UPDATE users
            SET role = %s,
                approved = 1,
                account_status = %s,
                terms_accepted = 1,
                memo = NULL,
                plan_expires_at = %s
            WHERE user_id = %s
            """,
            (target_plan, ACCOUNT_STATUS_APPROVED, new_expires_at, user_id),
        )
        self.conn.commit()
        self.record_payment(
            user_id=user_id,
            plan=target_plan,
            amount=paid_amount,
            method=method,
            confirmed_by=confirmed_by,
        )
        return True

    def expire_subscriptions(self, now: Optional[float] = None) -> List[int]:
        """Passe en rôle 'free' tous les comptes PRO/VIP dont plan_expires_at est expiré (> 0 et <= now)."""
        now_ts = float(now if now is not None else time.time())
        expired_uids: List[int] = []
        try:
            rows = self.conn.execute(
                "SELECT * FROM users WHERE LOWER(TRIM(COALESCE(role, ''))) IN ('pro', 'paid', 'premium', 'vip')"
            ).fetchall()
            for r in rows:
                r_dict = dict(r)
                uid = int(r_dict["user_id"])
                if self.is_admin(uid):
                    continue
                raw_exp = r_dict.get("plan_expires_at")
                try:
                    exp_val = float(raw_exp or 0.0)
                except (TypeError, ValueError):
                    exp_val = 0.0
                if exp_val > 0 and exp_val <= now_ts:
                    self.conn.execute(
                        "UPDATE users SET role = 'free' WHERE user_id = %s",
                        (uid,),
                    )
                    expired_uids.append(uid)
            if expired_uids:
                self.conn.commit()
        except Exception:
            pass
        return expired_uids

    # =========================================================
    # ADMIN: APPROVE TESTER
    # =========================================================

    def approve_user(self, user_id: int, role: str = "tester") -> bool:
        """Approuve un utilisateur, valide les CGU (terms_accepted=1) et réinitialise sa période d'essai sans rétrograder un compte PRO/VIP."""
        now = time.time()
        user = self.get_user(user_id)
        if not user:
            self.conn.execute(
                """
                INSERT INTO users (user_id, role, lang, timeframe, risk, terms_accepted, trial_start, created_at, approved, account_status, username)
                VALUES (%s, %s, 'fr', '1h', 'medium', 1, %s, %s, 1, %s, NULL)
                ON CONFLICT (user_id) DO UPDATE
                SET role = EXCLUDED.role, approved = 1, account_status = EXCLUDED.account_status, terms_accepted = 1, trial_start = EXCLUDED.trial_start
                """,
                (user_id, role, now, now, ACCOUNT_STATUS_APPROVED),
            )
            self.conn.commit()
            return True
        current_role = str(user.get("role") or "").strip().lower()
        effective_role = role
        if current_role == "vip" and role == "tester":
            effective_role = "vip"
        elif current_role in ("pro", "paid", "premium") and role == "tester":
            effective_role = "pro"
        elif current_role == "admin":
            effective_role = "admin"
        self.conn.execute(
            "UPDATE users SET role = %s, approved = 1, account_status = %s, terms_accepted = 1, trial_start = %s WHERE user_id = %s",
            (effective_role, ACCOUNT_STATUS_APPROVED, now, user_id)
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
        self.conn.execute("DELETE FROM user_feature_usage WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM settings WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM watchlist WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM alerts WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM signals WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM paper_positions WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM paper_capitals WHERE user_id = %s", (user_id,))
        try:
            self.conn.execute("DELETE FROM web_sessions WHERE user_id = %s", (user_id,))
            self.conn.execute("DELETE FROM web_accounts WHERE user_id = %s", (user_id,))
        except Exception:
            pass
        self.conn.commit()
        return True
