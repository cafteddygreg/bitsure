"""Tests HTTP des routes mot de passe oublié / sessions (base SQLite en mémoire, Resend simulé via requests.post)."""
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


class AuthApiTests(unittest.TestCase):
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
        cls.email_service = importlib.import_module("email_service")

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
        pw = was._hash_password_secure("Oldpass123")
        self.db.execute("INSERT INTO web_accounts (email, user_id, password_hash) VALUES ('teddy@example.com', 7, %s)", (pw,))
        for lim in (a.reset_email_limiter, a.reset_ip_limiter, a.reset_cooldown_limiter, a.reset_confirm_ip_limiter):
            lim.reset()
        was._auth_failed_attempts.clear()
        env = {"RESEND_API_KEY": "re_test_dummy", "EMAIL_FROM": "Bitsure <no-reply@example.test>"}
        self.patches = [
            patch.dict(os.environ, env),
            patch.object(was, "get_db", lambda: self.db),
            patch.object(was, "APP_URL", "https://app.example"),
            patch.object(was, "ALLOWED_ORIGINS", ["https://app.example"]),
            patch.object(was, "ensure_web_schema_initialized", lambda: None),
            patch.object(was, "_upsert_user_telemetry", lambda **k: None),
            patch.object(was, "_build_user_profile", lambda uid, csrf_token="": {"user_id": uid}),
            patch.object(was.threading, "Thread", _SyncThread),
            patch.object(was, "_is_strictly_admin", lambda uid, email=None: False),
            patch.object(was, "UserManager", MagicMock()),
        ]
        for p in self.patches:
            p.start()
        was.UserManager.get_instance.return_value.get_account_status.return_value = was.ACCOUNT_STATUS_APPROVED
        self.sent = []

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

    def resend_ok(self, url, json=None, headers=None, timeout=None):
        self.sent.append(json)
        return _resp(200, {"id": "email_123"})

    def reset_link_token(self):
        html = self.sent[-1]["html"]
        return html.split("token=")[1].split('"')[0]

    def login(self, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537", cookie=""):
        hdrs = {"User-Agent": ua}
        if cookie:
            hdrs["Cookie"] = cookie
        return self.call("POST", "/api/auth/login", {"email": "teddy@example.com", "password": "Oldpass123"}, hdrs)

    def auth_headers(self, res):
        _, p, _ = res
        return {"Authorization": f"Bearer {p['token']}", "X-CSRF-Token": p["csrf_token"], "User-Agent": "UA"}

    # ------------------------------------------------------------------ mot de passe oublié
    def test_forgot_valid_email_calls_resend_and_is_generic(self):
        with patch("requests.post", self.resend_ok):
            st, p, _ = self.call("POST", "/api/auth/forgot-password", {"email": "Teddy@Example.com"})
        self.assertEqual(st, 200)
        self.assertTrue(p["ok"])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["to"], ["teddy@example.com"])
        self.assertIn("https://app.example/reset-password?token=", self.sent[0]["html"])
        self.assertNotIn("Oldpass123", json.dumps(self.sent[0]))
        ev = self.db.execute("SELECT details FROM security_events").fetchall()
        raw = self.reset_link_token()
        self.assertFalse(any(raw in (e["details"] or "") for e in ev))  # jamais de token dans les journaux

    def test_forgot_unknown_email_same_response_no_email(self):
        with patch("requests.post", self.resend_ok):
            st1, p1, _ = self.call("POST", "/api/auth/forgot-password", {"email": "teddy@example.com"})
            self.authsec.reset_cooldown_limiter.reset()
            st2, p2, _ = self.call("POST", "/api/auth/forgot-password", {"email": "ghost@example.com"})
        self.assertEqual((st1, st2), (200, 200))
        self.assertEqual(p1, p2)
        self.assertEqual(len(self.sent), 1)

    def test_forgot_malformed_email(self):
        for bad in ("", "nope", "a@b", "a b@c.com", None):
            st, p, _ = self.call("POST", "/api/auth/forgot-password", {"email": bad})
            self.assertEqual((st, p["code"]), (400, "INVALID_EMAIL"))

    def test_forgot_when_resend_not_configured_is_honest(self):
        with patch.dict(os.environ, {"RESEND_API_KEY": "", "EMAIL_FROM": ""}):
            st, p, _ = self.call("POST", "/api/auth/forgot-password", {"email": "teddy@example.com"})
        self.assertEqual((st, p["code"]), (503, "EMAIL_UNAVAILABLE"))
        self.assertEqual(self.db.execute("SELECT * FROM password_reset_tokens").fetchall(), [])

    def test_resend_rejection_is_never_treated_as_sent(self):
        def reject(url, json=None, headers=None, timeout=None):
            return _resp(403, {"message": "domain not verified"})
        with patch("requests.post", reject):
            st, p, _ = self.call("POST", "/api/auth/forgot-password", {"email": "teddy@example.com"})
        self.assertEqual(st, 200)  # réponse générique (anti-énumération)
        # mais côté serveur : événement d'échec, et aucun lien valable ne reste
        types = [e["event_type"] for e in self.db.execute("SELECT event_type FROM security_events").fetchall()]
        self.assertIn("PASSWORD_RESET_EMAIL_FAILED", types)
        self.assertNotIn("PASSWORD_RESET_REQUESTED", types)
        tok = self.db.execute("SELECT invalidated_at FROM password_reset_tokens").fetchone()
        self.assertGreater(tok["invalidated_at"], 0)

    def test_email_service_failure_modes(self):
        es = self.email_service
        import requests
        with patch("requests.post", side_effect=requests.exceptions.Timeout()):
            self.assertEqual(es.send_email("a@b.co", "s", "<p>x</p>").error_code, "TIMEOUT")
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
            self.assertEqual(es.send_email("a@b.co", "s", "<p>x</p>").error_code, "NETWORK_ERROR")
        with patch("requests.post", return_value=_resp(200, {})):
            self.assertFalse(es.send_email("a@b.co", "s", "<p>x</p>").ok)  # 2xx sans id = non confirmé
        with patch.dict(os.environ, {"RESEND_API_KEY": ""}):
            self.assertEqual(es.send_email("a@b.co", "s", "<p>x</p>").error_code, "NOT_CONFIGURED")

    def test_forgot_rate_limited_and_cooldown(self):
        with patch("requests.post", self.resend_ok):
            self.call("POST", "/api/auth/forgot-password", {"email": "teddy@example.com"})
            st, p, _ = self.call("POST", "/api/auth/forgot-password", {"email": "teddy@example.com"})
        self.assertEqual((st, p["code"]), (429, "RATE_LIMITED"))
        self.assertGreater(p["retry_after"], 0)
        self.assertEqual(len(self.sent), 1)

    # ------------------------------------------------------------------ reset
    def request_link(self, email="teddy@example.com"):
        self.authsec.reset_cooldown_limiter.reset()
        with patch("requests.post", self.resend_ok):
            self.call("POST", "/api/auth/forgot-password", {"email": email})
        return self.reset_link_token()

    def test_validate_token_states(self):
        raw = self.request_link()
        self.assertEqual(self.call("POST", "/api/auth/reset-password/validate", {"token": raw})[0], 200)
        st, p, _ = self.call("POST", "/api/auth/reset-password/validate", {"token": "garbage"})
        self.assertEqual((st, p["code"]), (400, "TOKEN_INVALID"))
        self.db.execute("UPDATE password_reset_tokens SET expires_at = 1")
        st, p, _ = self.call("POST", "/api/auth/reset-password/validate", {"token": raw})
        self.assertEqual(p["code"], "TOKEN_EXPIRED")

    def test_two_requests_invalidate_previous_link(self):
        old = self.request_link()
        new = self.request_link()
        self.assertNotEqual(old, new)
        self.assertEqual(self.call("POST", "/api/auth/reset-password/validate", {"token": old})[1]["code"], "TOKEN_INVALID")
        self.assertEqual(self.call("POST", "/api/auth/reset-password/validate", {"token": new})[0], 200)

    def test_reset_success_then_reuse_and_login(self):
        sess = self.login()
        raw = self.request_link()
        body = {"token": raw, "password": "Brandnew123", "confirm_password": "Brandnew123"}
        st, p, _ = self.call("POST", "/api/auth/reset-password", body)
        self.assertEqual((st, p["ok"]), (200, True))
        # ancienne session révoquée
        self.assertEqual(self.call("GET", "/api/auth/sessions", None, self.auth_headers(sess))[0], 401)
        # lien déjà utilisé
        st, p, _ = self.call("POST", "/api/auth/reset-password", body)
        self.assertEqual((st, p["code"]), (400, "TOKEN_USED"))
        # ancien mot de passe refusé, nouveau accepté
        self.assertEqual(self.call("POST", "/api/auth/login", {"email": "teddy@example.com", "password": "Oldpass123"}, {})[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/login", {"email": "teddy@example.com", "password": "Brandnew123"}, {})[0], 200)

    def test_reset_validation_errors_server_side(self):
        raw = self.request_link()
        st, p, _ = self.call("POST", "/api/auth/reset-password", {"token": raw, "password": "Brandnew123", "confirm_password": "Other123"})
        self.assertEqual((st, p["code"]), (400, "PASSWORD_MISMATCH"))
        st, p, _ = self.call("POST", "/api/auth/reset-password", {"token": raw, "password": "weak", "confirm_password": "weak"})
        self.assertEqual((st, p["code"]), (400, "PASSWORD_WEAK"))
        self.assertTrue(p["rule_messages"])
        st, p, _ = self.call("POST", "/api/auth/reset-password", {"token": "bad", "password": "Brandnew123", "confirm_password": "Brandnew123"})
        self.assertEqual(p["code"], "TOKEN_INVALID")

    # ------------------------------------------------------------------ sessions & appareils
    def cookie_value(self, headers, name):
        for k, v in headers:
            if k == "Set-Cookie" and v.startswith(name + "="):
                return v.split(";")[0].split("=", 1)[1]
        return ""

    def test_new_device_requires_choice_then_personal_policy(self):
        res = self.login()
        st, p, hdrs = res
        self.assertEqual(st, 200)
        self.assertTrue(p["device_choice_required"])
        self.assertEqual(p["session_type"], "pending")
        h = self.auth_headers(res)
        st, p2, hdrs2 = self.call("POST", "/api/auth/session/device", {"kind": "personal"}, h)
        self.assertEqual((st, p2["session_type"]), (200, "personal"))
        self.assertTrue(any("Max-Age=%d" % self.authsec.PERSONAL_SESSION_SECONDS in v for k, v in hdrs2 if k == "Set-Cookie"))
        # 3 jours d'inactivité : toujours connecté
        self.db.execute("UPDATE web_sessions SET last_activity_at = last_activity_at - 259200, created_at = created_at - 259200, expires_at = expires_at - 259200 + 259200")
        self.assertEqual(self.call("GET", "/api/auth/me", None, h)[0], 200)

    def test_known_personal_device_skips_prompt_on_next_login(self):
        res = self.login()
        self.call("POST", "/api/auth/session/device", {"kind": "personal"}, self.auth_headers(res))
        device = self.cookie_value(res[2], self.authsec.DEVICE_COOKIE_NAME)
        self.assertTrue(device)
        st, p, _ = self.login(cookie=f"{self.authsec.DEVICE_COOKIE_NAME}={device}")
        self.assertFalse(p["device_choice_required"])
        self.assertEqual(p["session_type"], "personal")

    def test_public_device_locks_after_idle_and_relogin_works(self):
        res = self.login()
        h = self.auth_headers(res)
        self.call("POST", "/api/auth/session/device", {"kind": "public"}, h)
        self.assertEqual(self.call("GET", "/api/auth/me", None, h)[0], 200)
        self.db.execute("UPDATE web_sessions SET last_activity_at = last_activity_at - 1900")
        st, p, _ = self.call("GET", "/api/auth/me", None, h)
        self.assertEqual((st, p["code"], p["locked"]), (401, "SESSION_LOCKED", True))
        # reste verrouillée (pas de réactivation silencieuse) et les routes protégées répondent SESSION_LOCKED
        st, p, _ = self.call("GET", "/api/auth/sessions", None, h)
        self.assertEqual((st, p["code"]), (401, "SESSION_LOCKED"))
        # reconnexion sur le même appareil : nouvelle session valide, ancienne session verrouillée supprimée
        device = self.cookie_value(res[2], self.authsec.DEVICE_COOKIE_NAME)
        st, p, _ = self.login(cookie=f"{self.authsec.DEVICE_COOKIE_NAME}={device}")
        self.assertEqual((st, p["session_type"]), (200, "public"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM web_sessions").fetchone()["n"], 1)

    def test_background_polling_does_not_keep_public_session_alive(self):
        res = self.login()
        h = self.auth_headers(res)
        self.call("POST", "/api/auth/session/device", {"kind": "public"}, h)
        self.db.execute("UPDATE web_sessions SET last_activity_at = last_activity_at - 1000")
        before = self.db.execute("SELECT last_activity_at FROM web_sessions").fetchone()["last_activity_at"]
        # polling de fond : l'utilisateur est inactif depuis 600 s -> pas de prolongation
        bg = dict(h, **{"X-User-Idle": "600"})
        self.assertEqual(self.call("GET", "/api/auth/me", None, bg)[0], 200)
        self.assertEqual(self.db.execute("SELECT last_activity_at FROM web_sessions").fetchone()["last_activity_at"], before)
        # interaction réelle -> prolongation
        live = dict(h, **{"X-User-Idle": "2"})
        self.assertEqual(self.call("GET", "/api/auth/me", None, live)[0], 200)
        self.assertGreater(self.db.execute("SELECT last_activity_at FROM web_sessions").fetchone()["last_activity_at"], before)

    def test_invalid_device_kind_rejected(self):
        res = self.login()
        st, p, _ = self.call("POST", "/api/auth/session/device", {"kind": "pending"}, self.auth_headers(res))
        self.assertEqual((st, p["code"]), (400, "INVALID_DEVICE_KIND"))

    def test_list_revoke_and_logout_others(self):
        a = self.login(ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17) Version/17 Safari/605")
        b = self.login(ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537")
        ha = self.auth_headers(a)
        st, p, _ = self.call("GET", "/api/auth/sessions", None, ha)
        self.assertEqual(st, 200)
        self.assertEqual(len(p["sessions"]), 2)
        self.assertEqual(sum(1 for s in p["sessions"] if s["current"]), 1)
        other = next(s for s in p["sessions"] if not s["current"])
        self.assertNotIn("token", json.dumps(p))
        # CSRF obligatoire sur l'action
        bad = dict(ha, **{"X-CSRF-Token": "wrong", "Origin": "https://app.example"})
        self.assertEqual(self.call("POST", "/api/auth/sessions/revoke", {"id": other["id"]}, bad)[0], 403)
        st, p, _ = self.call("POST", "/api/auth/sessions/revoke", {"id": other["id"]}, ha)
        self.assertEqual(st, 200)
        self.assertEqual(self.call("GET", "/api/auth/me", None, self.auth_headers(b))[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/sessions/revoke", {"id": other["id"]}, ha)[0], 404)
        # session courante : refus explicite
        cur = self.call("GET", "/api/auth/sessions", None, ha)[1]["sessions"][0]
        self.assertEqual(self.call("POST", "/api/auth/sessions/revoke", {"id": cur["id"]}, ha)[1]["code"], "CURRENT_SESSION")
        # déconnexion de tous les autres appareils
        c = self.login()
        st, p, _ = self.call("POST", "/api/auth/sessions/revoke-others", {}, ha)
        self.assertEqual((st, p["revoked_sessions"]), (200, 1))
        self.assertEqual(self.call("GET", "/api/auth/me", None, self.auth_headers(c))[0], 401)
        self.assertEqual(self.call("GET", "/api/auth/me", None, ha)[0], 200)

    def test_sessions_require_authentication(self):
        self.assertEqual(self.call("GET", "/api/auth/sessions", None, {})[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/sessions/revoke-others", {}, {})[0], 401)

    def test_change_password_revokes_other_sessions_keeps_current(self):
        a = self.login()
        b = self.login()
        ha = self.auth_headers(a)
        st, p, _ = self.call("POST", "/api/auth/change-password",
                             {"current_password": "wrong", "new_password": "Brandnew123", "confirm_password": "Brandnew123"}, ha)
        self.assertEqual((st, p["code"]), (400, "CURRENT_PASSWORD_INVALID"))
        st, p, _ = self.call("POST", "/api/auth/change-password",
                             {"current_password": "Oldpass123", "new_password": "weak", "confirm_password": "weak"}, ha)
        self.assertEqual(p["code"], "PASSWORD_WEAK")
        st, p, _ = self.call("POST", "/api/auth/change-password",
                             {"current_password": "Oldpass123", "new_password": "Oldpass123", "confirm_password": "Oldpass123"}, ha)
        self.assertEqual(p["code"], "PASSWORD_UNCHANGED")
        with patch("requests.post", self.resend_ok):
            st, p, _ = self.call("POST", "/api/auth/change-password",
                                 {"current_password": "Oldpass123", "new_password": "Brandnew123", "confirm_password": "Brandnew123"}, ha)
        self.assertEqual((st, p["revoked_sessions"]), (200, 1))
        self.assertEqual(self.call("GET", "/api/auth/me", None, ha)[0], 200)
        self.assertEqual(self.call("GET", "/api/auth/me", None, self.auth_headers(b))[0], 401)
        self.assertEqual(self.sent[-1]["subject"], "Votre mot de passe Bitsure a été modifié")


if __name__ == "__main__":
    unittest.main()
