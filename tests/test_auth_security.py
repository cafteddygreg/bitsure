import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auth_security as a  # noqa: E402
from _sqlite_db import make_db  # noqa: E402

HASH = lambda pw: "hash:" + pw  # noqa: E731


class PasswordPolicy(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(a.validate_password("Abcdef12", "x@y.com"), [])
        self.assertIn("TOO_SHORT", a.validate_password("Ab1", ""))
        self.assertIn("NEEDS_DIGIT", a.validate_password("abcdefgh", ""))
        self.assertIn("NEEDS_LETTER", a.validate_password("12345678", ""))
        self.assertIn("SAME_AS_EMAIL", a.validate_password("me@bitsure.io", "me@bitsure.io"))
        self.assertIn("TOO_LONG", a.validate_password("a1" * 80, ""))


class Sessions(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        a.ensure_schema(self.db)

    def add(self, th, stype=None, created=1000.0, last=0.0, ua="", user=7, locked=0.0, expires=None):
        exp = expires if expires is not None else created + a.session_lifetime_seconds(stype or a.SESSION_PERSONAL)
        self.db.execute(
            """INSERT INTO web_sessions (token, token_hash, user_id, user_agent, created_at, expires_at, session_type, last_activity_at, locked_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (th, th, user, ua, created, exp, stype, last, locked),
        )
        return self.db.execute("SELECT * FROM web_sessions WHERE token_hash = %s", (th,)).fetchone()

    def test_personal_session_never_idle_locked(self):
        row = self.add("p1" + "0" * 30, a.SESSION_PERSONAL, 1000.0, 1000.0)
        # 3 jours sans toucher Bitsure : toujours valide
        self.assertEqual(a.evaluate_session(row, 1000.0 + 3 * 86400), "ok")
        # expire seulement à la fin de la durée de vie
        self.assertEqual(a.evaluate_session(row, 1000.0 + a.PERSONAL_SESSION_SECONDS + 1), "expired")

    def test_legacy_session_without_type_is_treated_as_personal(self):
        row = self.add("l1" + "0" * 30, None, 1000.0, 0.0, expires=1000.0 + 14 * 86400)
        self.assertEqual(a.evaluate_session(row, 1000.0 + 5 * 86400), "ok")

    def test_public_session_locks_after_30_min_idle(self):
        row = self.add("s1" + "0" * 30, a.SESSION_PUBLIC, 1000.0, 1000.0)
        self.assertEqual(a.evaluate_session(row, 1000.0 + 29 * 60), "ok")
        self.assertEqual(a.evaluate_session(row, 1000.0 + 31 * 60), "idle_lock")

    def test_pending_session_uses_strict_policy(self):
        row = self.add("n1" + "0" * 30, a.SESSION_PENDING, 1000.0, 1000.0)
        self.assertEqual(a.evaluate_session(row, 1000.0 + 31 * 60), "idle_lock")

    def test_activity_touch_extends_public_session(self):
        row = self.add("s2" + "0" * 30, a.SESSION_PUBLIC, 1000.0, 1000.0)
        a.touch_session(self.db, row, row["token_hash"], 1000.0 + 25 * 60)
        row2 = self.db.execute("SELECT * FROM web_sessions WHERE token_hash = %s", (row["token_hash"],)).fetchone()
        self.assertEqual(a.evaluate_session(row2, 1000.0 + 50 * 60), "ok")

    def test_lock_then_locked_state_and_purge_on_relogin(self):
        row = self.add("s3" + "0" * 30, a.SESSION_PUBLIC, 1000.0, 1000.0)
        a.lock_session(self.db, row["token_hash"], 5000.0)
        row2 = self.db.execute("SELECT * FROM web_sessions").fetchone()
        self.assertEqual(a.evaluate_session(row2, 5001.0), "locked")
        self.db.execute("UPDATE web_sessions SET device_hash = 'dev1'")
        a.purge_locked_sessions_for_device(self.db, 7, "dev1")
        self.assertEqual(self.db.execute("SELECT * FROM web_sessions").fetchall(), [])

    def test_choosing_device_type_recomputes_expiry(self):
        row = self.add("c1" + "0" * 30, a.SESSION_PENDING, 1000.0, 1000.0)
        a.apply_session_type(self.db, row["token_hash"], a.SESSION_PERSONAL, row["created_at"])
        r = self.db.execute("SELECT * FROM web_sessions").fetchone()
        self.assertEqual((r["session_type"], r["expires_at"]), (a.SESSION_PERSONAL, 1000.0 + a.PERSONAL_SESSION_SECONDS))

    def test_device_memory(self):
        self.assertIsNone(a.get_device_kind(self.db, 7, "d1"))
        a.set_device_kind(self.db, 7, "d1", a.SESSION_PUBLIC)
        self.assertEqual(a.get_device_kind(self.db, 7, "d1"), a.SESSION_PUBLIC)
        a.set_device_kind(self.db, 7, "d1", a.SESSION_PERSONAL)
        self.assertEqual(a.get_device_kind(self.db, 7, "d1"), a.SESSION_PERSONAL)
        self.assertIsNone(a.get_device_kind(self.db, 8, "d1"))
        with self.assertRaises(ValueError):
            a.set_device_kind(self.db, 7, "d1", "pending")

    def test_list_and_revoke(self):
        cur = "a" * 32
        other = "b" * 32
        self.add(cur, a.SESSION_PERSONAL, 1000.0, 1000.0, ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit Version/17 Safari/605.1")
        self.add(other, a.SESSION_PUBLIC, 900.0, 900.0, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537")
        self.add("c" * 32, a.SESSION_PERSONAL, 800.0, 800.0, user=99)
        lst = a.list_sessions(self.db, 7, cur, 2000.0)
        self.assertEqual(len(lst), 2)
        cur_item = next(s for s in lst if s["current"])
        self.assertEqual((cur_item["device"], cur_item["browser"]), ("iPhone", "Safari"))
        oth = next(s for s in lst if not s["current"])
        self.assertEqual((oth["device"], oth["browser"], oth["type"]), ("Windows", "Chrome", "public"))
        self.assertNotIn("token", cur_item)
        self.assertEqual(a.revoke_session_by_public_id(self.db, 7, cur_item["id"], cur), "current")
        self.assertEqual(a.revoke_session_by_public_id(self.db, 7, oth["id"], cur), "revoked")
        self.assertEqual(a.revoke_session_by_public_id(self.db, 7, oth["id"], cur), "not_found")
        # on ne peut pas révoquer la session d'un autre utilisateur
        self.assertEqual(a.revoke_session_by_public_id(self.db, 7, a.public_session_id("c" * 32), cur), "not_found")

    def test_revoke_all_except_current(self):
        self.add("a" * 32)
        self.add("b" * 32)
        self.add("c" * 32, user=99)
        n = a.revoke_all_sessions(self.db, 7, except_token_hash="a" * 32)
        self.assertEqual(n, 1)
        left = {r["token_hash"] for r in self.db.execute("SELECT token_hash FROM web_sessions").fetchall()}
        self.assertEqual(left, {"a" * 32, "c" * 32})


if __name__ == "__main__":
    unittest.main()
