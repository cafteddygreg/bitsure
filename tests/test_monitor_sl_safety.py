import asyncio
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

import sys
import types

try:  # python-binance peut être absent de l'environnement de test : stub minimal
    import binance.client  # noqa: F401
    import binance.exceptions  # noqa: F401
except ImportError:
    _b = types.ModuleType("binance")
    _bc = types.ModuleType("binance.client")
    _be = types.ModuleType("binance.exceptions")

    class _Client:
        def __init__(self, *a, **k):
            pass

    class _BinanceAPIException(Exception):
        code = None

    class _BinanceOrderException(Exception):
        pass

    _bc.Client = _Client
    _be.BinanceAPIException = _BinanceAPIException
    _be.BinanceOrderException = _BinanceOrderException
    _b.client, _b.exceptions = _bc, _be
    sys.modules.update({"binance": _b, "binance.client": _bc, "binance.exceptions": _be})

# D'autres fichiers de tests remplacent binance_manager / position_manager par des stubs dans sys.modules :
# on charge ici les VRAIS modules, puis on restaure les stubs pour ne pas perturber les autres tests.
_stubbed = {k: sys.modules.pop(k) for k in ("binance_manager", "position_manager") if k in sys.modules}
import binance_manager as bm
import position_manager as pm
sys.modules.update(_stubbed)


def _trade(**kw):
    t = {
        "id": 7, "user_id": 1, "symbol": "ETHUSDT", "direction": "SELL", "market_type": "futures",
        "entry_price": 2000.0, "sl_price": 2050.0, "tp_price": 1900.0, "quantity": 2.086, "leverage": 5,
        "sl_order_id": "111", "tp_order_id": "222",
    }
    t.update(kw)
    return t


class ClosePositionTests(unittest.TestCase):
    def _run_close(self, remote, context=bm.ORDER_CONTEXT_AUTOTRADE):
        client = MagicMock()
        client.futures_create_order.return_value = {"orderId": 99, "avgPrice": "2051"}
        with patch.object(bm, "_assert_order_context_allowed"), \
             patch.object(bm, "_client_for_user", return_value=client), \
             patch.object(bm, "get_open_binance_positions", return_value=remote), \
             patch.object(bm, "get_symbol_filters", return_value={"LOT_SIZE": {"stepSize": "0.001"}}):
            res = bm.close_position(1, "ETHUSDT", "SELL", 2.086, "futures", execution_context=context)
        return client, res

    def test_autotrade_uses_real_binance_quantity(self):
        remote = [{"symbol": "ETHUSDT", "direction": "SELL", "quantity": 2.0}]
        client, res = self._run_close(remote)
        kwargs = client.futures_create_order.call_args.kwargs
        self.assertAlmostEqual(float(kwargs["quantity"]), 2.0)
        self.assertTrue(kwargs["reduceOnly"])
        self.assertEqual(kwargs["side"], "BUY")

    def test_no_position_is_business_error_not_generic(self):
        with self.assertRaises(bm.BinancePositionNotFound) as ctx:
            self._run_close([])
        self.assertIsInstance(ctx.exception, bm.BinanceClientError)  # compat des appelants existants
        self.assertIn("Fermeture refusée", str(ctx.exception))


class MonitorTests(unittest.TestCase):
    def setUp(self):
        pm._breach_since.clear()
        pm._closing_trades.clear()

    def _monitor(self, trade, *, open_orders, remote_exists, close_side_effect=None, price=2060.0):
        m = {}
        with patch.object(pm, "flush_safety_notifications", new=AsyncMock()), \
             patch.object(pm, "get_open_trades", return_value=[trade]), \
             patch.object(pm, "get_config", return_value=MagicMock(safety_warn=False)), \
             patch.object(pm, "get_price", return_value=price), \
             patch.object(pm, "get_open_binance_orders", return_value=open_orders), \
             patch.object(pm, "_remote_position_exists", return_value=remote_exists), \
             patch.object(pm, "close_position", side_effect=close_side_effect, return_value={"executed_price": 2061.0}) as cp, \
             patch.object(pm, "_cancel_remaining_protection") as cancel, \
             patch.object(pm, "close_trade", return_value=(-10.0, -0.5)) as ct, \
             patch.object(pm, "engage_safety_warn") as warn, \
             patch.object(pm, "_resolve_real_exit_price", return_value=2058.0), \
             patch.object(pm, "update_trailing_stop", return_value=None), \
             patch.object(pm, "clear_safety_warn"):
            asyncio.run(pm.monitor_open_positions(None))
            m.update(close_position=cp, cancel=cancel, close_trade=ct, warn=warn)
        return m

    def test_stale_sl_order_triggers_safety_close(self):
        m = self._monitor(_trade(), open_orders=[{"orderId": 222}], remote_exists=True)
        m["close_position"].assert_called_once()
        self.assertEqual(m["close_position"].call_args.kwargs["execution_context"], bm.ORDER_CONTEXT_AUTOTRADE)
        self.assertEqual(m["close_trade"].call_args.args[1], "SL")
        self.assertEqual(m["close_trade"].call_args.args[2], 2061.0)
        m["cancel"].assert_called_once()
        self.assertEqual(m["cancel"].call_args.args[1], "SAFETY")

    def test_missing_sl_order_id_triggers_safety_close(self):
        m = self._monitor(_trade(sl_order_id=None), open_orders=[], remote_exists=True)
        m["close_position"].assert_called_once()
        m["close_trade"].assert_called_once()

    def test_live_sl_order_gets_grace_then_safety_close(self):
        orders = [{"orderId": 111}]
        m = self._monitor(_trade(), open_orders=orders, remote_exists=True)
        m["close_position"].assert_not_called()
        m["close_trade"].assert_not_called()
        pm._breach_since[7] = time.time() - pm.PROTECTIVE_ORDER_GRACE_SECONDS - 1
        m = self._monitor(_trade(), open_orders=orders, remote_exists=True)
        m["close_position"].assert_called_once()
        m["close_trade"].assert_called_once()

    def test_position_closed_by_exchange_order_syncs_without_market_close(self):
        m = self._monitor(_trade(), open_orders=[{"orderId": 111}], remote_exists=False)
        m["close_position"].assert_not_called()
        m["close_trade"].assert_called_once()

    def test_no_binance_position_syncs_local_state_without_network_warning(self):
        m = self._monitor(_trade(sl_order_id=None), open_orders=[], remote_exists=False,
                          close_side_effect=bm.BinancePositionNotFound("Fermeture refusée: aucune position"))
        m["close_trade"].assert_called_once()
        self.assertEqual(m["close_trade"].call_args.args[2], 2058.0)
        messages = [c.args[1] for c in m["warn"].call_args_list]
        self.assertFalse(any("Erreur réseau" in x or "Refus métier" in x for x in messages))

    def test_error_labels_are_separated(self):
        m = self._monitor(_trade(sl_order_id=None), open_orders=[], remote_exists=True,
                          close_side_effect=bm.BinanceClientError("Erreur Binance à la fermeture : timeout"))
        self.assertIn("Erreur réseau/API", m["warn"].call_args.args[1])
        m = self._monitor(_trade(sl_order_id=None), open_orders=[], remote_exists=True,
                          close_side_effect=bm.BinanceClientError("Fermeture refusée: autre refus"))
        self.assertIn("Refus métier", m["warn"].call_args.args[1])

    def test_no_double_close_when_already_closing(self):
        pm._closing_trades.add(7)
        m = self._monitor(_trade(sl_order_id=None), open_orders=[], remote_exists=True)
        m["close_position"].assert_not_called()
        m["close_trade"].assert_not_called()


class CloseTradeIdempotenceTests(unittest.TestCase):
    def test_second_close_does_not_record_loss_twice(self):
        cur = MagicMock()
        cur.rowcount = 0
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        with patch.object(pm, "get_connection", return_value=conn), \
             patch.object(pm, "record_trade_loss") as loss:
            pm.close_trade(_trade(), "SL", 2060.0)
        loss.assert_not_called()


if __name__ == "__main__":
    unittest.main()
