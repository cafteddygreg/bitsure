"""Tests HTTP des sessions, appareils et changement de mot de passe."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _api_harness import ApiHarness, _resp  # noqa: F401
import json, os  # noqa: E401
from unittest.mock import patch


class AuthApiTests(ApiHarness):
    # ------------------------------------------------------------------ sessions & appareils
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
        st, p, _ = self.call("POST", "/api/auth/change-password",
                             {"current_password": "Oldpass123", "new_password": "Brandnew123", "confirm_password": "Brandnew123"}, ha)
        self.assertEqual((st, p["revoked_sessions"]), (200, 1))
        self.assertEqual(self.call("GET", "/api/auth/me", None, ha)[0], 200)
        self.assertEqual(self.call("GET", "/api/auth/me", None, self.auth_headers(b))[0], 401)


if __name__ == "__main__":
    unittest.main()
