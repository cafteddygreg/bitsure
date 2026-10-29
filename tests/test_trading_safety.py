import os
import time
import unittest
import sys
import types
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

# Unit tests avoid requiring local PostgreSQL/psycopg2 dependencies.
database_stub = types.ModuleType("database")
database_stub.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("DB not available in unit test"))
database_stub.get_db = lambda: None
sys.modules.setdefault("database", database_stub)
logger_stub = types.ModuleType("trading_logger")
class _Logger:
    def critical(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def info(self, *a, **k): pass
    def debug(self, *a, **k): pass
logger_stub.get_trading_logger = lambda name: _Logger()
logger_stub.log_trade_opened = lambda *a, **k: None
logger_stub.log_trade_closed = lambda *a, **k: None
logger_stub.log_error = lambda *a, **k: None
logger_stub.LOG_PATH = "trading.log"
class _RedactFilter:
    def filter(self, record): return True
logger_stub.RedactSensitiveFilter = _RedactFilter
sys.modules.setdefault("trading_logger", logger_stub)

telegram_stub = types.ModuleType("telegram")
class _Button:
    def __init__(self, *a, **k): pass
class _Markup:
    def __init__(self, *a, **k): pass
telegram_stub.InlineKeyboardButton = _Button
telegram_stub.InlineKeyboardMarkup = _Markup
sys.modules.setdefault("telegram", telegram_stub)
telegram_ext_stub = types.ModuleType("telegram.ext")
class _ContextTypes:
    DEFAULT_TYPE = object
telegram_ext_stub.ContextTypes = _ContextTypes
sys.modules.setdefault("telegram.ext", telegram_ext_stub)

binance_stub = types.ModuleType("binance")
binance_exceptions_stub = types.ModuleType("binance.exceptions")
class _BinanceAPIException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.message = str(args[0]) if args else ""
class _BinanceOrderException(Exception): pass
binance_exceptions_stub.BinanceAPIException = _BinanceAPIException
binance_exceptions_stub.BinanceOrderException = _BinanceOrderException
sys.modules.setdefault("binance", binance_stub)
sys.modules.setdefault("binance.exceptions", binance_exceptions_stub)
binance_client_stub = types.ModuleType("binance.client")
class _Client: pass
binance_client_stub.Client = _Client
sys.modules.setdefault("binance.client", binance_client_stub)

binance_manager_stub = types.ModuleType("binance_manager")
class _BinanceClientError(Exception): pass
binance_manager_stub.BinanceClientError = _BinanceClientError
binance_manager_stub.open_position = lambda *a, **k: {"quantity": a[3] if len(a) > 3 else k.get("quantity", 0), "order_id": "1", "client_order_id": k.get("client_order_id")}
binance_manager_stub.get_price = lambda *a, **k: 100.0
binance_manager_stub.get_tradable_symbols = lambda *a, **k: []
binance_manager_stub.get_klines_dataframe = lambda *a, **k: None
binance_manager_stub.make_client_order_id = lambda prefix, unique_key: f"{prefix}_{unique_key}"
binance_manager_stub.close_position = lambda *a, **k: {"order_id": "close"}
binance_manager_stub.cancel_order = lambda *a, **k: None
binance_manager_stub.get_open_binance_positions = lambda *a, **k: []
binance_manager_stub.get_open_binance_orders = lambda *a, **k: []
binance_manager_stub.replace_futures_stop_loss_order = lambda *a, **k: "sl_new"
binance_manager_stub.ORDER_CONTEXT_AUTOTRADE = "autotrade"
binance_manager_stub.ORDER_CONTEXT_MANUAL_AUTHENTICATED = "manual_authenticated"
binance_manager_stub.ORDER_CONTEXT_EMERGENCY = "emergency_stop"
sys.modules.setdefault("binance_manager", binance_manager_stub)
for _attr, _val in vars(binance_manager_stub).items():
    if not _attr.startswith("__") and not hasattr(sys.modules["binance_manager"], _attr):
        setattr(sys.modules["binance_manager"], _attr, _val)

risk_manager_stub = types.ModuleType("risk_manager")
class _RiskResult:
    def __init__(self, allowed=True, reason=None):
        self.allowed = allowed
        self.reason = reason
risk_manager_stub.check_can_open_position = lambda *a, **k: _RiskResult(True)
risk_manager_stub.calculate_position_size = lambda *a, **k: 0.1
risk_manager_stub.record_trade_loss = lambda *a, **k: 0.0
risk_manager_stub.EPSILON = 1e-8
sys.modules.setdefault("risk_manager", risk_manager_stub)

history_manager_stub = types.ModuleType("history_manager")
class _HistoryManager:
    @classmethod
    def get_instance(cls): return cls()
history_manager_stub.HistoryManager = _HistoryManager
sys.modules.setdefault("history_manager", history_manager_stub)

signal_engine_stub = types.ModuleType("signal_engine")
class _SignalEngine: pass
signal_engine_stub.SignalEngine = _SignalEngine
sys.modules.setdefault("signal_engine", signal_engine_stub)

from trading_config import TradingConfig
from trading_safety import SafetyError, validate_signal_freshness


class TradingSafetyTests(unittest.TestCase):
    def test_stale_signal_is_rejected(self):
        signal = {"created_at": time.time() - 901}
        with self.assertRaises(SafetyError):
            validate_signal_freshness(signal, max_age_seconds=900)

    def test_duplicate_reserved_signal_does_not_open_order(self):
        import execution_engine

        signal = {
            "id": "sig-1",
            "user_id": 42,
            "symbol": "BTCUSDT",
            "direction": "BUY",
            "entry_price": 100.0,
            "sl": 95.0,
            "tp": 110.0,
            "score": 90,
            "status": "pending",
            "created_at": time.time(),
        }
        config = TradingConfig(user_id=42, auto_trade=True)
        with patch.object(execution_engine, "reserve_signal_for_execution", side_effect=SafetyError("already used")), \
             patch.object(execution_engine, "open_position") as open_position:
            result = execution_engine.execute_signal(signal, config)

        open_position.assert_not_called()
        self.assertEqual(result["status"], "skipped")
        self.assertIn("already used", result["error_message"])

    def test_safety_lock_persists_after_24h_and_sends_reminder_once(self):
        """safety_lock ne doit plus expirer seul même après 24h et envoie un rappel une seule fois."""
        import execution_engine
        import trading_safety
        from execution_engine import validate_signal_for_execution
        from trading_safety import assert_trading_allowed

        base_now = 1_700_000_000.0
        signal = {
            "id": "sig-2",
            "user_id": 42,
            "symbol": "BTCUSDT",
            "direction": "BUY",
            "entry_price": 100.0,
            "sl": 95.0,
            "tp": 110.0,
            "score": 90,
            "status": "pending",
            "created_at": base_now + 86400.0,
        }
        lock_config = TradingConfig(
            user_id=42,
            auto_trade=True,
            safety_lock=True,
            safety_lock_reason="divergence",
            safety_lock_at=base_now,
            safety_lock_ttl_seconds=3600,
            safety_lock_reminded=False,
        )

        # Horloge avancée de 24 h (86 400 s > TTL 3 600 s)
        with patch("trading_safety.time.time", return_value=base_now + 86400.0), \
             patch("trading_safety.update_config", return_value=lock_config) as upd_mock, \
             patch("trading_safety._dispatch_or_queue_notification") as notify_mock:
            # 1er appel : SafetyError levée et rappel envoyé une fois
            with self.assertRaises(SafetyError):
                assert_trading_allowed(lock_config)
            self.assertTrue(lock_config.safety_lock)
            self.assertFalse(lock_config.safety_warn)
            self.assertTrue(lock_config.safety_lock_reminded)
            self.assertEqual(notify_mock.call_count, 1)
            upd_mock.assert_called_once_with(42, safety_lock_reminded=True)

            # 2e appel : SafetyError toujours levée, aucun second rappel envoyé
            with self.assertRaises(SafetyError):
                assert_trading_allowed(lock_config)
            self.assertEqual(notify_mock.call_count, 1)

            # Validation de signal : toujours refusée tant que /clearsafe n'a pas été exécuté
            with patch.object(execution_engine, "check_can_open_position", return_value=_RiskResult(True)):
                allowed_after, reason_after = validate_signal_for_execution(42, signal, lock_config)
            self.assertFalse(allowed_after)
            self.assertIn("Safe mode actif", reason_after)

    def test_timeout_after_main_order_places_protection_or_engages_safe_mode(self):
        """Timeout réseau après l'ordre principal -> relit clientOrderId/position et pose la protection ou engage_safe_mode."""
        import importlib.machinery
        import importlib.util
        import requests
        spec = importlib.machinery.PathFinder.find_spec("binance_manager")
        real_bm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(real_bm)

        class MockClient:
            def __init__(self):
                self.calls = []
                self.fail_main_with_timeout = True
                self.fail_protection_and_close = False

            def futures_create_order(self, **kwargs):
                self.calls.append(("futures_create_order", kwargs))
                if kwargs.get("type") == "MARKET" and not kwargs.get("reduceOnly"):
                    if self.fail_main_with_timeout:
                        raise requests.Timeout("Read timed out after main order")
                    return {"orderId": 101, "clientOrderId": kwargs.get("newClientOrderId"), "status": "FILLED", "avgPrice": "100.0"}
                if self.fail_protection_and_close:
                    raise requests.RequestException("Network down for protection and reduceOnly")
                return {"orderId": 202 if kwargs.get("type") == "STOP_MARKET" else 203}

            def futures_get_order(self, **kwargs):
                self.calls.append(("futures_get_order", kwargs))
                if self.fail_protection_and_close:
                    raise requests.Timeout("Still timed out")
                return {
                    "orderId": 101,
                    "clientOrderId": kwargs.get("origClientOrderId"),
                    "status": "FILLED",
                    "avgPrice": "100.0",
                }

            def futures_get_open_orders(self, **kwargs):
                return []

        mock_client = MockClient()
        filters = {
            "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
            "PRICE_FILTER": {"tickSize": "0.10"},
            "MIN_NOTIONAL": {"notional": "5.0"},
        }

        def fake_algo_ok(client, symbol, side, otype, trigger, **kw):
            # Depuis la migration Binance, SL/TP passent par l'API Algo (/fapi/v1/algoOrder).
            return {"orderId": 202 if otype == "STOP_MARKET" else 203, "algo": True}

        def fake_algo_down(client, symbol, side, otype, trigger, **kw):
            raise real_bm.BinanceAlgoError("Network down for protection")

        # Cas A : Timeout sur l'ordre principal, mais l'ordre a été exécuté sur Binance -> relit clientOrderId et pose SL/TP
        pos_calls = [
            [],  # avant l'ouverture : aucune position existante
            [{"symbol": "BTCUSDT", "direction": "BUY", "quantity": 0.1}],  # après timeout : position présente
        ]
        with patch.object(real_bm, "futures_place_conditional_order", side_effect=fake_algo_ok), \
             patch.object(real_bm, "futures_list_conditional_orders", return_value=[]), \
             patch.object(real_bm, "_assert_order_context_allowed", return_value=None), \
             patch.object(real_bm, "_client_for_user", return_value=mock_client), \
             patch.object(real_bm, "get_open_binance_positions", side_effect=lambda *a, **k: pos_calls.pop(0) if pos_calls else []), \
             patch.object(real_bm, "get_symbol_filters", return_value=filters), \
             patch.object(real_bm, "get_price", return_value=100.0), \
             patch.object(real_bm, "set_leverage", return_value=None):
            res = real_bm.open_position(
                user_id=42,
                symbol="BTCUSDT",
                direction="BUY",
                quantity=0.1,
                sl_price=95.0,
                tp_price=110.0,
                market_type="futures",
                leverage=5,
                client_order_id="sig_uuid123",
            )
        self.assertEqual(str(res["order_id"]), "101")
        self.assertEqual(str(res["sl_order_id"]), "202")
        self.assertEqual(str(res["tp_order_id"]), "203")

        # Cas B : Timeout et échec complet de protection + fermeture reduceOnly -> engage_safe_mode appelé
        mock_client_fail = MockClient()
        mock_client_fail.fail_main_with_timeout = True
        mock_client_fail.fail_protection_and_close = True
        pos_calls_b = [
            [],
            [{"symbol": "BTCUSDT", "direction": "BUY", "quantity": 0.1}],
        ]
        with patch.object(real_bm, "futures_place_conditional_order", side_effect=fake_algo_down), \
             patch.object(real_bm, "futures_list_conditional_orders", return_value=[]), \
             patch.object(real_bm, "_assert_order_context_allowed", return_value=None), \
             patch.object(real_bm, "_client_for_user", return_value=mock_client_fail), \
             patch.object(real_bm, "get_open_binance_positions", side_effect=lambda *a, **k: pos_calls_b.pop(0) if pos_calls_b else []), \
             patch.object(real_bm, "get_symbol_filters", return_value=filters), \
             patch.object(real_bm, "get_price", return_value=100.0), \
             patch.object(real_bm, "set_leverage", return_value=None), \
             patch.object(real_bm, "engage_safe_mode") as safe_mock:
            with self.assertRaises(real_bm.BinanceClientError):
                real_bm.open_position(
                    user_id=42,
                    symbol="BTCUSDT",
                    direction="BUY",
                    quantity=0.1,
                    sl_price=95.0,
                    tp_price=110.0,
                    market_type="futures",
                    leverage=5,
                    client_order_id="sig_uuid456",
                )
            safe_mock.assert_called_once()

    def test_sl_failure_triggers_reduce_only_close(self):
        """Échec de la pose du SL après l'ordre principal -> fermeture immédiate en reduceOnly."""
        import importlib
        spec = importlib.machinery.PathFinder.find_spec("binance_manager")
        real_bm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(real_bm)

        created_orders = []

        class MockClient:
            def futures_create_order(self, **kwargs):
                created_orders.append(kwargs)
                if kwargs.get("type") == "MARKET" and not kwargs.get("reduceOnly"):
                    return {"orderId": 500, "clientOrderId": kwargs.get("newClientOrderId"), "status": "FILLED", "avgPrice": "100.0"}
                if kwargs.get("type") == "STOP_MARKET":
                    raise real_bm.BinanceOrderException("SL rejected by exchange")
                if kwargs.get("reduceOnly"):
                    return {"orderId": 501, "status": "FILLED"}
                return {"orderId": 502}

            def futures_get_open_orders(self, **kwargs):
                return []

        filters = {
            "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
            "PRICE_FILTER": {"tickSize": "0.10"},
            "MIN_NOTIONAL": {"notional": "5.0"},
        }
        def fake_algo_sl_rejected(client, symbol, side, otype, trigger, **kw):
            raise real_bm.BinanceAlgoError("Code -2021: SL rejected by exchange", code=-2021)

        pos_calls = [
            [],
            [{"symbol": "BTCUSDT", "direction": "BUY", "quantity": 0.1}],
        ]
        with patch.object(real_bm, "futures_place_conditional_order", side_effect=fake_algo_sl_rejected), \
             patch.object(real_bm, "futures_list_conditional_orders", return_value=[]), \
             patch.object(real_bm, "_assert_order_context_allowed", return_value=None), \
             patch.object(real_bm, "_client_for_user", return_value=MockClient()), \
             patch.object(real_bm, "get_open_binance_positions", side_effect=lambda *a, **k: pos_calls.pop(0) if pos_calls else []), \
             patch.object(real_bm, "get_symbol_filters", return_value=filters), \
             patch.object(real_bm, "get_price", return_value=100.0), \
             patch.object(real_bm, "set_leverage", return_value=None):
            with self.assertRaises(real_bm.BinanceClientError) as ctx:
                real_bm.open_position(
                    user_id=42,
                    symbol="BTCUSDT",
                    direction="BUY",
                    quantity=0.1,
                    sl_price=95.0,
                    tp_price=110.0,
                    market_type="futures",
                    leverage=5,
                )
        self.assertIn("refermé", str(ctx.exception))
        reduce_only_calls = [c for c in created_orders if c.get("reduceOnly") is True and c.get("side") == "SELL"]
        self.assertEqual(len(reduce_only_calls), 1)

    def test_spot_buy_places_oco_and_cancels_on_close(self):
        """Spot : create_oco_order est appelé après le BUY, sl_order_id/tp_order_id sont stockés et annulés à la clôture."""
        import importlib
        import position_manager
        spec = importlib.machinery.PathFinder.find_spec("binance_manager")
        real_bm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(real_bm)

        oco_calls = []

        class MockSpotClient:
            def create_order(self, **kwargs):
                return {"orderId": 700, "clientOrderId": kwargs.get("newClientOrderId"), "status": "FILLED", "fills": [{"price": "100.0", "qty": "0.1"}]}

            def create_oco_order(self, **kwargs):
                oco_calls.append(kwargs)
                return {
                    "orderListId": 99,
                    "orderReports": [
                        {"orderId": 701, "type": "STOP_LOSS_LIMIT"},
                        {"orderId": 702, "type": "LIMIT_MAKER"},
                    ],
                }

        filters = {
            "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
            "PRICE_FILTER": {"tickSize": "0.10"},
            "MIN_NOTIONAL": {"notional": "5.0"},
        }
        with patch.object(real_bm, "_assert_order_context_allowed", return_value=None), \
             patch.object(real_bm, "_client_for_user", return_value=MockSpotClient()), \
             patch.object(real_bm, "get_symbol_filters", return_value=filters), \
             patch.object(real_bm, "get_price", return_value=100.0):
            res = real_bm.open_position(
                user_id=42,
                symbol="BTCUSDT",
                direction="BUY",
                quantity=0.1,
                sl_price=95.0,
                tp_price=110.0,
                market_type="spot",
            )

        self.assertEqual(len(oco_calls), 1)
        self.assertEqual(oco_calls[0]["side"], "SELL")
        self.assertEqual(res["sl_order_id"], "701")
        self.assertEqual(res["tp_order_id"], "702")

        # Vérification de l'annulation dans position_manager._cancel_remaining_protection
        cancelled = []
        trade = {
            "id": 1,
            "user_id": 42,
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "sl_order_id": res["sl_order_id"],
            "tp_order_id": res["tp_order_id"],
        }
        with patch.object(position_manager, "cancel_order", side_effect=lambda uid, sym, oid, mkt, **kw: cancelled.append(oid)):
            position_manager._cancel_remaining_protection(trade, "TP")
            self.assertIn("701", cancelled)
            cancelled.clear()
            position_manager._cancel_remaining_protection(trade, "MANUAL")
            self.assertEqual(cancelled, ["701", "702"])

    def test_close_requires_matching_remote_position(self):
        import position_manager

        row = (1, 42, "BTCUSDT", "BUY", 100.0, 95.0, 110.0, 0.5, 1, "futures", None, None)

        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *args, **kwargs): pass
            def fetchone(self): return row

        class Conn:
            def cursor(self): return Cursor()
            def commit(self): pass
            def close(self): pass

        with patch.object(position_manager, "get_connection", return_value=Conn()), \
             patch.object(position_manager, "get_open_binance_positions", return_value=[]), \
             patch.object(position_manager, "close_position") as close_position:
            res = position_manager.close_trade_manual(1, 42)

        close_position.assert_not_called()
        self.assertTrue(res.get("already_closed_on_binance"))

    def test_update_config_preserves_enabled_states(self):
        from trading_config import update_config, TradingConfig

        # Mock DB connection for update_config test
        class DummyCursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *args, **kwargs): pass
            def fetchone(self):
                # row matching TradingConfig fields
                return (42, True, 1, 1.0, 3, 70, 5.0, False, 1.0, False, 1, 1.0, "", "", "futures", "day", "1h", 5, False, 0, 0.0, True, False, None, None)

        class DummyConn:
            def cursor(self): return DummyCursor()
            def commit(self): pass
            def close(self): pass

        with patch("trading_config.get_connection", return_value=DummyConn()), \
             patch("trading_config.ensure_config_row", return_value=None):
            updated = update_config(42, analysis_interval_minutes=10)
            self.assertTrue(updated.auto_trade)
            self.assertTrue(updated.periodic_analysis_enabled)

    def test_manual_trade_execution_when_autotrade_disabled(self):
        import execution_engine
        from binance_manager import ORDER_CONTEXT_MANUAL_AUTHENTICATED

        signal = {
            "id": "manual-token123",
            "user_id": 42,
            "symbol": "BTCUSDT",
            "direction": "BUY",
            "entry_price": 100.0,
            "sl": 95.0,
            "tp": 110.0,
            "score": 90,
            "created_at": time.time(),
        }
        # AutoTrade is False (default for manual users)
        config = TradingConfig(user_id=42, auto_trade=False)

        called_context = []

        def mock_open_pos(*args, **kwargs):
            called_context.append(kwargs.get("execution_context"))
            return {
                "quantity": kwargs.get("quantity", 0.1),
                "order_id": "999",
                "client_order_id": kwargs.get("client_order_id"),
                "sl_order_id": "1000",
                "tp_order_id": "1001",
            }

        with patch.object(execution_engine, "calculate_position_size", return_value=0.1), \
             patch.object(execution_engine, "mark_signal_status", return_value=None), \
             patch.object(execution_engine, "insert_trade_row", return_value=13), \
             patch.object(execution_engine, "open_position", side_effect=mock_open_pos):
            result = execution_engine.execute_signal(signal, config)

        self.assertEqual(result["status"], "open")
        self.assertEqual(called_context[0], ORDER_CONTEXT_MANUAL_AUTHENTICATED)

    def test_periodic_analysis_signal_not_rejected_when_autotrade_disabled(self):
        import execution_engine
        from execution_engine import validate_signal_for_execution

        signal = {
            "id": "sig-btcusdt-84",
            "user_id": 42,
            "symbol": "BTCUSDT",
            "direction": "BUY",
            "entry_price": 65000.0,
            "sl": 64200.0,
            "tp": 67200.0,
            "score": 84,
            "status": "pending",
            "signal_type": "market_scan",
            "created_at": time.time(),
        }
        config = TradingConfig(
            user_id=42,
            auto_trade=False,
            periodic_analysis_enabled=True,
            min_score=78,
        )
        with patch.object(execution_engine, "check_can_open_position", return_value=_RiskResult(True)) as chk_mock:
            allowed, reason = validate_signal_for_execution(42, signal, config)
            self.assertTrue(allowed, f"Signal should be allowed in periodic analysis mode: {reason}")
            chk_mock.assert_called_once_with(42, config, "BTCUSDT", "BUY", require_auto_trade=False)

        # Un symbole non documenté (ex: PAXGUSDT, MOCAUSDT) doit toujours être rejeté
        undoc_signal = dict(signal, symbol="PAXGUSDT")
        allowed_undoc, reason_undoc = validate_signal_for_execution(42, undoc_signal, config)
        self.assertFalse(allowed_undoc)
        self.assertIn("non documenté", reason_undoc)

    def test_resolve_requested_scan_symbols_never_adds_unrequested_altcoins(self):
        from execution_engine import _resolve_requested_scan_symbols

        # 1. Avec Whitelist : uniquement les symboles documentés de la Whitelist
        cfg_wl = TradingConfig(user_id=42, symbol_whitelist=["BTCUSDT", "MOCAUSDT", "PAXGUSDT"])
        syms, src = _resolve_requested_scan_symbols(42, cfg_wl)
        self.assertEqual(syms, ["BTCUSDT"])
        self.assertEqual(src, "Whitelist (Symboles documentés)")

        # 1b. Un symbole hors univers (AVAXUSDT : paire de recherche Strategy Lab) reste filtré même s'il est demandé
        cfg_extra = TradingConfig(user_id=42, symbol_whitelist=["SOLUSDT", "AVAXUSDT"])
        syms_extra, _ = _resolve_requested_scan_symbols(42, cfg_extra)
        self.assertEqual(syms_extra, ["SOLUSDT"])

        # 2. Sans Whitelist ni Watchlist : exactement l'univers documenté (config.DOCUMENTED_SYMBOLS), rien d'autre
        from config import DOCUMENTED_SYMBOLS
        cfg_default = TradingConfig(user_id=42, symbol_whitelist=[])
        syms_def, _ = _resolve_requested_scan_symbols(42, cfg_default)
        self.assertEqual(syms_def, list(DOCUMENTED_SYMBOLS))
        self.assertNotIn("AVAXUSDT", syms_def)


if __name__ == "__main__":
    unittest.main()
