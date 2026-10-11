import importlib
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")
import sitecustomize  # noqa: F401


def _make_handler(mod, method: str = "GET", path: str = "/api/test", headers: dict | None = None):
    handler = mod.BitsureAPIHandler.__new__(mod.BitsureAPIHandler)
    handler.command = method
    handler.path = path
    handler.client_address = ("127.0.0.1", 12345)
    handler.headers = headers or {}
    handler.wfile = io.BytesIO()
    handler._sent_status = None
    handler._sent_headers = []

    def send_response(code, message=None):
        handler._sent_status = code

    def send_header(k, v):
        handler._sent_headers.append((k, v))

    def end_headers():
        pass

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    return handler


class TestCorsCsrfSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved_modules = dict(sys.modules)
        for mod_name in (
            "binance",
            "binance.exceptions",
            "binance.client",
            "psycopg2",
            "psycopg2.pool",
            "psycopg2.extras",
            "binance_manager",
            "signal_engine",
            "data_fetcher",
            "paper_trader",
            "position_manager",
            "alert_manager",
            "history_manager",
            "decision_journal",
            "health_monitor",
            "indicators",
            "strategy_lab",
        ):
            sys.modules[mod_name] = MagicMock()
        if "database" in sys.modules and not hasattr(sys.modules["database"], "get_db"):
            sys.modules["database"].get_db = MagicMock()
            sys.modules["database"].get_connection = MagicMock()
        sys.modules.pop("config", None)
        sys.modules.pop("web_api_server", None)
        cls.config = importlib.import_module("config")
        cls.web_api_server = importlib.import_module("web_api_server")

    @classmethod
    def tearDownClass(cls):
        for k in list(sys.modules.keys()):
            if k not in cls._saved_modules:
                sys.modules.pop(k, None)
        sys.modules.update(cls._saved_modules)

    def test_evil_origin_receives_no_allow_origin_headers(self):
        was = self.web_api_server
        with patch.object(was, "ALLOWED_ORIGINS", ["https://app.bitsure.io"]), \
             patch.object(was, "APP_URL", "https://app.bitsure.io"):
            h = _make_handler(was, "GET", "/api/auth/me", {"Origin": "https://evil.com"})
            h._send_json(200, {"ok": True})
            header_keys = {k for k, _ in h._sent_headers}
            self.assertNotIn("Access-Control-Allow-Origin", header_keys)
            self.assertNotIn("Access-Control-Allow-Credentials", header_keys)
            self.assertNotIn("Vary", header_keys)

            h_opt = _make_handler(was, "OPTIONS", "/api/live/order", {"Origin": "https://evil.com"})
            h_opt.do_OPTIONS()
            opt_keys = {k for k, _ in h_opt._sent_headers}
            self.assertNotIn("Access-Control-Allow-Origin", opt_keys)
            self.assertNotIn("Access-Control-Allow-Credentials", opt_keys)

    def test_allowed_origin_receives_cors_headers(self):
        was = self.web_api_server
        with patch.object(was, "ALLOWED_ORIGINS", ["https://app.bitsure.io"]), \
             patch.object(was, "APP_URL", "https://app.bitsure.io"):
            h = _make_handler(was, "GET", "/api/auth/me", {"Origin": "https://app.bitsure.io"})
            h._send_json(200, {"ok": True})
            headers_dict = dict(h._sent_headers)
            self.assertEqual(headers_dict.get("Access-Control-Allow-Origin"), "https://app.bitsure.io")
            self.assertEqual(headers_dict.get("Access-Control-Allow-Credentials"), "true")
            self.assertEqual(headers_dict.get("Vary"), "Origin")

    def test_cookie_samesite_lax_by_default_and_none_only_when_cross_origin_configured(self):
        was = self.web_api_server
        with patch.object(was, "APP_URL", "https://app.bitsure.io"), \
             patch.object(was, "ALLOWED_ORIGINS", ["https://app.bitsure.io"]):
            h = _make_handler(was, "POST", "/api/auth/login", {"X-Forwarded-Proto": "https"})
            cookie = h._build_session_cookie_header("tok123")
            self.assertIn("Secure", cookie)
            self.assertIn("SameSite=Lax", cookie)
            self.assertNotIn("SameSite=None", cookie)

        with patch.object(was, "APP_URL", "https://app.bitsure.io"), \
             patch.object(was, "ALLOWED_ORIGINS", ["https://app.bitsure.io", "https://partner.bitsure.io"]):
            h2 = _make_handler(was, "POST", "/api/auth/login", {"X-Forwarded-Proto": "https"})
            cookie2 = h2._build_session_cookie_header("tok123")
            self.assertIn("Secure", cookie2)
            self.assertIn("SameSite=None", cookie2)

    def test_post_from_evil_origin_rejected_with_403_and_security_event(self):
        was = self.web_api_server
        fake_sess = {"user_id": 42, "email": "pro@bitsure.io", "csrf_token": "csrf-secret-123"}
        with patch.object(was, "ALLOWED_ORIGINS", ["https://app.bitsure.io"]), \
             patch.object(was, "APP_URL", "https://app.bitsure.io"), \
             patch.object(was, "_resolve_authenticated_session", return_value=fake_sess), \
             patch.object(was, "log_security_event") as mock_log:
            h = _make_handler(
                was,
                "POST",
                "/api/live/order",
                {
                    "Origin": "https://evil.com",
                    "Authorization": "Bearer tok123",
                    "X-CSRF-Token": "csrf-secret-123",
                },
            )
            res = h._require_auth(check_csrf=True)
            self.assertIsNone(res)
            self.assertEqual(h._sent_status, 403)
            body = json.loads(h.wfile.getvalue().decode("utf-8"))
            self.assertEqual(body.get("code"), "ORIGIN_FORBIDDEN")
            mock_log.assert_called_once()

    def test_browser_origin_cannot_bypass_csrf_with_bearer_token(self):
        was = self.web_api_server
        fake_sess = {"user_id": 42, "email": "pro@bitsure.io", "csrf_token": "csrf-secret-123"}
        mock_um = MagicMock()
        mock_um.get_account_status.return_value = "APPROVED"

        with patch.object(was, "ALLOWED_ORIGINS", ["https://app.bitsure.io"]), \
             patch.object(was, "APP_URL", "https://app.bitsure.io"), \
             patch.object(was, "_resolve_authenticated_session", return_value=dict(fake_sess)), \
             patch.object(was.UserManager, "get_instance", return_value=mock_um), \
             patch.object(was, "_is_strictly_admin", return_value=False), \
             patch.object(was, "log_security_event") as mock_log:
            # 1. Browser request (Origin present) with Bearer but NO X-CSRF-Token -> must fail 403
            h_no_csrf = _make_handler(
                was,
                "POST",
                "/api/live/order",
                {
                    "Origin": "https://app.bitsure.io",
                    "Authorization": "Bearer tok123",
                },
            )
            self.assertIsNone(h_no_csrf._require_auth(check_csrf=True))
            self.assertEqual(h_no_csrf._sent_status, 403)
            mock_log.assert_called_once()

            # 2. Browser request from allowed Origin WITH valid X-CSRF-Token -> OK
            h_ok = _make_handler(
                was,
                "POST",
                "/api/live/order",
                {
                    "Origin": "https://app.bitsure.io",
                    "Authorization": "Bearer tok123",
                    "X-CSRF-Token": "csrf-secret-123",
                },
            )
            sess_ok = h_ok._require_auth(check_csrf=True)
            self.assertIsNotNone(sess_ok)

            # 3. Non-browser API client (no Origin header) with Bearer -> allowed without CSRF
            h_api = _make_handler(
                was,
                "POST",
                "/api/live/order",
                {
                    "Authorization": "Bearer tok123",
                },
            )
            sess_api = h_api._require_auth(check_csrf=True)
            self.assertIsNotNone(sess_api)


if __name__ == "__main__":
    unittest.main()
