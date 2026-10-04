import sys
import types
import unittest
from unittest.mock import MagicMock

if "database" not in sys.modules:
    database_stub = types.ModuleType("database")
    database_stub.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("DB not available in unit test"))
    database_stub._get_pool = lambda: None
    sys.modules["database"] = database_stub
elif not hasattr(sys.modules["database"], "_get_pool"):
    sys.modules["database"]._get_pool = lambda: None

if "binance_manager" not in sys.modules:
    bm_stub = types.ModuleType("binance_manager")
    class _BinanceClientError(Exception): pass
    bm_stub.BinanceClientError = _BinanceClientError
    bm_stub.open_position = lambda *a, **k: {"quantity": a[3] if len(a) > 3 else k.get("quantity", 0), "order_id": "1", "client_order_id": k.get("client_order_id")}
    bm_stub.get_price = lambda *a, **k: 100.0
    bm_stub.get_tradable_symbols = lambda *a, **k: []
    bm_stub.make_client_order_id = lambda prefix, unique_key: f"{prefix}_{unique_key}"
    bm_stub.close_position = lambda *a, **k: {"order_id": "1"}
    bm_stub.cancel_order = lambda *a, **k: None
    bm_stub.get_open_binance_positions = lambda *a, **k: []
    bm_stub.get_open_binance_orders = lambda *a, **k: []
    bm_stub.get_klines_dataframe = lambda *a, **k: None
    bm_stub.replace_futures_stop_loss_order = lambda *a, **k: "sl_new"
    bm_stub.get_account_balance = lambda *a, **k: 1000.0
    bm_stub.get_available_balance = lambda *a, **k: 1000.0
    bm_stub.ORDER_CONTEXT_AUTOTRADE = "autotrade"
    bm_stub.ORDER_CONTEXT_MANUAL_AUTHENTICATED = "manual_authenticated"
    bm_stub.ORDER_CONTEXT_EMERGENCY = "emergency_stop"
    sys.modules["binance_manager"] = bm_stub

if "telegram" not in sys.modules:
    tg_stub = types.ModuleType("telegram")
    class _Btn:
        def __init__(self, *a, **k): pass
    class _Mkp:
        def __init__(self, *a, **k): pass
    tg_stub.InlineKeyboardButton = _Btn
    tg_stub.InlineKeyboardMarkup = _Mkp
    tg_ext_stub = types.ModuleType("telegram.ext")
    class _Ctx: DEFAULT_TYPE = object
    tg_ext_stub.ContextTypes = _Ctx
    sys.modules["telegram"] = tg_stub
    sys.modules["telegram.ext"] = tg_ext_stub

if "history_manager" not in sys.modules:
    hm_stub = types.ModuleType("history_manager")
    class _HM:
        @classmethod
        def get_instance(cls): return cls()
    hm_stub.HistoryManager = _HM
    sys.modules["history_manager"] = hm_stub

if "signal_engine" not in sys.modules:
    se_stub = types.ModuleType("signal_engine")
    class _SE: pass
    se_stub.SignalEngine = _SE
    sys.modules["signal_engine"] = se_stub

from health_monitor import run_health_check, check_db_health


def test_health_monitor_basic():
    # Database check
    db_ok = check_db_health()
    assert isinstance(db_ok, bool)

    # Watchdog run
    mock_app = MagicMock()
    report = run_health_check(context=mock_app)
    assert "timestamp" in report
    assert "db_ok" in report
    assert "scheduler_running" in report
    assert "repaired_jobs" in report
    assert "user_statuses" in report


class HealthMonitorUnitTests(unittest.TestCase):
    def test_health_monitor_basic_unittest(self):
        test_health_monitor_basic()


if __name__ == "__main__":
    unittest.main()
