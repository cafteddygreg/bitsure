"""Tests du workflow de récupération de compte interne (demande -> examen admin -> temporaire -> changement obligatoire)."""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _api_harness import ApiHarness  # noqa: E402

UA_WIN = "Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537"
UA_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17) Version/17 Safari/605"
UA_LINUX = "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0"


class RecoveryTests(ApiHarness):
    # ------------------------------------------------------------------ helpers
    def req(self, email="teddy@example.com", headers=None, note=""):
        return self.call("POST", "/api/auth/recovery/request", {"email": email, "note": note}, headers or {"User-Agent": UA_WIN})

    def admin(self):
        res = self.call("POST", "/api/auth/login", {"email": "admin@example.com", "password": "Adminpass123"}, {"User-Agent": "AdminUA"})
        self.assertEqual(res[0], 200)
        return self.auth_headers(res)

    def admin_post(self, action, body, ah=None):
        return self.call("POST", f"/api/admin/recovery/{action}", body, ah or self.admin())

    def approve(self, rid, ah=None, revoke=True):
        return self.admin_post("approve", {"id": rid, "confirm": True, "revoke_sessions": revoke}, ah)

    def login_temp(self, temp, ua=UA_WIN):
        return self.call("POST", "/api/auth/login", {"email": "teddy@example.com", "password": temp}, {"User-Agent": ua})

    def events(self):
        return self.db.execute("SELECT event_type, details FROM security_events").fetchall()

    # ------------------------------------------------------------------ demande
    def test_request_creates_pending_and_status_is_minimal(self):
        st, p, _ = self.req(note="J'ai oublié")
        self.assertEqual(st, 200)
        self.assertTrue(p["tracking_token"] and p["request_id"].startswith("REQ-"))
        st, s, _ = self.call("POST", "/api/auth/recovery/status", {"token": p["tracking_token"]})
        self.assertEqual((st, s["request"]["status"]), (200, "pending"))
        dump = json.dumps(s)
        for leaked in ("signals", "trust", "user_id", "teddy@example.com", "temp_hash", "10.0.0.1"):
            self.assertNotIn(leaked, dump)
        self.assertEqual(self.call("POST", "/api/auth/recovery/status", {"token": "nope"})[0], 404)

    def test_unknown_account_is_indistinguishable_and_hidden_from_admin(self):
        known = self.req("teddy@example.com")
        unknown = self.req("ghost@example.com")
        self.assertEqual(known[0], unknown[0])
        self.assertEqual(set(known[1].keys()), set(unknown[1].keys()))
        st, s, _ = self.call("POST", "/api/auth/recovery/status", {"token": unknown[1]["tracking_token"]})
        self.assertEqual((st, s["request"]["status"]), (200, "pending"))
        st, lst, _ = self.call("GET", "/api/admin/recovery/requests", None, self.admin())
        self.assertEqual([r["email"] for r in lst["requests"]], ["teddy@example.com"])
        # une demande orpheline ne peut jamais être approuvée
        self.assertEqual(self.approve(unknown[1]["request_id"])[0], 404)

    def test_malformed_email_and_rate_limit(self):
        for bad in ("", "x", "a@b", None):
            self.assertEqual(self.req(bad)[0], 400)
        for _ in range(3):
            self.assertEqual(self.req("ghost@example.com")[0], 200)
        st, p, _ = self.req("ghost@example.com")
        self.assertEqual((st, p["code"]), (429, "RATE_LIMITED"))

    def test_ip_rate_limit(self):
        for i in range(5):
            self.assertEqual(self.req(f"u{i}@example.com")[0], 200)
        self.assertEqual(self.req("u9@example.com")[0], 429)

    def test_existing_open_request_is_reused(self):
        a = self.req()[1]
        b = self.req()[1]
        self.assertEqual(a["request_id"], b["request_id"])
        self.assertNotEqual(a["tracking_token"], b["tracking_token"])
        n = self.db.execute("SELECT COUNT(*) AS n FROM password_recovery_requests WHERE user_id = 7").fetchone()["n"]
        self.assertEqual(n, 1)

    # ------------------------------------------------------------------ signaux
    def test_trust_signals_are_signals_not_identity(self):
        res = self.login(ua=UA_WIN)
        self.call("POST", "/api/auth/session/device", {"kind": "personal"}, self.auth_headers(res))
        device = self.cookie_value(res[2], self.authsec.DEVICE_COOKIE_NAME)
        # même appareil + même navigateur + session connue -> confiance élevée
        h = dict(self.auth_headers(res), **{"Cookie": f"{self.authsec.DEVICE_COOKIE_NAME}={device}", "User-Agent": UA_WIN})
        rid_high = self.call("POST", "/api/auth/recovery/request", {"email": "teddy@example.com"}, h)[1]["request_id"]
        d = self.call("GET", f"/api/admin/recovery/request?id={rid_high}", None, self.admin())[1]["request"]
        self.assertEqual(d["trust_level"], "high")
        states = {s["key"]: s["state"] for s in d["signals"]}
        self.assertEqual((states["session"], states["device"], states["browser"]), ("match", "match", "match"))
        self.assertEqual(states["network"], "partial")  # réseau : signal faible uniquement
        # l'adresse IP n'est jamais exposée à l'admin
        self.assertNotIn("10.0.0.1", json.dumps(d))
        self.assertTrue(any(s["known"] for s in d["sessions"]))
        # autre appareil, autre navigateur, autre réseau -> confiance faible + signal négatif
        self.admin_post("reject", {"id": rid_high, "confirm": True, "reason": "test"})
        self.db.execute("UPDATE web_sessions SET ip_address = '203.0.113.9'")
        rid_low = self.call("POST", "/api/auth/recovery/request", {"email": "teddy@example.com"}, {"User-Agent": UA_LINUX})[1]["request_id"]
        d = self.call("GET", f"/api/admin/recovery/request?id={rid_low}", None, self.admin())[1]["request"]
        self.assertEqual(d["trust_level"], "low")
        self.assertIn({"key": "new_device", "state": "negative"}, d["signals"])
        self.assertNotIn("203.0.113.9", json.dumps(d))

    # ------------------------------------------------------------------ droits admin & confirmation
    def test_only_admin_can_decide(self):
        rid = self.req()[1]["request_id"]
        user = self.auth_headers(self.login())
        for action, body in (("approve", {"id": rid, "confirm": True}), ("reject", {"id": rid, "confirm": True}),
                             ("request-info", {"id": rid, "confirm": True, "message": "x"}), ("revoke-sessions", {"id": rid, "confirm": True})):
            self.assertEqual(self.call("POST", f"/api/admin/recovery/{action}", body, user)[0], 403, action)
            self.assertEqual(self.call("POST", f"/api/admin/recovery/{action}", body, {})[0], 401, action)
        self.assertEqual(self.call("GET", "/api/admin/recovery/requests", None, user)[0], 403)
        status = self.db.execute("SELECT status, temp_hash FROM password_recovery_requests WHERE id = %s", (rid,)).fetchone()
        self.assertEqual((status["status"], status["temp_hash"] or ""), ("pending", ""))

    def test_confirmation_required_server_side(self):
        rid = self.req()[1]["request_id"]
        ah = self.admin()
        for action, body in (("approve", {"id": rid}), ("reject", {"id": rid}), ("request-info", {"id": rid, "message": "x"})):
            st, p, _ = self.call("POST", f"/api/admin/recovery/{action}", body, ah)
            self.assertEqual((st, p["code"]), (400, "CONFIRMATION_REQUIRED"), action)
        self.assertEqual(self.db.execute("SELECT status FROM password_recovery_requests WHERE id = %s", (rid,)).fetchone()["status"], "pending")

    # ------------------------------------------------------------------ approbation + mot de passe temporaire
    def test_approve_generates_random_temp_once_and_never_leaks(self):
        rid = self.req()[1]["request_id"]
        ah = self.admin()
        st, p, _ = self.approve(rid, ah)
        self.assertEqual(st, 200)
        temp = p["temp_password"]
        self.assertRegex(temp, r"^[A-Za-z2-9]{4}-[A-Za-z2-9]{4}-[A-Za-z2-9]{4}$")
        self.assertEqual(self.authsec.validate_password(temp.replace("-", "") + "", "x@y.z"), [])
        row = self.db.execute("SELECT temp_hash FROM password_recovery_requests WHERE id = %s", (rid,)).fetchone()
        self.assertTrue(row["temp_hash"].startswith("pbkdf2_sha256$"))
        # jamais en clair en base (toutes tables)
        for table in ("password_recovery_requests", "recovery_messages", "recovery_tracking_tokens", "security_events", "web_sessions", "web_accounts"):
            self.assertNotIn(temp, json.dumps(self.db.execute(f"SELECT * FROM {table}").fetchall(), default=str), table)
        # ni dans les réponses suivantes, ni dans le détail admin
        self.assertNotIn(temp, json.dumps(self.call("GET", f"/api/admin/recovery/request?id={rid}", None, ah)[1]))
        self.assertNotIn(temp, json.dumps(self.call("GET", "/api/admin/recovery/requests", None, ah)[1]))
        # approbation multiple impossible
        st, p2, _ = self.approve(rid, ah)
        self.assertEqual((st, p2["code"]), (409, "NOT_APPROVABLE"))
        self.assertNotIn("temp_password", p2)
        # deux demandes -> deux mots de passe distincts
        self.assertNotEqual(self.recovery.generate_temp_password(), self.recovery.generate_temp_password())

    def test_rejected_or_expired_request_cannot_be_approved(self):
        rid = self.req()[1]["request_id"]
        ah = self.admin()
        self.assertEqual(self.admin_post("reject", {"id": rid, "confirm": True, "reason": "Doute"}, ah)[0], 200)
        self.assertEqual(self.approve(rid, ah)[0], 409)
        st, s, _ = self.call("POST", "/api/auth/recovery/status", {"token": self.req()[1]["tracking_token"]})
        self.assertEqual(s["request"]["status"], "pending")  # une nouvelle demande est possible après refus
        rid2 = self.db.execute("SELECT id FROM password_recovery_requests WHERE status = 'pending'").fetchone()["id"]
        self.db.execute("UPDATE password_recovery_requests SET created_at = 1 WHERE id = %s", (rid2,))
        self.assertEqual(self.approve(rid2, ah)[0], 409)  # demande périmée : non approuvable
        self.assertEqual(self.db.execute("SELECT status FROM password_recovery_requests WHERE id = %s", (rid2,)).fetchone()["status"], "expired")

    def test_request_info_flow_and_internal_messages(self):
        tok = self.req()[1]
        ah = self.admin()
        self.assertEqual(self.admin_post("request-info", {"id": tok["request_id"], "confirm": True, "message": "Quel est votre dernier trade ?"}, ah)[0], 200)
        s = self.call("POST", "/api/auth/recovery/status", {"token": tok["tracking_token"]})[1]["request"]
        self.assertEqual(s["status"], "needs_info")
        self.assertEqual(s["messages"][-1]["author"], "admin")
        self.assertEqual(self.call("POST", "/api/auth/recovery/message", {"token": tok["tracking_token"], "body": "BTC"})[0], 200)
        s = self.call("POST", "/api/auth/recovery/status", {"token": tok["tracking_token"]})[1]["request"]
        self.assertEqual(s["status"], "pending")
        self.assertEqual(self.call("POST", "/api/auth/recovery/message", {"token": tok["tracking_token"], "body": "x" * 2000})[0], 400)
        self.assertEqual(self.admin_post("message", {"id": tok["request_id"], "body": "Merci"}, ah)[0], 200)

    # ------------------------------------------------------------------ connexion avec temporaire + changement obligatoire
    def approved_temp(self):
        rid = self.req()[1]["request_id"]
        temp = self.approve(rid)[1]["temp_password"]
        return rid, temp

    def test_wrong_or_expired_temp_refused(self):
        rid, temp = self.approved_temp()
        self.assertEqual(self.login_temp("ABCD-EFGH-JKLM")[0], 401)
        self.db.execute("UPDATE password_recovery_requests SET temp_expires_at = 1")
        self.assertEqual(self.login_temp(temp)[0], 401)
        st, s, _ = self.call("POST", "/api/auth/recovery/status", {"token": self.req("teddy@example.com")[1]["tracking_token"]})
        self.assertEqual(self.db.execute("SELECT status FROM password_recovery_requests WHERE id = %s", (rid,)).fetchone()["status"], "expired")

    def test_temp_login_blocks_app_until_password_changed(self):
        rid, temp = self.approved_temp()
        res = self.login_temp(temp)
        self.assertEqual(res[0], 200)
        self.assertTrue(res[1]["must_change_password"])
        h = self.auth_headers(res)
        # l'application est bloquée
        for method, path in (("GET", "/api/auth/sessions"), ("POST", "/api/auth/sessions/revoke-others"), ("POST", "/api/auth/session/device")):
            st, p, _ = self.call(method, path, {} if method == "POST" else None, h)
            self.assertEqual((st, p["code"]), (403, "PASSWORD_CHANGE_REQUIRED"), path)
        me = self.call("GET", "/api/auth/me", None, h)[1]
        self.assertTrue(me["session"]["must_change_password"])
        # confirmation incorrecte / mot de passe faible / identique au temporaire
        fc = "/api/auth/password/force-change"
        self.assertEqual(self.call("POST", fc, {"new_password": "Brandnew123", "confirm_password": "Other123"}, h)[1]["code"], "PASSWORD_MISMATCH")
        self.assertEqual(self.call("POST", fc, {"new_password": "weak", "confirm_password": "weak"}, h)[1]["code"], "PASSWORD_WEAK")
        self.assertEqual(self.call("POST", fc, {"new_password": temp, "confirm_password": temp}, h)[1]["code"], "PASSWORD_UNCHANGED")
        still = self.call("GET", "/api/auth/sessions", None, h)
        self.assertEqual(still[0], 403)

    def test_force_change_completes_recovery(self):
        other = self.login()  # session existante (ancien appareil), ouverte avant la récupération
        rid, temp = self.approved_temp()
        res = self.login_temp(temp)
        h = self.auth_headers(res)
        st, p, _ = self.call("POST", "/api/auth/password/force-change", {"new_password": "Brandnew123", "confirm_password": "Brandnew123"}, h)
        self.assertEqual((st, p["ok"], p["revoked_sessions"]), (200, True, 1))
        # l'app est débloquée, la session courante est conservée, les anciennes sont révoquées
        self.assertEqual(self.call("GET", "/api/auth/sessions", None, h)[0], 200)
        self.assertEqual(self.call("GET", "/api/auth/me", None, self.auth_headers(other))[0], 401)
        # temporaire invalidé, ancien mot de passe remplacé, nouveau accepté
        self.assertEqual(self.login_temp(temp)[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/login", {"email": "teddy@example.com", "password": "Oldpass123"}, {})[0], 401)
        again = self.call("POST", "/api/auth/login", {"email": "teddy@example.com", "password": "Brandnew123"}, {})
        self.assertEqual((again[0], again[1]["must_change_password"]), (200, False))
        row = self.db.execute("SELECT status, temp_hash FROM password_recovery_requests WHERE id = %s", (rid,)).fetchone()
        self.assertEqual((row["status"], row["temp_hash"]), ("completed", ""))
        # impossible de refaire un changement obligatoire une fois fait
        self.assertEqual(self.call("POST", "/api/auth/password/force-change", {"new_password": "Another123", "confirm_password": "Another123"}, h)[1]["code"], "NOT_REQUIRED")

    def test_admin_option_keep_other_sessions(self):
        other = self.login()
        rid = self.req()[1]["request_id"]
        temp = self.approve(rid, revoke=False)[1]["temp_password"]
        h = self.auth_headers(self.login_temp(temp))
        p = self.call("POST", "/api/auth/password/force-change", {"new_password": "Brandnew123", "confirm_password": "Brandnew123"}, h)[1]
        self.assertEqual(p["revoked_sessions"], 0)
        self.assertEqual(self.call("GET", "/api/auth/me", None, self.auth_headers(other))[0], 200)

    def test_admin_can_revoke_all_sessions_of_account(self):
        rid = self.req()[1]["request_id"]
        a, b = self.login(), self.login()
        ah = self.admin()
        st, p, _ = self.admin_post("revoke-sessions", {"id": rid, "confirm": True}, ah)
        self.assertEqual((st, p["revoked_sessions"]), (200, 2))
        self.assertEqual(self.call("GET", "/api/auth/me", None, self.auth_headers(a))[0], 401)

    def test_normal_login_or_password_change_invalidates_pending_temp(self):
        rid, temp = self.approved_temp()
        # l'utilisateur retrouve son mot de passe : le temporaire n'a plus lieu d'être
        self.assertEqual(self.call("POST", "/api/auth/login", {"email": "teddy@example.com", "password": "Oldpass123"}, {})[0], 200)
        self.assertEqual(self.login_temp(temp)[0], 401)
        # changement de mot de passe classique (session ouverte) après une nouvelle approbation
        sess = self.login()
        rid2 = self.req()[1]["request_id"]
        temp2 = self.approve(rid2)[1]["temp_password"]
        body = {"current_password": "Oldpass123", "new_password": "Brandnew123", "confirm_password": "Brandnew123"}
        self.assertEqual(self.call("POST", "/api/auth/change-password", body, self.auth_headers(sess))[0], 200)
        self.assertEqual(self.login_temp(temp2)[0], 401)

    def test_audit_log_complete_and_free_of_secrets(self):
        tok = self.req()[1]
        rid = tok["request_id"]
        temp = self.approve(rid)[1]["temp_password"]
        h = self.auth_headers(self.login_temp(temp))
        self.call("POST", "/api/auth/password/force-change", {"new_password": "Brandnew123", "confirm_password": "Brandnew123"}, h)
        types = {e["event_type"] for e in self.events()}
        for expected in ("RECOVERY_REQUESTED", "RECOVERY_APPROVED", "RECOVERY_TEMP_LOGIN", "RECOVERY_PASSWORD_CHANGED"):
            self.assertIn(expected, types)
        dump = json.dumps(self.events(), default=str)
        for secret in (temp, tok["tracking_token"], "Brandnew123", "Oldpass123", "10.0.0.1"):
            self.assertNotIn(secret, dump)

    def test_status_page_shows_approval_without_secret(self):
        tok = self.req()[1]
        temp = self.approve(tok["request_id"])[1]["temp_password"]
        s = self.call("POST", "/api/auth/recovery/status", {"token": tok["tracking_token"]})[1]
        self.assertEqual(s["request"]["status"], "approved")
        self.assertGreater(s["request"]["temp_expires_at"], 0)
        self.assertNotIn(temp, json.dumps(s))


if __name__ == "__main__":
    unittest.main()
