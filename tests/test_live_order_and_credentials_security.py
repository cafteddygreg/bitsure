import importlib
import io
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")
import sitecustomize  # noqa: F401


def _make_api_handler(mod, method: str, path: str, body: dict, headers: dict | None = None):
    raw_body = json.dumps(body).encode("utf-8")
    req_headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(raw_body)),
        "X-Session-Token": "valid-token",
    }
    if headers:
        req_headers.update(headers)
    handler = mod.BitsureAPIHandler.__new__(mod.BitsureAPIHandler)
    handler.command = method
    handler.path = path
    handler.client_address = ("127.0.0.1", 12345)
    handler.headers = req_headers
    handler.rfile = io.BytesIO(raw_body)
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


class TestLiveOrderAndCredentialsSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved_modules = dict(sys.modules)
        for mod_name in ("binance", "binance.exceptions", "binance.client"):
            if mod_name not in sys.modules:
                sys.modules[mod_name] = MagicMock()
        if not hasattr(sys.modules["binance.exceptions"], "BinanceAPIException"):
            sys.modules["binance.exceptions"].BinanceAPIException = Exception
            sys.modules["binance.exceptions"].BinanceOrderException = Exception
        if "database" in sys.modules and not hasattr(sys.modules["database"], "get_db"):
            sys.modules["database"].get_db = MagicMock()
            sys.modules["database"].get_connection = MagicMock()

        for mod_name in (
            "config",
            "crypto_utils",
            "trading_config",
            "binance_manager",
            "live_trader",
            "migrate_encrypt_credentials",
            "web_api_server",
        ):
            sys.modules.pop(mod_name, None)

        for mod_name in (
            "signal_engine",
            "data_fetcher",
            "paper_trader",
            "alert_manager",
            "history_manager",
            "decision_journal",
            "health_monitor",
            "indicators",
            "strategy_lab",
        ):
            sys.modules[mod_name] = MagicMock()

        cls.config = importlib.import_module("config")
        cls.crypto_utils = importlib.import_module("crypto_utils")
        cls.trading_config = importlib.import_module("trading_config")
        cls.binance_manager = importlib.import_module("binance_manager")
        cls.live_trader = importlib.import_module("live_trader")
        cls.migrate_mod = importlib.import_module("migrate_encrypt_credentials")
        cls.web_api_server = importlib.import_module("web_api_server")

    @classmethod
    def tearDownClass(cls):
        for k in list(sys.modules.keys()):
            if k not in cls._saved_modules:
                sys.modules.pop(k, None)
        sys.modules.update(cls._saved_modules)

    def _default_cfg(self, user_id: int = 42, leverage: int = 5, risk_per_trade: float = 1.0):
        return self.trading_config.TradingConfig(
            user_id=user_id,
            auto_trade=False,
            risk_per_trade=risk_per_trade,
            max_daily_loss=5.0,
            max_positions=3,
            min_score=68,
            leverage=leverage,
            market_type="futures",
            symbol_whitelist=["BTCUSDT", "ETHUSDT"],
            testnet=True,
        )

    # ------------------------------------------------------------------
    # TASK 1: POST /api/trading/live-order & live_trader.py
    # ------------------------------------------------------------------
    def test_live_order_without_sl_is_rejected(self):
        lt = self.live_trader
        bm = self.binance_manager
        cfg = self._default_cfg(leverage=5)
        with patch.object(lt, "get_config", return_value=cfg):
            draft = lt.build_draft(
                user_id=42,
                symbol="BTCUSDT",
                side="BUY",
                amount=50.0,
                leverage=2,
                sl_price=None,
                tp_price=68000.0,
            )
            with self.assertRaises(bm.BinanceClientError) as ctx:
                lt.validate_draft(42, draft)
            self.assertIn("Stop-Loss", str(ctx.exception))

    def test_live_order_leverage_above_user_config_is_rejected(self):
        lt = self.live_trader
        bm = self.binance_manager
        cfg = self._default_cfg(leverage=5)
        with patch.object(lt, "get_config", return_value=cfg):
            draft = lt.build_draft(
                user_id=42,
                symbol="BTCUSDT",
                side="BUY",
                amount=50.0,
                leverage=10,  # > cfg.leverage (5)
                sl_price=64000.0,
                tp_price=68000.0,
            )
            with self.assertRaises(bm.BinanceClientError) as ctx:
                lt.validate_draft(42, draft)
            self.assertIn("dépasse le levier configuré", str(ctx.exception))

    def test_live_order_sl_loss_exceeding_risk_per_trade_is_rejected(self):
        lt = self.live_trader
        bm = self.binance_manager
        # balance=1000, risk_per_trade=1% -> max_risk = 10 USDT
        # amount=100, lev=5 -> notional=500 at price=50000 -> qty=0.01
        # SL at 48000 -> |50000 - 48000| * 0.01 = 20 USDT > 10 USDT -> rejected!
        cfg = self._default_cfg(leverage=5, risk_per_trade=1.0)
        mock_client = MagicMock()
        mock_client.futures_leverage_bracket.return_value = [{"brackets": [{"initialLeverage": 50}]}]
        filters = {
            "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
            "PRICE_FILTER": {"tickSize": "0.1"},
            "MIN_NOTIONAL": {"notional": "5.0"},
        }
        with patch.object(lt, "get_config", return_value=cfg), \
             patch.object(lt, "check_can_open_position", return_value=MagicMock(allowed=True, reason="")), \
             patch.object(lt, "_client_for_user", return_value=mock_client), \
             patch.object(lt, "get_symbol_filters", return_value=filters), \
             patch.object(lt, "get_account_balance", return_value=1000.0), \
             patch.object(lt, "get_price", return_value=50000.0):
            draft = lt.build_draft(
                user_id=42,
                symbol="BTCUSDT",
                side="BUY",
                amount=100.0,
                leverage=5,
                sl_price=48000.0,
                tp_price=55000.0,
            )
            with self.assertRaises(bm.BinanceClientError) as ctx:
                lt.validate_draft(42, draft)
            self.assertIn("Perte potentielle au SL", str(ctx.exception))

    def test_live_order_execute_without_pin_is_rejected(self):
        was = self.web_api_server
        session = {"user_id": 42, "role": "pro", "csrf_token": "csrf-1"}
        handler = _make_api_handler(
            was,
            "POST",
            "/api/trading/live-order",
            {
                "action": "execute",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "amount": 20.0,
                "leverage": 2,
                "sl_price": 49800.0,
                "tp_price": 51000.0,
                "idempotency_key": "idem-no-pin-1",
                # Missing "pin"
            },
        )
        handler._require_auth = MagicMock(return_value=session)
        with patch.object(was, "ensure_web_schema_initialized", return_value=None):
            handler.do_POST()
        self.assertEqual(handler._sent_status, 403)
        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertIn("PIN", payload["error"])

    def test_concurrent_same_idempotency_key_executes_only_one_binance_order(self):
        lt = self.live_trader
        bm = self.binance_manager
        cfg = self._default_cfg(leverage=5, risk_per_trade=2.0)

        mock_client = MagicMock()
        mock_client.futures_leverage_bracket.return_value = [{"brackets": [{"initialLeverage": 50}]}]

        entry_calls = []

        def fake_futures_create_order(**kwargs):
            if kwargs.get("type") in ("MARKET", "LIMIT"):
                time.sleep(0.05)
                entry_calls.append(kwargs)
                return {"orderId": 90001, "clientOrderId": kwargs.get("newClientOrderId"), "avgPrice": "50000.0"}
            return {"orderId": 90002}

        mock_client.futures_create_order.side_effect = fake_futures_create_order

        filters = {
            "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
            "PRICE_FILTER": {"tickSize": "0.1"},
            "MIN_NOTIONAL": {"notional": "5.0"},
        }

        # Stateful in-memory table simulation for order_idempotency
        idem_rows = {}
        idem_lock = threading.Lock()

        class FakeCursor:
            def __init__(self):
                self._last_row = None

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                s = " ".join(sql.split()).upper()
                if s.startswith("SELECT RESULT_JSON FROM ORDER_IDEMPOTENCY"):
                    with idem_lock:
                        val = idem_rows.get((params[0], params[1]))
                        self._last_row = (val,) if val is not None else None
                elif s.startswith("INSERT INTO ORDER_IDEMPOTENCY"):
                    with idem_lock:
                        idem_rows[(params[0], params[1])] = params[2]
                    self._last_row = None
                else:
                    self._last_row = None

            def fetchone(self):
                return self._last_row

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        user_lock = threading.Lock()

        from contextlib import contextmanager

        @contextmanager
        def fake_user_trading_lock(uid):
            with user_lock:
                yield FakeConn()

        lt._IDEMPOTENCY_MEMORY_STORE.clear()
        with patch.object(lt, "get_config", return_value=cfg), \
             patch.object(lt, "user_trading_lock", side_effect=fake_user_trading_lock), \
             patch.object(lt, "_assert_order_context_allowed", return_value=None), \
             patch.object(lt, "check_can_open_position", return_value=MagicMock(allowed=True, reason="")), \
             patch.object(lt, "_client_for_user", return_value=mock_client), \
             patch.object(lt, "get_open_binance_positions", return_value=[]), \
             patch.object(lt, "set_leverage", return_value=None), \
             patch.object(lt, "get_symbol_filters", return_value=filters), \
             patch.object(lt, "get_account_balance", return_value=1000.0), \
             patch.object(lt, "get_price", return_value=50000.0), \
             patch.object(lt, "get_connection", side_effect=FakeConn), \
             patch.object(lt.security_manager, "verify_code", return_value=(True, "OK")), \
             patch.object(bm, "_cancel_conflicting_futures_protective_orders", return_value=0):

            draft = lt.build_draft(
                user_id=42,
                symbol="BTCUSDT",
                side="BUY",
                amount=50.0,
                leverage=2,
                sl_price=49500.0,
                tp_price=52000.0,
            )

            results = [None, None]
            errors = []

            def worker(idx):
                try:
                    results[idx] = lt.execute_draft(
                        42,
                        draft,
                        execution_context=bm.ORDER_CONTEXT_MANUAL_AUTHENTICATED,
                        pin="123456",
                        idempotency_key="concurrent-key-999",
                    )
                except Exception as exc:
                    errors.append(exc)

            t1 = threading.Thread(target=worker, args=(0,))
            t2 = threading.Thread(target=worker, args=(1,))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(errors, [])
            self.assertEqual(len(entry_calls), 1, "Binance main order must be called only ONCE for duplicate idempotency_key")
            self.assertEqual(results[0]["order"]["orderId"], 90001)
            self.assertEqual(results[1]["order"]["orderId"], 90001)

    # ------------------------------------------------------------------
    # TASK 2: Chiffrement des clés Binance au repos & permissions retrait
    # ------------------------------------------------------------------
    def test_encryption_at_rest_round_trip_and_legacy_plaintext_compatibility(self):
        cu = self.crypto_utils
        tc = self.trading_config

        stored_db = {}

        class CredCursor:
            def __init__(self):
                self._row = None

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                s = " ".join(sql.split()).upper()
                if s.startswith("INSERT INTO BINANCE_CREDENTIALS"):
                    uid, k, sec, testnet = params
                    stored_db[uid] = (k, sec, testnet, True)
                elif s.startswith("SELECT API_KEY, API_SECRET, TESTNET, IS_VALID FROM BINANCE_CREDENTIALS"):
                    self._row = stored_db.get(params[0])

            def fetchone(self):
                return self._row

        class CredConn:
            def cursor(self):
                return CredCursor()

            def commit(self):
                pass

            def close(self):
                pass

        cfg = self._default_cfg(user_id=77)
        with patch.object(cu.config, "ENCRYPTION_KEY", "my-test-secret-encryption-key-32b"), \
             patch.object(tc, "get_connection", side_effect=CredConn), \
             patch.object(tc, "get_config", return_value=cfg):

            # 1. Save credentials -> value in DB != plaintext and starts with enc:v1:
            tc.save_binance_credentials(77, "PLAIN_API_KEY_123", "PLAIN_API_SECRET_456", testnet=True)
            raw_key_in_db, raw_secret_in_db, _, _ = stored_db[77]
            self.assertNotEqual(raw_key_in_db, "PLAIN_API_KEY_123")
            self.assertNotEqual(raw_secret_in_db, "PLAIN_API_SECRET_456")
            self.assertTrue(raw_key_in_db.startswith("enc:v1:"))
            self.assertTrue(raw_secret_in_db.startswith("enc:v1:"))

            # 2. Round-trip via get_binance_credentials
            creds = tc.get_binance_credentials(77, market_type="futures")
            self.assertEqual(creds["api_key"], "PLAIN_API_KEY_123")
            self.assertEqual(creds["api_secret"], "PLAIN_API_SECRET_456")

            # 3. Legacy unprefixed value in DB remains readable
            stored_db[77] = ("LEGACY_RAW_KEY", "LEGACY_RAW_SECRET", True, True)
            legacy_creds = tc.get_binance_credentials(77, market_type="futures")
            self.assertEqual(legacy_creds["api_key"], "LEGACY_RAW_KEY")
            self.assertEqual(legacy_creds["api_secret"], "LEGACY_RAW_SECRET")

            # 4. Migration script dry-run vs --apply (idempotent)
            with patch.object(self.migrate_mod, "get_connection", side_effect=lambda: self._make_migration_conn(stored_db)):
                dry_stats = self.migrate_mod.migrate_credentials(apply=False)
                self.assertEqual(dry_stats["to_migrate"], 1)
                self.assertEqual(stored_db[77][0], "LEGACY_RAW_KEY")

                apply_stats = self.migrate_mod.migrate_credentials(apply=True)
                self.assertEqual(apply_stats["migrated"], 1)
                self.assertTrue(stored_db[77][0].startswith("enc:v1:"))
                self.assertTrue(stored_db[77][1].startswith("enc:v1:"))

                # Second apply is idempotent (0 migrated)
                second_stats = self.migrate_mod.migrate_credentials(apply=True)
                self.assertEqual(second_stats["migrated"], 0)
                self.assertEqual(second_stats["already_encrypted"], 1)

    @staticmethod
    def _make_migration_conn(stored_db: dict):
        class MigCursor:
            def __init__(self):
                self._rows = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                s = " ".join(sql.split()).upper()
                if s.startswith("SELECT USER_ID, API_KEY, API_SECRET FROM BINANCE_CREDENTIALS"):
                    self._rows = [(uid, vals[0], vals[1]) for uid, vals in stored_db.items()]
                elif s.startswith("UPDATE BINANCE_CREDENTIALS"):
                    new_k, new_s, uid = params
                    old = stored_db[uid]
                    stored_db[uid] = (new_k, new_s, old[2], old[3])

            def fetchall(self):
                return self._rows

        class MigConn:
            def cursor(self):
                return MigCursor()

            def commit(self):
                pass

            def close(self):
                pass

        return MigConn()

    def test_api_key_with_withdrawals_enabled_is_rejected_and_not_saved(self):
        was = self.web_api_server
        bm = self.binance_manager

        mock_client = MagicMock()
        mock_client.get_api_key_permission.return_value = {
            "ipRestrict": False,
            "enableReading": True,
            "enableSpotAndMarginTrading": True,
            "enableWithdrawals": True,
        }

        with patch.object(bm, "_build_resilient_client", return_value=mock_client):
            with self.assertRaises(bm.BinanceClientError) as ctx:
                bm.check_api_key_permissions("k_withdraw", "s_withdraw", testnet=False)
            self.assertIn("enableWithdrawals", str(ctx.exception))

        # Also test via POST /api/trading/credentials -> HTTP 400 and save_binance_credentials NOT called
        session = {"user_id": 42, "role": "pro", "csrf_token": "csrf-1"}
        handler = _make_api_handler(
            was,
            "POST",
            "/api/trading/credentials",
            {"api_key": "k_withdraw", "api_secret": "s_withdraw", "testnet": False},
        )
        handler._require_auth = MagicMock(return_value=session)
        with patch.object(was, "ensure_web_schema_initialized", return_value=None), \
             patch.object(bm, "_build_resilient_client", return_value=mock_client), \
             patch.object(was.trading_config, "save_binance_credentials") as mock_save:
            handler.do_POST()
            self.assertEqual(handler._sent_status, 400)
            mock_save.assert_not_called()

    def test_missing_encryption_key_in_production_raises_error(self):
        cu = self.crypto_utils
        with patch.object(cu.config, "ENCRYPTION_KEY", ""), \
             patch.dict(os.environ, {"ENCRYPTION_KEY": "", "ENV": "production"}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                cu.resolve_encryption_key("")
            self.assertIn("ENCRYPTION_KEY", str(ctx.exception))

        with patch.object(cu.config, "ENCRYPTION_KEY", ""), \
             patch.dict(os.environ, {"ENCRYPTION_KEY": "", "ENV": "development", "DATABASE_URL": "postgresql://user:pass@host/db"}, clear=False):
            with self.assertRaises(RuntimeError) as ctx2:
                cu.resolve_encryption_key("")
            self.assertIn("ENCRYPTION_KEY", str(ctx2.exception))


if __name__ == "__main__":
    unittest.main()
