"""Tests de l'audit de santé/sécurité et des en-têtes de sécurité du serveur."""
import os
import sys
import tempfile
import threading
import types
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")


try:  # dépendances absentes de l'environnement de test : stubs minimaux (jamais utilisés si elles sont installées)
    import binance.client  # noqa: F401
except ModuleNotFoundError:
    _b, _bc, _be = (types.ModuleType(n) for n in ("binance", "binance.client", "binance.exceptions"))

    class _Client:
        def __init__(self, *a, **k):
            self.API_KEY, self.API_SECRET, self.testnet = (a + ("", ""))[0], (a + ("", ""))[1], k.get("testnet", False)

    class _Err(Exception):
        code = None
        message = ""

    _bc.Client, _be.BinanceAPIException, _be.BinanceOrderException = _Client, _Err, _Err
    _b.client, _b.exceptions = _bc, _be
    sys.modules.update({"binance": _b, "binance.client": _bc, "binance.exceptions": _be})
try:
    import database  # noqa: F401
except Exception:  # noqa: BLE001
    _db = types.ModuleType("database")
    _db.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("DB indisponible en test"))
    sys.modules["database"] = _db

import security_audit as sa  # noqa: E402

SERVER_SRC = (Path(__file__).resolve().parent.parent / "web_api_server.py").read_text(encoding="utf-8")


class RouteAnalysisTests(unittest.TestCase):
    def test_real_server_has_a_gate_and_only_expected_public_routes(self):
        a = sa.analyse_routes(SERVER_SRC)
        self.assertTrue(a["gate_found"]["GET"] and a["gate_found"]["POST"])
        for method in ("GET", "POST"):
            public = {r for r in a["public"][method] if not r.endswith("*")} - {"/api", "/assets/"}
            self.assertEqual(public - sa.EXPECTED_PUBLIC[method], set(), method)
        self.assertIn("/api/auth/change-password", a["protected"]["POST"])

    def test_route_placed_before_the_gate_is_reported_public(self):
        src = '''
class H:
    def do_GET(self):
        path = "/"
        if path == "/api/secret-report":
            self._send_json(200, {})
            return
        sess = self._require_auth(require_approved=True)
        if path == "/api/private":
            return
    def do_POST(self):
        path = "/"
        sess = self._require_auth(require_approved=True)
'''
        a = sa.analyse_routes(src)
        self.assertIn("/api/secret-report", a["public"]["GET"])
        self.assertIn("/api/private", a["protected"]["GET"])

    def test_missing_gate_is_detected(self):
        a = sa.analyse_routes("class H:\n    def do_GET(self):\n        path = '/'\n        if path == '/x':\n            pass\n    def do_POST(self):\n        pass\n")
        self.assertFalse(a["gate_found"]["GET"])


class SecretScanTests(unittest.TestCase):
    def test_detects_hardcoded_default_secret_and_ignores_placeholders_and_tests(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cfg.py").write_text('KEY = os.getenv("BINANCE_API_KEY", "Zq8Xv2LmN4pRt7WyB1cD5fGh9JkL3sA6uE0oI8aP")\n')
            (root / "ok.py").write_text('KEY = os.getenv("BINANCE_API_KEY", "")\nTOKEN = "your-token-goes-here-xxxxxxxxxxxxxxxxxxxx"\n')
            (root / "tests").mkdir()
            (root / "tests" / "t.py").write_text('SECRET = "Zq8Xv2LmN4pRt7WyB1cD5fGh9JkL3sA6uE0oI8aP"\n')
            hits = sa.scan_secrets(root)
        self.assertEqual(hits, ["cfg.py:1"])

    def test_repository_has_no_hardcoded_secret(self):
        self.assertEqual(sa.scan_secrets(), [])


class ReportTests(unittest.TestCase):
    def _c(self, status, sev):
        return sa._chk("x", "t", status, sev, "a", "b")

    def test_overall_levels(self):
        build = lambda checks: sa.build_report(checks, 0, 1, "t")["overall"]
        self.assertEqual(build([self._c("pass", "info")]), "ok")
        self.assertEqual(build([self._c("warn", "low")]), "attention")
        self.assertEqual(build([self._c("fail", "high")]), "degraded")
        self.assertEqual(build([self._c("fail", "critical")]), "critical")

    def test_public_status_reveals_no_detail(self):
        with patch.dict(sa._state, {"last": None, "running": True}):
            self.assertEqual(sa.public_status(), "checking")
        down = sa._chk("svc.database", "services", "fail", "critical", "a", "b")
        weak_config = sa._chk("cfg.admin_password", "configuration", "fail", "high", "a", "b")
        leaked = sa._chk("code.secrets", "code", "fail", "high", "a", "b")
        with patch.dict(sa._state, {"last": {"overall": "critical", "checks": [down]}, "running": False}):
            self.assertEqual(sa.public_status(), "degraded")
        # Un constat de configuration/code, même grave, n'est PAS une panne de service.
        with patch.dict(sa._state, {"last": {"overall": "degraded", "checks": [weak_config, leaked]}, "running": False}):
            self.assertEqual(sa.public_status(), "operational")
        with patch.dict(sa._state, {"last": {"overall": "attention", "checks": []}, "running": False}):
            self.assertEqual(sa.public_status(), "operational")

    def test_auto_lock_only_set_on_failure(self):
        self.assertTrue(sa._chk("a", "t", "fail", "critical", "x", "y", auto_lock=True)["auto_lock"])
        self.assertFalse(sa._chk("a", "t", "pass", "critical", "x", "y", auto_lock=True)["auto_lock"])


class LiveServerHeaderTests(unittest.TestCase):
    def test_server_sends_security_headers_and_hides_version_and_refuses_foreign_origin(self):
        try:
            import web_api_server as web
        except Exception as exc:  # noqa: BLE001 (dépendances absentes de l'environnement de test)
            self.skipTest(f"web_api_server non importable ici : {exc}")
        server = ThreadingHTTPServer(("127.0.0.1", 0), web.BitsureAPIHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            sa.configure(server.server_address[1])
            with patch.object(web.health_monitor, "check_db_health", return_value=True):
                checks = {c["id"]: c for c in sa.check_headers()}
        finally:
            server.shutdown()
            server.server_close()
        for cid in ("hdr.x-content-type-options", "hdr.x-frame-options", "hdr.referrer-policy",
                    "hdr.strict-transport-security", "hdr.server", "hdr.cors"):
            self.assertEqual(checks[cid]["status"], "pass", checks[cid])


if __name__ == "__main__":
    unittest.main()
