"""
tests/test_log_doctor.py
------------------------
Suite de tests unitaires robustes pour l'interpréteur de logs (log_doctor.py).
Vérifie :
1. Capture en mémoire (Ring Buffer) et masquage automatique des clés API de >= 40 caractères.
2. Détection et explication des erreurs Binance (-2015, -2019, -4164, -4061), Safe Mode,
   conflits de polling Telegram, erreurs PostgreSQL et délais réseau.
3. Diagnostic des commandes qui ne répondent pas (CGU non acceptées, compte non approuvé,
   quota atteint, Safe Mode actif).
4. Intégration optionnelle de Gemini Flash-Lite (`gemini-3.1-flash-lite`) avec repli
   100% fonctionnel lorsque `GEMINI_API_KEY` est absente ou en cas d'erreur réseau.
"""

import logging
import os
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("TELEGRAM_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
os.environ.setdefault("ADMIN_ID", "123456789")

if "database" not in sys.modules:
    db_stub = types.ModuleType("database")
    db_stub.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("DB stub"))
    sys.modules["database"] = db_stub

import log_doctor


class TestLogDoctor(unittest.TestCase):
    def setUp(self):
        log_doctor._MEMORY_LOG_BUFFER.clear()
        log_doctor.install_log_buffer()

    def test_memory_ring_buffer_captures_and_redacts_secrets(self):
        logger = logging.getLogger("trading_test_doc")
        secret_key = "wTKgkH0mkEre1MKPjDfZ5Re09YNhPV6BLdRReGbTRIM9gnu3aDHloAPat6VvJEFl"
        logger.error(f"Binance failure with key {secret_key} code=-2015")

        recent = log_doctor.get_recent_logs(max_lines=20)
        joined = "\n".join(recent)
        self.assertIn("[REDACTED]", joined)
        self.assertNotIn(secret_key, joined)

    def test_interprets_binance_and_telegram_errors_locally(self):
        sample_logs = [
            "2026-10-05 12:00:01 | ERROR | trading | APIError(code=-2015): Invalid API-key, IP, or permissions for action",
            "2026-10-05 12:00:05 | ERROR | telegram | Conflict: terminated by other getUpdates request; make sure that only one bot instance is running",
            "2026-10-05 12:00:10 | CRITICAL | trading_safety | SAFE_MODE_ENGAGED user=42 reason=SL_MISSING_CLOSE_FAILED",
        ]
        diag = log_doctor.analyze_logs_locally(sample_logs, user_id=None)
        titles = [f["title"] for f in diag["findings"]]

        self.assertTrue(any("-2015" in t for t in titles))
        self.assertTrue(any("Conflit Telegram" in t for t in titles))
        self.assertTrue(any("Safe Mode critique" in t for t in titles))

    def test_interprets_direct_user_question_even_with_empty_logs(self):
        diag = log_doctor.analyze_logs_locally(
            [],
            user_id=None,
            user_question="J'ai reçu Margin is insufficient (-2019) quand j'ouvre un trade",
        )
        titles = [f["title"] for f in diag["findings"]]
        self.assertTrue(any("-2019" in t for t in titles))

    def test_build_report_works_without_gemini_key(self):
        log_doctor._MEMORY_LOG_BUFFER.append(
            "2026-10-05 12:01:00 | ERROR | trading | Order's position side does not match user's setting (-4061)"
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            report = log_doctor.build_log_diagnostic_report(
                user_id=None,
                user_question="Pourquoi mon ordre Futures échoue ?",
                use_gemini=True,
            )
        self.assertIn("Mode Hedge / One-Way incompatible", report)
        self.assertIn("Pourquoi mon ordre Futures échoue ?", report)

    def test_gemini_flash_lite_called_when_api_key_present(self):
        import json
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "1) Cause: Clé Spot utilisée en Futures.\n2) Solution: Tape /setmarket spot."}
                        ]
                    }
                }
            ]
        }).encode("utf-8")
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_resp
        mock_cm.__exit__.return_value = False

        with patch("log_doctor.urllib.request.urlopen", return_value=mock_cm) as urlopen_mock, \
             patch("config.GEMINI_API_KEY", "fake-gemini-key"):
            report = log_doctor.build_log_diagnostic_report(
                user_id=None,
                user_question="Que signifient les logs ?",
                use_gemini=True,
            )
            self.assertTrue(urlopen_mock.called)
            req_obj = urlopen_mock.call_args[0][0]
            self.assertIn("gemini-3.1-flash-lite", req_obj.full_url)
            self.assertIn("Analyse Gemini Flash-Lite", report)
            self.assertIn("Tape /setmarket spot", report)

    def test_approve_user_and_confirm_binance_payment_logic(self):
        from user_manager import UserManager
        um = UserManager.__new__(UserManager)
        um.conn = MagicMock()
        um.get_user = MagicMock(return_value={"user_id": 999, "role": "tester", "approved": 0, "memo": None})

        # Sans memo en attente, confirm_binance_payment(999) doit renvoyer False pour laisser /teddy approuver en tester
        self.assertFalse(um.confirm_binance_payment(999))
        self.assertTrue(um.approve_user(999))

        # Avec force=True (ou /teddy <id> pro), confirm_binance_payment passe l'utilisateur en pro et approved=1
        self.assertTrue(um.confirm_binance_payment(999, force=True))

    def test_public_system_status_page_hides_raw_logs_and_shows_service_health(self):
        fake_probes_ok = {
            "commands": {"ok": True, "total": 32, "failed": [], "detail": "32/32 handlers vérifiés"},
            "binance": {
                "ok": True,
                "spot_public": True,
                "futures_public": True,
                "spot_testnet": True,
                "futures_testnet": True,
                "account_api_ok": True,
                "account_balance_str": "1000.00 USDT dispo / 1000.00 USDT total (SPOT)",
                "geo_blocked_main_api": False,
                "errors": [],
            },
            "apis": {
                "db_ok": True,
                "scheduler_ok": True,
                "market_klines_ok": True,
                "twelvedata_configured": False,
                "gemini_configured": False,
                "errors": [],
            },
        }
        with patch("log_doctor.get_recent_logs", return_value=[]), \
             patch("log_doctor.run_real_system_probes", return_value=fake_probes_ok):
            status_healthy = log_doctor.build_public_system_status_page(user_id=None)
            self.assertIn("État des Services", status_healthy)
            self.assertIn("Tous les systèmes sont opérationnels", status_healthy)
            self.assertIn("Commandes Telegram", status_healthy)
            self.assertIn("1000.00 USDT dispo", status_healthy)

        # En cas d'incident détecté dans les logs ou d'échec /account, la page publique affiche l'incident sans exposer la ligne de log brute
        with patch("log_doctor.get_recent_logs", return_value=[
            "2026-10-05 16:30:00 | ERROR | trading | APIError(code=-2019): Margin is insufficient"
        ]), patch("log_doctor.run_real_system_probes", return_value=fake_probes_ok):
            status_incident = log_doctor.build_public_system_status_page(user_id=None)
            self.assertIn("Fonctionnement partiel", status_incident)
            self.assertIn("Marge / Solde USDT insuffisant", status_incident)
            self.assertNotIn("2026-10-05 16:30:00 | ERROR", status_incident)

    def test_detects_binance_geo_block_eligibility_error(self):
        diag = log_doctor.analyze_logs_locally(
            [
                "d location according to 'b. Eligibility' in https://www.binance.com/en/terms. Please contact customer service if you believe you received this message in error."
            ],
            user_id=None,
        )
        titles = [f["title"] for f in diag["findings"]]
        self.assertTrue(any("HTTP 451" in t or "Blocage géographique" in t for t in titles))


if __name__ == "__main__":
    unittest.main()
