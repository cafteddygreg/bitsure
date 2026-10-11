import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database


class _SqliteRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _SqliteConnWrapper:
    def __init__(self, path: str):
        self._raw = sqlite3.connect(path, check_same_thread=False)
        self._raw.row_factory = sqlite3.Row

    def _translate(self, sql: str) -> str:
        s = sql.replace("%s", "?")
        s = s.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        s = s.replace("DOUBLE PRECISION", "REAL")
        s = s.replace("BIGINT", "INTEGER")
        if "ALTER TABLE" in s.upper() and "ADD COLUMN IF NOT EXISTS" in s.upper():
            s = s.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")
        return s

    def execute(self, sql: str, params=()):
        q = self._translate(sql)
        try:
            cur = self._raw.execute(q, params or ())
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                return self._raw.cursor()
            raise
        return _SqliteCursorWrapper(cur)

    def commit(self):
        self._raw.commit()


class _SqliteCursorWrapper:
    def __init__(self, cur):
        self._cur = cur
        self.rowcount = cur.rowcount

    def fetchone(self):
        r = self._cur.fetchone()
        return _SqliteRow(dict(r)) if r is not None else None

    def fetchall(self):
        return [_SqliteRow(dict(r)) for r in self._cur.fetchall()]


def _invoke_post(path: str, payload: dict, headers: dict = None, client_ip: str = "203.0.113.42"):
    import web_api_server

    raw_body = json.dumps(payload).encode("utf-8")
    hdrs = {
        "Content-Type": "application/json",
        "Content-Length": str(len(raw_body)),
    }
    if headers:
        hdrs.update(headers)

    handler = web_api_server.BitsureAPIHandler.__new__(web_api_server.BitsureAPIHandler)
    handler.path = path
    handler.headers = hdrs
    handler.client_address = (client_ip, 54321)
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()

    captured = {}

    def _capture_json(status, data, extra_headers=None):
        captured["status"] = status
        captured["data"] = data
        captured["headers"] = extra_headers or []

    handler._send_json = _capture_json
    handler.do_POST()
    return captured["status"], captured["data"], captured.get("headers", [])


class MediumFixesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.tmp.close()
        self.conn = _SqliteConnWrapper(self.tmp.name)

        self.conn.execute(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                role TEXT DEFAULT 'tester',
                approved INTEGER DEFAULT 1,
                account_status TEXT DEFAULT 'APPROVED',
                terms_accepted INTEGER DEFAULT 1,
                lang TEXT DEFAULT 'fr',
                timeframe TEXT DEFAULT '1h',
                risk TEXT DEFAULT 'medium',
                trial_start REAL DEFAULT 0,
                plan_expires_at REAL DEFAULT 0,
                created_at REAL DEFAULT 0,
                daily_requests INTEGER DEFAULT 0,
                last_request_date TEXT DEFAULT '',
                quota_daily_analyses INTEGER DEFAULT 15,
                quota_daily_scans INTEGER DEFAULT 10,
                quota_max_alerts INTEGER DEFAULT 10,
                quota_max_paper_trades INTEGER DEFAULT 25
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE web_sessions (
                token TEXT PRIMARY KEY,
                token_hash TEXT,
                user_id INTEGER NOT NULL,
                email TEXT,
                csrf_token TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at REAL DEFAULT 0,
                expires_at REAL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE web_accounts (
                email TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                telegram_handle TEXT,
                google_sub TEXT,
                auth_provider TEXT DEFAULT 'local',
                terms_accepted INTEGER DEFAULT 1,
                terms_accepted_at REAL DEFAULT 0,
                terms_version TEXT DEFAULT '2.2.0',
                terms_accepted_ip TEXT DEFAULT '',
                data_collection_consent INTEGER DEFAULT 1,
                created_at REAL DEFAULT 0,
                last_login_at REAL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE paper_capital (
                user_id INTEGER PRIMARY KEY,
                capital REAL NOT NULL,
                initial_capital REAL NOT NULL,
                updated_at REAL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE paper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT DEFAULT 'BUY',
                entry_price REAL NOT NULL,
                sl REAL NOT NULL,
                tp REAL NOT NULL,
                qty REAL NOT NULL,
                leverage REAL DEFAULT 1.0,
                margin_used REAL DEFAULT 0,
                fee_open REAL DEFAULT 0,
                fee_close REAL DEFAULT 0,
                status TEXT DEFAULT 'open',
                opened_at REAL NOT NULL,
                closed_at REAL,
                close_price REAL,
                pnl REAL,
                pnl_pct REAL
            )
            """
        )
        self.conn.commit()

        import importlib
        import sys

        if "binance_manager" in sys.modules and not hasattr(sys.modules["binance_manager"], "test_connection"):
            sys.modules.pop("binance_manager", None)
            importlib.import_module("binance_manager")

        import web_api_server
        from user_manager import UserManager
        from paper_trader import PaperTrader

        self.db_patcher = patch.object(database, "get_db", return_value=self.conn)
        self.web_db_patcher = patch.object(web_api_server, "get_db", return_value=self.conn)
        self.db_patcher.start()
        self.web_db_patcher.start()

        UserManager._instance = None
        PaperTrader._instance = None
        web_api_server._auth_failed_attempts.clear()

    def tearDown(self):
        self.db_patcher.stop()
        self.web_db_patcher.stop()
        try:
            self.conn._raw.close()
            os.unlink(self.tmp.name)
        except Exception:
            pass

    def test_username_btsrteddy_without_admin_id_or_role_is_not_admin(self):
        import user_manager
        from user_manager import UserManager

        um = UserManager.get_instance()
        # Insert user with username @btsrteddy and role='tester', user_id=777777
        self.conn.execute(
            "INSERT INTO users (user_id, username, role, approved, account_status) VALUES (?, ?, ?, 1, 'APPROVED')",
            (777777, "@btsrteddy", "tester"),
        )
        self.conn.commit()

        with patch.object(user_manager, "ADMIN_ID", 123456789):
            self.assertFalse(um.is_admin(777777, username="btsrteddy"))
            self.assertFalse(um.is_admin(777777, username="@btsrteddy"))
            # Numeric ADMIN_ID is admin
            self.assertTrue(um.is_admin(123456789, username="anyone"))

        # Database role='admin' is admin
        self.conn.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (777777,))
        self.conn.commit()
        with patch.object(user_manager, "ADMIN_ID", 123456789):
            self.assertTrue(um.is_admin(777777, username="btsrteddy"))

    def test_raw_session_token_absent_from_database_and_resolved_by_sha256(self):
        import web_api_server

        raw_token, csrf_token = web_api_server._create_session(
            user_id=501,
            email="trader@example.com",
            ip_address="198.51.100.10",
            user_agent="UnitTest/1.0",
        )
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        # Verify raw token is NOT stored in web_sessions (neither in token nor token_hash)
        rows = self.conn.execute("SELECT token, token_hash, user_id FROM web_sessions").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["token"], raw_token)
        self.assertNotEqual(rows[0]["token_hash"], raw_token)
        self.assertEqual(rows[0]["token_hash"], expected_hash)

        # Verify _resolve_authenticated_session resolves using the raw token in Cookie
        resolved = web_api_server._resolve_authenticated_session(
            {"Cookie": f"bitsure_session={raw_token}"}
        )
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["user_id"], 501)
        self.assertEqual(resolved["csrf_token"], csrf_token)

    def test_sixth_failed_login_returns_429(self):
        import web_api_server

        pw_hash = web_api_server._hash_password_secure("CorrectHorseBatteryStaple1!")
        self.conn.execute(
            "INSERT INTO web_accounts (email, user_id, password_hash) VALUES (?, ?, ?)",
            ("victim@example.com", 601, pw_hash),
        )
        self.conn.commit()

        # First 5 failed login attempts return 401
        for attempt in range(1, 6):
            status, data, _ = _invoke_post(
                "/api/auth/login",
                {"email": "victim@example.com", "password": f"wrong-{attempt}"},
                client_ip="192.0.2.99",
            )
            self.assertEqual(status, 401, f"Attempt {attempt} should return 401, got {status}")

        # 6th attempt within 15 minutes must be blocked with 429
        status6, data6, _ = _invoke_post(
            "/api/auth/login",
            {"email": "victim@example.com", "password": "wrong-6"},
            client_ip="192.0.2.99",
        )
        self.assertEqual(status6, 429)
        self.assertFalse(data6["ok"])
        self.assertEqual(data6.get("code"), "RATE_LIMITED")

    def test_paper_open_ignores_client_entry_price_and_returns_503_when_price_unavailable(self):
        import web_api_server

        uid = 801
        self.conn.execute(
            "INSERT INTO users (user_id, username, role, approved, account_status, terms_accepted) VALUES (?, ?, 'pro', 1, 'APPROVED', 1)",
            (uid, "@paperuser"),
        )
        self.conn.commit()

        raw_token, csrf_token = web_api_server._create_session(uid, "paper@example.com")
        headers = {
            "Cookie": f"bitsure_session={raw_token}",
            "X-CSRF-Token": csrf_token,
            "Origin": "https://app.bitsure.io",
        }

        # 1. Client sends bogus entry_price=10.0 while server realtime price is 95000.0
        with patch.object(web_api_server, "ALLOWED_ORIGINS", ["https://app.bitsure.io"]), \
             patch.object(web_api_server, "run_coro", return_value={"price": 95_000.0}), \
             patch.object(web_api_server.UserManager, "check_and_consume_feature_quota", return_value=(True, 1, 25)):
            status, data, _ = _invoke_post(
                "/api/paper/open",
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "qty": 0.01,
                    "leverage": 1.0,
                    "entry_price": 10.0,  # Must be ignored!
                },
                headers=headers,
            )
        self.assertEqual(status, 200, f"Unexpected status {status}: {data}")
        self.assertTrue(data["ok"])
        opened_price = float(data["position"]["entry_price"])
        # With 0.05% slippage on 95000, entry_price is ~95047.5, never near client's 10.0 or 83000.0
        self.assertGreater(opened_price, 94_000.0)
        self.assertLess(opened_price, 96_000.0)

        # 2. When server price is unavailable (0.0 or exception), return 503 (never fallback to 83000.0)
        with patch.object(web_api_server, "ALLOWED_ORIGINS", ["https://app.bitsure.io"]), \
             patch.object(web_api_server, "run_coro", return_value={"price": 0.0}), \
             patch.object(web_api_server.UserManager, "check_and_consume_feature_quota", return_value=(True, 2, 25)):
            status_unavail, data_unavail, _ = _invoke_post(
                "/api/paper/open",
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "qty": 0.01,
                    "leverage": 1.0,
                    "entry_price": 50_000.0,
                },
                headers=headers,
            )
        self.assertEqual(status_unavail, 503)
        self.assertFalse(data_unavail["ok"])


if __name__ == "__main__":
    unittest.main()
