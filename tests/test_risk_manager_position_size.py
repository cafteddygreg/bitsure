import os
import sys
import types
import unittest
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

database_stub = types.ModuleType("database")
database_stub.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("DB not available in unit test"))
sys.modules.setdefault("database", database_stub)

binance_manager_stub = types.ModuleType("binance_manager")
class _BinanceClientError(Exception):
    pass
binance_manager_stub.BinanceClientError = _BinanceClientError
binance_manager_stub.open_position = lambda *a, **k: {"quantity": a[3] if len(a) > 3 else k.get("quantity", 0), "order_id": "1", "client_order_id": k.get("client_order_id")}
binance_manager_stub.get_price = lambda *a, **k: 100.0
binance_manager_stub.get_tradable_symbols = lambda *a, **k: []
binance_manager_stub.get_klines_dataframe = lambda *a, **k: None
binance_manager_stub.make_client_order_id = lambda prefix, unique_key: f"{prefix}_{unique_key}"
binance_manager_stub.close_position = lambda *a, **k: {"order_id": "close"}
binance_manager_stub.cancel_order = lambda *a, **k: None
binance_manager_stub.get_account_balance = lambda *a, **k: 0
binance_manager_stub.get_available_balance = lambda *a, **k: 0
binance_manager_stub.get_open_binance_positions = lambda *a, **k: []
binance_manager_stub.get_open_binance_orders = lambda *a, **k: []
binance_manager_stub.ORDER_CONTEXT_AUTOTRADE = "autotrade"
binance_manager_stub.ORDER_CONTEXT_MANUAL_AUTHENTICATED = "manual_authenticated"
binance_manager_stub.ORDER_CONTEXT_EMERGENCY = "emergency_stop"
sys.modules.setdefault("binance_manager", binance_manager_stub)

from trading_config import TradingConfig
import risk_manager


class PositionSizeExposureTests(unittest.TestCase):
    def test_futures_exposure_cap_is_leverage_adjusted_notional(self):
        config = TradingConfig(user_id=1, market_type="futures", leverage=50, risk_per_trade=1.0)
        with patch.object(risk_manager, "get_account_balance", return_value=4525.82), \
             patch.object(risk_manager, "get_available_balance", return_value=4525.82):
            quantity = risk_manager.calculate_position_size(
                user_id=1,
                config=config,
                entry_price=3000.0,
                sl_price=2998.0,
                market_type="futures",
            )
        self.assertAlmostEqual(quantity, 22.6291, places=4)

    def test_spot_exposure_cap_remains_unleveraged(self):
        config = TradingConfig(user_id=1, market_type="spot", leverage=50, risk_per_trade=1.0)
        with patch.object(risk_manager, "get_account_balance", return_value=4525.82), \
             patch.object(risk_manager, "get_available_balance", return_value=4525.82):
            quantity = risk_manager.calculate_position_size(
                user_id=1,
                config=config,
                entry_price=3000.0,
                sl_price=2998.0,
                market_type="spot",
            )
            # max_notional = 4525.82 * 0.50 = 2262.91
            # quantity = 2262.91 / 3000 = 0.75430333...
            expected_quantity = (4525.82 * 0.50) / 3000.0
            self.assertAlmostEqual(quantity, expected_quantity, places=4)

    def test_check_can_open_position_refuses_when_balance_unavailable_or_zero(self):
        """solde indisponible ou <= 0 -> refus (fail-closed)."""
        import importlib
        rm = importlib.reload(risk_manager)
        config = TradingConfig(
            user_id=101,
            auto_trade=True,
            market_type="futures",
            max_positions=3,
            max_daily_loss=5.0,
        )
        with patch.object(rm, "count_duplicate_open_positions", return_value=0), \
             patch.object(rm, "count_local_open_positions", return_value=0), \
             patch.object(rm, "count_remote_open_positions", return_value=0), \
             patch.object(rm, "get_account_balance", side_effect=RuntimeError("API down")):
            res_err = rm.check_can_open_position(101, config, "BTCUSDT", "BUY")
            self.assertFalse(res_err.allowed)
            self.assertIn("Solde", res_err.reason)

        with patch.object(rm, "count_duplicate_open_positions", return_value=0), \
             patch.object(rm, "count_local_open_positions", return_value=0), \
             patch.object(rm, "count_remote_open_positions", return_value=0), \
             patch.object(rm, "get_account_balance", return_value=0.0):
            res_zero = rm.check_can_open_position(101, config, "BTCUSDT", "BUY")
            self.assertFalse(res_zero.allowed)
            self.assertIn("Solde", res_zero.reason)

    def test_record_daily_pnl_utc_midnight_reset_and_gain_offsets_loss(self):
        """reset à minuit UTC ; gain compense perte ; blocage si daily_pnl <= -(max_daily_loss% * solde)."""
        import importlib
        import trading_config as tc
        rm = importlib.reload(risk_manager)

        state = {"daily_pnl": 0.0, "daily_pnl_day": ""}

        class _Cur:
            def execute(self, sql, params=None):
                q = " ".join(sql.strip().split()).upper()
                if q.startswith("SELECT DAILY_PNL, DAILY_PNL_DAY"):
                    self._row = (state["daily_pnl"], state["daily_pnl_day"])
                elif q.startswith("UPDATE TRADING_CONFIG SET DAILY_PNL ="):
                    state["daily_pnl"] = float(params[0])
                    state["daily_pnl_day"] = str(params[1])
                    self._row = None
                else:
                    self._row = None

            def fetchone(self):
                return self._row

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        class _Conn:
            def cursor(self):
                return _Cur()

            def commit(self):
                pass

            def close(self):
                pass

        # Jour 1 UTC : 2026-10-10 23:50:00 UTC (1791676200)
        day1_ts = 1791676200.0
        # Jour 2 UTC : 2026-10-11 00:05:00 UTC (1791677100)
        day2_ts = 1791677100.0

        with patch.object(tc, "get_connection", side_effect=lambda: _Conn()), \
             patch.object(tc, "ensure_config_row", return_value=None):
            with patch.object(tc.time, "time", return_value=day1_ts):
                # Perte de -60 USDT sur un solde de 1000 USDT (max_daily_loss=5% -> seuil -50 USDT)
                net1 = tc.record_daily_pnl(202, -60.0)
                self.assertAlmostEqual(net1, -60.0)
                day1_str = state["daily_pnl_day"]

                cfg_blocked = TradingConfig(
                    user_id=202,
                    auto_trade=True,
                    market_type="futures",
                    max_positions=3,
                    max_daily_loss=5.0,
                    daily_pnl=state["daily_pnl"],
                    daily_pnl_day=day1_str,
                )
                with patch.object(rm.time, "time", return_value=day1_ts), \
                     patch.object(rm, "count_duplicate_open_positions", return_value=0), \
                     patch.object(rm, "count_local_open_positions", return_value=0), \
                     patch.object(rm, "count_remote_open_positions", return_value=0), \
                     patch.object(rm, "get_account_balance", return_value=1000.0):
                    chk1 = rm.check_can_open_position(202, cfg_blocked, "BTCUSDT", "BUY")
                    self.assertFalse(chk1.allowed)

                # Un gain de +25 USDT ramène le PnL net à -35 USDT (> -50 USDT) -> autorisé !
                net2 = tc.record_daily_pnl(202, +25.0)
                self.assertAlmostEqual(net2, -35.0)
                cfg_recovered = TradingConfig(
                    user_id=202,
                    auto_trade=True,
                    market_type="futures",
                    max_positions=3,
                    max_daily_loss=5.0,
                    daily_pnl=state["daily_pnl"],
                    daily_pnl_day=state["daily_pnl_day"],
                )
                with patch.object(rm.time, "time", return_value=day1_ts), \
                     patch.object(rm, "count_duplicate_open_positions", return_value=0), \
                     patch.object(rm, "count_local_open_positions", return_value=0), \
                     patch.object(rm, "count_remote_open_positions", return_value=0), \
                     patch.object(rm, "get_account_balance", return_value=1000.0):
                    chk2 = rm.check_can_open_position(202, cfg_recovered, "BTCUSDT", "BUY")
                    self.assertTrue(chk2.allowed)

                # Nouvelle perte de -30 USDT -> net = -65 USDT (bloqué le jour 1)
                tc.record_daily_pnl(202, -30.0)
                self.assertAlmostEqual(state["daily_pnl"], -65.0)

            # Passage à minuit UTC (Jour 2) -> reset automatique à 0 puis applique le nouveau trade
            with patch.object(tc.time, "time", return_value=day2_ts):
                net_day2 = tc.record_daily_pnl(202, -10.0)
                self.assertAlmostEqual(net_day2, -10.0)
                self.assertNotEqual(state["daily_pnl_day"], day1_str)

    def test_reconcile_missing_remote_fetches_exchange_sl_fill_and_records_daily_pnl(self):
        """clôture par SL exchange -> prix de fill récupéré et PnL enregistré via record_daily_pnl."""
        import position_manager as pm
        from unittest.mock import MagicMock

        local_trade = {
            "id": 77,
            "user_id": 303,
            "symbol": "BTCUSDT",
            "direction": "BUY",
            "entry_price": 50000.0,
            "sl_price": 49000.0,
            "tp_price": 52000.0,
            "quantity": 0.1,
            "leverage": 5,
            "market_type": "futures",
            "sl_order_id": "SL_ORD_999",
            "tp_order_id": "TP_ORD_999",
        }
        fake_client = MagicMock()
        # Le SL a été exécuté à 48950.0 (slippage réel sur l'exchange) alors que le prix spot courant est 49500.0
        fake_client.futures_get_order.return_value = {
            "orderId": "SL_ORD_999",
            "status": "FILLED",
            "avgPrice": "48950.0",
        }
        recorded_pnls = []
        closed_updates = []

        class _Cur:
            def execute(self, sql, params=None):
                if "UPDATE trades" in sql:
                    closed_updates.append(params)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        class _Conn:
            def cursor(self):
                return _Cur()

            def commit(self):
                pass

            def close(self):
                pass

        import binance_manager as bm_mod
        with patch.object(pm, "get_open_trades", return_value=[local_trade]), \
             patch.object(pm, "get_open_binance_positions", return_value=[]), \
             patch.object(pm, "get_open_binance_orders", return_value=[]), \
             patch.object(pm, "get_price", return_value=49500.0), \
             patch.object(pm, "cancel_order", return_value=None), \
             patch.object(pm, "get_connection", side_effect=lambda: _Conn()), \
             patch.object(pm, "get_config", return_value=TradingConfig(user_id=303)), \
             patch.object(pm, "record_trade_loss", side_effect=lambda uid, loss: recorded_pnls.append((uid, -abs(loss))) or loss), \
             patch.object(bm_mod, "_client_for_user", return_value=fake_client, create=True), \
             patch.object(bm_mod, "_extract_order_fill_price", side_effect=lambda o: float(o.get("avgPrice")), create=True):
            summary = pm.reconcile_user_positions(303)

        self.assertEqual(summary["repaired"], 1)
        self.assertEqual(len(recorded_pnls), 1)
        uid_rec, pnl_rec = recorded_pnls[0]
        self.assertEqual(uid_rec, 303)
        # (48950 - 50000) * 0.1 = -105.0 USDT (et non (49500 - 50000) * 0.1 = -50.0 USDT)
        self.assertAlmostEqual(pnl_rec, -105.0, places=4)


if __name__ == "__main__":
    unittest.main()
