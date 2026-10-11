import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST_TOKEN")


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.rowcount = len(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class InMemoryUsersDB:
    def __init__(self):
        self.users = {}
        self.settings = {}
        self.usage = {}
        self.promo_redemptions = set()
        self.payment_log = []

    def commit(self):
        pass

    def execute(self, sql, params=()):
        q = " ".join(sql.strip().split()).upper()
        if q.startswith("SELECT * FROM USERS WHERE USER_ID ="):
            uid = int(params[0])
            row = self.users.get(uid)
            return FakeCursor([dict(row)] if row else [])
        if q.startswith("SELECT * FROM USERS WHERE LOWER(TRIM(COALESCE(ROLE, ''))) IN"):
            rows = [
                dict(u)
                for uid, u in self.users.items()
                if str(u.get("role") or "").strip().lower() in ("pro", "paid", "premium", "vip", "admin")
                and ("USER_ID > 0" not in q or uid > 0)
            ]
            return FakeCursor(rows)
        if q.startswith("SELECT 1 FROM USERS WHERE USER_ID ="):
            uid = int(params[0])
            return FakeCursor([{"1": 1}] if uid in self.users else [])
        if q.startswith("SELECT 1 FROM PROMO_REDEMPTIONS WHERE USER_ID ="):
            uid, code = int(params[0]), str(params[1]).upper()
            return FakeCursor([{"1": 1}] if (uid, code) in self.promo_redemptions else [])
        if q.startswith("INSERT INTO PROMO_REDEMPTIONS"):
            uid, code = int(params[0]), str(params[1]).upper()
            if (uid, code) in self.promo_redemptions:
                cur = FakeCursor([])
                cur.rowcount = 0
                return cur
            self.promo_redemptions.add((uid, code))
            cur = FakeCursor([])
            cur.rowcount = 1
            return cur
        if q.startswith("INSERT INTO PAYMENT_LOG"):
            self.payment_log.append({
                "user_id": int(params[0]),
                "plan": params[1],
                "amount": float(params[2]),
                "method": params[3],
                "confirmed_by": params[4],
                "created_at": float(params[5]),
            })
            return FakeCursor([])
        if q.startswith("SELECT USERNAME, ROLE FROM USERS WHERE USER_ID ="):
            uid = int(params[0])
            row = self.users.get(uid)
            return FakeCursor([{"username": row.get("username"), "role": row.get("role")}] if row else [])
        if q.startswith("SELECT USER_ID, USERNAME FROM USERS WHERE USERNAME IS NOT NULL"):
            rows = [
                {"user_id": uid, "username": u.get("username")}
                for uid, u in self.users.items()
                if u.get("username")
            ]
            return FakeCursor(rows)
        if "WHERE LOWER(TRIM(USERNAME)) IN" in q and "USER_ID < 0" in q:
            targets = {str(params[0]).lower(), str(params[1]).lower()}
            for uid, u in self.users.items():
                if uid < 0 and str(u.get("username") or "").strip().lower() in targets:
                    return FakeCursor([dict(u)])
            return FakeCursor([])
        if q.startswith("SELECT MEMO FROM USERS WHERE USER_ID ="):
            uid = int(params[0])
            row = self.users.get(uid)
            return FakeCursor([{"memo": row.get("memo")}] if row else [])
        if q.startswith("SELECT USER_ID FROM USERS WHERE MEMO ="):
            memo = params[0]
            for uid, u in self.users.items():
                if u.get("memo") == memo:
                    return FakeCursor([{"user_id": uid}])
            return FakeCursor([])
        if q.startswith("INSERT INTO USERS"):
            if len(params) == 4:
                uid, trial_start, created_at, username = int(params[0]), params[1], params[2], params[3]
                if uid not in self.users:
                    self.users[uid] = {
                        "user_id": uid,
                        "role": "tester",
                        "lang": "fr",
                        "timeframe": "1h",
                        "risk": "medium",
                        "terms_accepted": 0,
                        "trial_start": trial_start,
                        "created_at": created_at,
                        "approved": 0,
                        "memo": None,
                        "username": username,
                    }
                elif "DO UPDATE" in q:
                    self.users[uid]["approved"] = 1
                    self.users[uid]["terms_accepted"] = 1
                    self.users[uid]["username"] = username
            elif len(params) == 4 and "VALUES (%S, %S," in q:
                uid, role, trial_start, created_at = int(params[0]), params[1], params[2], params[3]
                self.users[uid] = {
                    "user_id": uid,
                    "role": role,
                    "lang": "fr",
                    "timeframe": "1h",
                    "risk": "medium",
                    "terms_accepted": 1,
                    "trial_start": trial_start,
                    "created_at": created_at,
                    "approved": 1,
                    "memo": None,
                    "username": None,
                }
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET APPROVED = 1, TERMS_ACCEPTED = 1"):
            if len(params) == 3:
                acc_status, role, uid = params[0], params[1], int(params[2])
            else:
                acc_status, role, uid = "APPROVED", params[0], int(params[1])
            if uid in self.users:
                self.users[uid]["approved"] = 1
                self.users[uid]["terms_accepted"] = 1
                self.users[uid]["account_status"] = acc_status
                self.users[uid]["role"] = role
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET USER_ID ="):
            if len(params) == 4:
                new_uid, uname, acc_status, old_uid = int(params[0]), params[1], params[2], int(params[3])
            else:
                new_uid, uname, acc_status, old_uid = int(params[0]), params[1], "APPROVED", int(params[2])
            old_row = self.users.pop(old_uid, {})
            old_row.update({
                "user_id": new_uid,
                "username": uname,
                "approved": 1,
                "terms_accepted": 1,
                "account_status": acc_status,
            })
            self.users[new_uid] = old_row
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET ROLE = 'PRO', APPROVED = 1"):
            uid = int(params[-1])
            if uid in self.users:
                self.users[uid]["role"] = "pro"
                self.users[uid]["approved"] = 1
                self.users[uid]["account_status"] = "APPROVED"
                self.users[uid]["terms_accepted"] = 1
                self.users[uid]["memo"] = None
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET ROLE = 'FREE' WHERE USER_ID ="):
            uid = int(params[0])
            if uid in self.users:
                self.users[uid]["role"] = "free"
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET ROLE = %S, APPROVED = 1"):
            role = params[0]
            uid = int(params[-1])
            if uid in self.users:
                self.users[uid]["role"] = role
                self.users[uid]["approved"] = 1
                self.users[uid]["account_status"] = "APPROVED"
                self.users[uid]["terms_accepted"] = 1
                if "MEMO = NULL" in q:
                    self.users[uid]["memo"] = None
                    self.users[uid]["plan_expires_at"] = float(params[2])
                elif "PLAN_EXPIRES_AT = %S" in q:
                    self.users[uid]["trial_start"] = params[2]
                    self.users[uid]["plan_expires_at"] = float(params[3])
                else:
                    self.users[uid]["trial_start"] = params[-2]
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET TRIAL_START = %S WHERE USER_ID ="):
            trial_start, uid = float(params[0]), int(params[1])
            if uid in self.users:
                self.users[uid]["trial_start"] = trial_start
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET MEMO = %S WHERE USER_ID ="):
            memo, uid = params[0], int(params[1])
            if uid in self.users:
                self.users[uid]["memo"] = memo
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET USERNAME ="):
            uname, uid = params[0], int(params[1])
            if uid in self.users:
                self.users[uid]["username"] = uname
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET TERMS_ACCEPTED = 1"):
            uid = int(params[0])
            if uid in self.users:
                self.users[uid]["terms_accepted"] = 1
            return FakeCursor([])
        if q.startswith("SELECT VALUE FROM SETTINGS"):
            uid, key = int(params[0]), params[1]
            val = self.settings.get((uid, key))
            return FakeCursor([{"value": val}] if val is not None else [])
        return FakeCursor([])


class UserAccessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from user_manager import UserManager
        self.db = InMemoryUsersDB()
        self.um = UserManager.__new__(UserManager)
        self.um.conn = self.db

    def test_paid_user_with_approved_zero_is_automatically_unlocked(self):
        # Simule un utilisateur que l'admin a mis dans 'pro' mais avec approved=0 et terms_accepted=0
        self.db.users[777001] = {
            "user_id": 777001,
            "role": "pro",
            "lang": "fr",
            "timeframe": "1h",
            "risk": "medium",
            "terms_accepted": 0,
            "trial_start": 0,
            "created_at": 1700000000.0,
            "approved": 0,
            "memo": None,
            "username": "@paidtrader",
        }
        self.assertTrue(self.um.can_access_bot(777001))
        self.assertTrue(self.um.has_accepted_terms(777001))
        self.assertTrue(self.um.is_premium(777001))
        self.assertTrue(self.um.check_limit(777001))
        # Vérifie que la base a été auto-réparée
        self.assertEqual(self.db.users[777001]["approved"], 1)
        self.assertEqual(self.db.users[777001]["terms_accepted"], 1)

    def test_preregistered_username_links_on_first_message(self):
        placeholder_id = self.um.resolve_user_target("@newpaiduser", create_if_username=True)
        self.assertIsNotNone(placeholder_id)
        self.assertLess(placeholder_id, 0)
        self.um.confirm_binance_payment(placeholder_id, force=True)

        # L'utilisateur envoie /start pour la première fois avec son vrai ID Telegram 888999
        self.assertTrue(self.um.can_access_bot(888999, username="newpaiduser"))
        self.assertTrue(self.um.has_accepted_terms(888999, username="newpaiduser"))
        self.assertEqual(self.um.get_role(888999), "pro")

    def test_approve_user_never_downgrades_pro_user(self):
        self.db.users[555111] = {
            "user_id": 555111,
            "role": "pro",
            "lang": "fr",
            "timeframe": "1h",
            "risk": "medium",
            "terms_accepted": 1,
            "trial_start": 1700000000.0,
            "created_at": 1700000000.0,
            "approved": 1,
            "memo": None,
            "username": "@prouser",
        }
        self.um.approve_user(555111, role="tester")
        self.assertEqual(self.um.get_role(555111), "pro")

    def test_promo_code_single_use_rejects_second_redemption(self):
        """promo 2× -> 2e refusée."""
        self.db.users[600001] = {
            "user_id": 600001,
            "role": "tester",
            "lang": "fr",
            "timeframe": "1h",
            "risk": "medium",
            "terms_accepted": 1,
            "trial_start": 1700000000.0,
            "created_at": 1700000000.0,
            "approved": 1,
            "memo": None,
            "username": "@promouser",
        }
        ok1, _ = self.um.redeem_promo(600001, "TRADERBURUNDI")
        self.assertTrue(ok1)
        ok2, msg2 = self.um.redeem_promo(600001, "TRADERBURUNDI")
        self.assertFalse(ok2)
        self.assertIn("déjà", msg2.lower())

    def test_expired_plan_is_not_premium_and_expiry_job_downgrades_to_free(self):
        """plan expiré -> is_premium False ; job quotidien -> role 'free'."""
        import time as _time
        now = _time.time()
        self.db.users[600002] = {
            "user_id": 600002,
            "role": "pro",
            "lang": "fr",
            "timeframe": "1h",
            "risk": "medium",
            "terms_accepted": 1,
            "trial_start": now - 40 * 86400,
            "created_at": now - 40 * 86400,
            "approved": 1,
            "memo": None,
            "username": "@expireduser",
            "plan_expires_at": now - 3600,
        }
        self.assertFalse(self.um.is_premium(600002))
        self.assertNotIn(600002, self.um.get_premium_users())
        expired = self.um.expire_subscriptions(now=now)
        self.assertIn(600002, expired)
        self.assertEqual(self.db.users[600002]["role"], "free")

    def test_confirmed_payment_extends_expiry_by_30_days_and_logs_payment(self):
        """paiement confirmé -> échéance +30 j + écriture dans payment_log."""
        import time as _time
        from config import PLAN_DURATION_DAYS
        now = _time.time()
        self.db.users[600003] = {
            "user_id": 600003,
            "role": "tester",
            "lang": "fr",
            "timeframe": "1h",
            "risk": "medium",
            "terms_accepted": 1,
            "trial_start": now,
            "created_at": now,
            "approved": 1,
            "memo": "TEDDY-PRO-600003-1234",
            "username": "@payer",
            "plan_expires_at": 0.0,
        }
        ok = self.um.confirm_binance_payment(600003, confirmed_by=1)
        self.assertTrue(ok)
        self.assertEqual(self.um.get_role(600003), "pro")
        exp = self.db.users[600003]["plan_expires_at"]
        self.assertGreaterEqual(exp, now + (PLAN_DURATION_DAYS * 86400) - 5)
        self.assertTrue(self.um.is_premium(600003))
        self.assertEqual(len(self.db.payment_log), 1)
        self.assertEqual(self.db.payment_log[0]["user_id"], 600003)
        self.assertEqual(self.db.payment_log[0]["plan"], "pro")

    def test_vip_recognized_as_premium(self):
        """vip reconnu premium (is_premium et get_premium_users)."""
        import time as _time
        now = _time.time()
        self.db.users[600004] = {
            "user_id": 600004,
            "role": "vip",
            "lang": "fr",
            "timeframe": "1h",
            "risk": "medium",
            "terms_accepted": 1,
            "trial_start": now,
            "created_at": now,
            "approved": 1,
            "memo": None,
            "username": "@viptrader",
            "plan_expires_at": now + 30 * 86400,
        }
        self.assertEqual(self.um.get_role(600004), "vip")
        self.assertTrue(self.um.is_premium(600004))
        self.assertIn(600004, self.um.get_premium_users())

    async def test_start_command_succeeds_for_paid_user_and_callback(self):
        import sys
        from unittest.mock import MagicMock
        with patch.dict(
            sys.modules,
            {
                "matplotlib": MagicMock(),
                "matplotlib.pyplot": MagicMock(),
                "pandas": MagicMock(),
                "telegram": MagicMock(),
                "telegram.ext": MagicMock(),
                "telegram.constants": MagicMock(),
                "apscheduler": MagicMock(),
                "apscheduler.schedulers": MagicMock(),
                "apscheduler.schedulers.asyncio": MagicMock(),
                "data_fetcher": MagicMock(),
                "signal_engine": MagicMock(),
                "indicators": MagicMock(),
                "alert_manager": MagicMock(),
                "history_manager": MagicMock(),
                "paper_trader": MagicMock(),
            },
        ), patch("user_manager.UserManager.get_instance", return_value=self.um):
            import bot_handlers
            self.db.users[999111] = {
                "user_id": 999111,
                "role": "pro",
                "lang": "fr",
                "timeframe": "1h",
                "risk": "medium",
                "terms_accepted": 0,
                "trial_start": 0,
                "created_at": 1700000000.0,
                "approved": 0,
                "memo": None,
                "username": "@vipmember",
            }
            reply_mock = AsyncMock()
            update = SimpleNamespace(
                effective_user=SimpleNamespace(id=999111, username="vipmember", first_name="VIP"),
                message=None,
                callback_query=SimpleNamespace(message=SimpleNamespace(reply_text=reply_mock)),
            )
            context = SimpleNamespace(args=[], bot=SimpleNamespace(send_message=AsyncMock()))
            with patch.object(bot_handlers, "user_mgr", self.um):
                await bot_handlers.start(update, context)
            reply_mock.assert_awaited_once()
            sent_text = reply_mock.await_args.args[0]
            self.assertIn("Bitsure Teddy", sent_text)
            self.assertNotIn("invitation", sent_text.lower())


if __name__ == "__main__":
    unittest.main()
