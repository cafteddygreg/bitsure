"""Harnais commun des tests HTTP (base SQLite en mémoire, handler réel)."""
import importlib
import io
import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sitecustomize  # noqa: F401,E402
from _sqlite_db import make_db  # noqa: E402


class _SyncThread:
    def __init__(self, target=None, **kw):
        self._t = target

    def start(self):
        self._t()


def _resp(status, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    return r


class ApiHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = dict(sys.modules)
        for m in ("binance", "binance.exceptions", "binance.client", "psycopg2", "psycopg2.pool", "psycopg2.extras",
                  "binance_manager", "signal_engine", "data_fetcher", "paper_trader", "position_manager", "alert_manager",
                  "history_manager", "decision_journal", "health_monitor", "indicators", "strategy_lab"):
            sys.modules[m] = MagicMock()
        if "database" in sys.modules and not hasattr(sys.modules["database"], "get_db"):
            sys.modules["database"].get_db = MagicMock()
            sys.modules["database"].get_connection = MagicMock()
        sys.modules.pop("config", None)
        sys.modules.pop("web_api_server", None)
        importlib.import_module("config")
        cls.was = importlib.import_module("web_api_server")
        cls.authsec = importlib.import_module("auth_security")
        cls.recovery = importlib.import_module("account_recovery")

    @classmethod
    def tearDownClass(cls):
        for k in list(sys.modules):
            if k not in cls._saved:
                sys.modules.pop(k, None)
        sys.modules.update(cls._saved)

    def setUp(self):
        was, a = self.was, self.authsec
        self.db = make_db()
        a.ensure_schema(self.db)
        self.recovery.ensure_schema(self.db)
        for lim in (self.recovery.request_ip_limiter, self.recovery.request_email_limiter, self.recovery.request_device_limiter,
                    self.recovery.status_ip_limiter, self.recovery.message_ip_limiter):
            lim.reset()
        pw = was._hash_password_secure("Oldpass123")
        self.db.execute("INSERT INTO web_accounts (email, user_id, password_hash) VALUES ('teddy@example.com', 7, %s)", (pw,))
        self.db.execute("INSERT INTO web_accounts (email, user_id, password_hash) VALUES ('admin@example.com', 1, %s)", (was._hash_password_secure("Adminpass123"),))
        was._auth_failed_attempts.clear()
        self.patches = [
            patch.object(was, "get_db", lambda: self.db),
            patch.object(was, "APP_URL", "https://app.example"),
            patch.object(was, "ALLOWED_ORIGINS", ["https://app.example"]),
            patch.object(was, "ensure_web_schema_initialized", lambda: None),
            patch.object(was, "_upsert_user_telemetry", lambda **k: None),
            patch.object(was, "_build_user_profile", lambda uid, csrf_token="": {"user_id": uid}),
            patch.object(was.threading, "Thread", _SyncThread),
            patch.object(was, "_is_strictly_admin", lambda uid, email=None: uid == 1),
            patch.object(was, "UserManager", MagicMock()),
        ]
        for p in self.patches:
            p.start()
        was.UserManager.get_instance.return_value.get_account_status.return_value = was.ACCOUNT_STATUS_APPROVED

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    # ------------------------------------------------------------------ helpers
    def call(self, method, path, body=None, headers=None):
        was = self.was
        h = was.BitsureAPIHandler.__new__(was.BitsureAPIHandler)
        h.command, h.path = method, path
        h.client_address = ("10.0.0.1", 1)
        h.headers = headers or {}
        h.wfile = io.BytesIO()
        h._sent_headers = []
        h.send_response = lambda code, message=None: setattr(h, "_status", code)
        h.send_header = lambda k, v: h._sent_headers.append((k, v))
        h.end_headers = lambda: None
        h._read_body = lambda: body or {}
        (h.do_POST if method == "POST" else h.do_GET)()
        payload = json.loads(h.wfile.getvalue().decode() or "{}")
        return h._status, payload, h._sent_headers

    def login(self, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537", cookie=""):
        hdrs = {"User-Agent": ua}
        if cookie:
            hdrs["Cookie"] = cookie
        return self.call("POST", "/api/auth/login", {"email": "teddy@example.com", "password": "Oldpass123"}, hdrs)

    def auth_headers(self, res):
        _, p, _ = res
        return {"Authorization": f"Bearer {p['token']}", "X-CSRF-Token": p["csrf_token"], "User-Agent": "UA"}

    def cookie_value(self, headers, name):
        for k, v in headers:
            if k == "Set-Cookie" and v.startswith(name + "="):
                return v.split(";")[0].split("=", 1)[1]
        return ""

