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

    def commit(self):
        pass

    def execute(self, sql, params=()):
        q = " ".join(sql.strip().split()).upper()
        if q.startswith("SELECT * FROM USERS WHERE USER_ID ="):
            uid = int(params[0])
            row = self.users.get(uid)
            return FakeCursor([dict(row)] if row else [])
        if q.startswith("SELECT 1 FROM USERS WHERE USER_ID ="):
            uid = int(params[0])
            return FakeCursor([{"1": 1}] if uid in self.users else [])
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
        if q.startswith("UPDATE USERS SET APPROVED = 1, TERMS_ACCEPTED = 1, ROLE ="):
            role, uid = params[0], int(params[1])
            if uid in self.users:
                self.users[uid]["approved"] = 1
                self.users[uid]["terms_accepted"] = 1
                self.users[uid]["role"] = role
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET USER_ID ="):
            new_uid, uname, old_uid = int(params[0]), params[1], int(params[2])
            old_row = self.users.pop(old_uid, {})
            old_row.update({
                "user_id": new_uid,
                "username": uname,
                "approved": 1,
                "terms_accepted": 1,
            })
            self.users[new_uid] = old_row
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET ROLE = 'PRO', APPROVED = 1, TERMS_ACCEPTED = 1, MEMO = NULL"):
            uid = int(params[0])
            if uid in self.users:
                self.users[uid]["role"] = "pro"
                self.users[uid]["approved"] = 1
                self.users[uid]["terms_accepted"] = 1
                self.users[uid]["memo"] = None
            return FakeCursor([])
        if q.startswith("UPDATE USERS SET ROLE = %S, APPROVED = 1, TERMS_ACCEPTED = 1, TRIAL_START = %S"):
            role, trial_start, uid = params[0], params[1], int(params[2])
            if uid in self.users:
                self.users[uid]["role"] = role
                self.users[uid]["approved"] = 1
                self.users[uid]["terms_accepted"] = 1
                self.users[uid]["trial_start"] = trial_start
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
