"""Tests : API Algo Binance (SL/TP), recalage des niveaux sur le fill, taille de position et validation Paper."""
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

database_stub = types.ModuleType("database")
database_stub.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("DB not available in unit test"))
sys.modules.setdefault("database", database_stub)


try:  # python-binance absent de l'environnement de test : stub minimal (jamais utilisé si la lib est installée)
    import binance.client  # noqa: F401
except ModuleNotFoundError:
    _b = types.ModuleType("binance")
    _bc = types.ModuleType("binance.client")
    _be = types.ModuleType("binance.exceptions")

    class _Client:
        def __init__(self, *a, **k):
            self.API_KEY = a[0] if a else ""
            self.API_SECRET = a[1] if len(a) > 1 else ""
            self.testnet = k.get("testnet", False)

    class _BinanceAPIException(Exception):
        def __init__(self, *a, **k):
            super().__init__(*a)
            self.code = k.get("code")
            self.message = str(a[0]) if a else ""

    class _BinanceOrderException(Exception):
        pass

    _bc.Client = _Client
    _be.BinanceAPIException = _BinanceAPIException
    _be.BinanceOrderException = _BinanceOrderException
    _b.client, _b.exceptions = _bc, _be
    sys.modules.update({"binance": _b, "binance.client": _bc, "binance.exceptions": _be})

import binance_manager as bm  # noqa: E402
import risk_manager as rm  # noqa: E402


class FakeClient:
    API_KEY = "k"
    API_SECRET = "s"
    testnet = True


def _resp(status=200, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.text = str(payload)
    return r


class AlgoOrderTests(unittest.TestCase):
    def test_conditional_order_uses_algo_endpoint_with_string_trigger(self):
        captured = {}

        def fake_request(method, url, headers=None, timeout=None):
            captured["method"], captured["url"] = method, url
            return _resp(200, {"algoId": 42, "clientAlgoId": "c1", "algoType": "CONDITIONAL",
                               "orderType": "STOP_MARKET", "symbol": "BTCUSDT", "side": "SELL",
                               "algoStatus": "NEW", "triggerPrice": "60000.0", "closePosition": True})

        with patch.object(bm.requests, "request", side_effect=fake_request):
            out = bm.futures_place_conditional_order(FakeClient(), "BTCUSDT", "SELL", "STOP_MARKET", "60000.0")
        self.assertEqual(captured["method"], "POST")
        self.assertIn("testnet.binancefuture.com/fapi/v1/algoOrder", captured["url"])
        self.assertIn("algoType=CONDITIONAL", captured["url"])
        self.assertIn("triggerPrice=60000.0", captured["url"])
        self.assertIn("closePosition=true", captured["url"])
        self.assertNotIn("stopPrice", captured["url"])
        self.assertEqual(out["orderId"], 42)
        self.assertTrue(out["algo"])

    def test_error_code_is_exposed(self):
        with patch.object(bm.requests, "request", return_value=_resp(400, {"code": -2021, "msg": "Order would immediately trigger."})):
            with self.assertRaises(bm.BinanceAlgoError) as ctx:
                bm.futures_place_conditional_order(FakeClient(), "BTCUSDT", "SELL", "STOP_MARKET", "1")
        self.assertEqual(ctx.exception.code, -2021)

    def test_transient_errors_are_retried(self):
        calls = {"n": 0}

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                return _resp(503, {"code": -1001, "msg": "busy"})
            return _resp(200, {"algoId": 7, "algoStatus": "NEW", "orderType": "STOP_MARKET", "triggerPrice": "1"})

        with patch.object(bm.requests, "request", side_effect=flaky), patch.object(bm.time, "sleep"):
            out = bm.futures_place_conditional_order(FakeClient(), "BTCUSDT", "SELL", "STOP_MARKET", "1")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(out["orderId"], 7)

    def test_protective_orders_place_sl_and_tp_via_algo_with_tick_formatting(self):
        placed = []

        def fake_place(client, symbol, side, otype, trigger, **kw):
            placed.append((otype, trigger))
            return {"orderId": len(placed), "algo": True}

        filters = {"PRICE_FILTER": {"tickSize": "0.10"}}
        with patch.object(bm, "futures_place_conditional_order", side_effect=fake_place), \
             patch.object(bm, "_cancel_conflicting_futures_protective_orders", return_value=[]):
            sl, tp = bm._place_futures_protective_orders(FakeClient(), "BTCUSDT", "SELL", 59999.97, 62000.04, filters)
        self.assertEqual((sl, tp), ("1", "2"))
        self.assertEqual(placed[0], ("STOP_MARKET", "59999.9"))      # floor au tick, jamais de float/notation scientifique
        self.assertEqual(placed[1], ("TAKE_PROFIT_MARKET", "62000"))

    def test_tp_immediate_trigger_is_nudged_then_downgraded_to_warning(self):
        attempts = []

        def fake_place(client, symbol, side, otype, trigger, **kw):
            if otype == "TAKE_PROFIT_MARKET":
                attempts.append(trigger)
                raise bm.BinanceAlgoError("Code -2021: Order would immediately trigger.", code=-2021)
            return {"orderId": 1, "algo": True}

        warnings = []
        filters = {"PRICE_FILTER": {"tickSize": "0.10"}}
        with patch.object(bm, "futures_place_conditional_order", side_effect=fake_place), \
             patch.object(bm, "get_mark_price", return_value=61000.0), \
             patch.object(bm, "_cancel_conflicting_futures_protective_orders", return_value=[]):
            sl, tp = bm._place_futures_protective_orders(FakeClient(), "BTCUSDT", "SELL", 59000.0, 60500.0, filters, warnings=warnings)
        self.assertEqual(sl, "1")
        self.assertIsNone(tp)
        self.assertEqual(len(attempts), 2)                 # 1 essai + 1 essai décalé
        self.assertGreater(float(attempts[1]), 61000.0)    # TP long décalé au-dessus du mark
        self.assertEqual(len(warnings), 1)

    def test_sl_immediate_trigger_propagates_so_caller_closes_position(self):
        def fake_place(client, symbol, side, otype, trigger, **kw):
            raise bm.BinanceAlgoError("Code -2021", code=-2021)

        with patch.object(bm, "futures_place_conditional_order", side_effect=fake_place), \
             patch.object(bm, "_cancel_conflicting_futures_protective_orders", return_value=[]):
            with self.assertRaises(bm.BinanceAlgoError):
                bm._place_futures_protective_orders(FakeClient(), "BTCUSDT", "SELL", 59000.0, None, {"PRICE_FILTER": {"tickSize": "0.1"}})

    def test_find_protective_orders_includes_algo_orders(self):
        client = MagicMock()
        client.futures_get_open_orders.return_value = []
        algo = [{"orderId": 9, "symbol": "BTCUSDT", "side": "SELL", "type": "STOP_MARKET", "stopPrice": "59000", "closePosition": True, "algo": True}]
        with patch.object(bm, "futures_list_conditional_orders", return_value=algo):
            found = bm._find_futures_protective_orders(client, "BTCUSDT", side="SELL", order_types={"STOP_MARKET"})
        self.assertEqual([o["orderId"] for o in found], [9])


class RebaseTests(unittest.TestCase):
    def test_long_slippage_shifts_levels_keeping_distances(self):
        sl, tp = bm.rebase_protective_levels("BUY", 100.0, 100.5, 98.0, 106.0)
        self.assertAlmostEqual(sl, 98.5)
        self.assertAlmostEqual(tp, 106.5)

    def test_short_slippage(self):
        sl, tp = bm.rebase_protective_levels("SELL", 100.0, 99.5, 102.0, 94.0)
        self.assertAlmostEqual(sl, 101.5)
        self.assertAlmostEqual(tp, 93.5)

    def test_no_planned_entry_leaves_levels_untouched(self):
        self.assertEqual(bm.rebase_protective_levels("BUY", None, 100.0, 98.0, 106.0), (98.0, 106.0))

    def test_absurd_gap_is_not_treated_as_slippage(self):
        # signal périmé (+100%) : on ne déplace pas SL/TP, niveaux d'origine conservés
        self.assertEqual(bm.rebase_protective_levels("BUY", 100.0, 200.0, 99.0, 110.0), (99.0, 110.0))

    def test_order_of_levels_preserved(self):
        sl, tp = bm.rebase_protective_levels("BUY", 100.0, 101.0, 99.0, 103.0)
        self.assertLess(sl, 101.0)
        self.assertGreater(tp, 101.0)


class SizingTests(unittest.TestCase):
    def test_pure_sizing_matches_risk_formula(self):
        r = rm.compute_risk_based_quantity(balance=10000, risk_pct=1.0, entry_price=100.0, sl_price=98.0,
                                           leverage=10, market_type="futures", direction="BUY")
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["quantity"], 50.0)          # 100 USDT de risque / 2 USDT de distance
        self.assertAlmostEqual(r["risk_amount"], 100.0)

    def test_cap_is_shared_with_execution_rule(self):
        # risque énorme -> plafonné à 50% du solde x levier (même plafond que calculate_position_size)
        r = rm.compute_risk_based_quantity(balance=1000, risk_pct=50.0, entry_price=100.0, sl_price=99.9,
                                           leverage=2, market_type="futures", direction="BUY")
        self.assertTrue(r["capped"])
        self.assertAlmostEqual(r["notional"], 1000 * 0.5 * 2)

    def test_wrong_side_sl_is_refused(self):
        r = rm.compute_risk_based_quantity(balance=1000, risk_pct=1.0, entry_price=100.0, sl_price=102.0,
                                           leverage=1, market_type="futures", direction="BUY")
        self.assertFalse(r["ok"])
        self.assertIn("SL", r["reason"])

    def test_step_size_rounds_down(self):
        r = rm.compute_risk_based_quantity(balance=10000, risk_pct=1.0, entry_price=100.0, sl_price=97.0,
                                           leverage=5, market_type="futures", direction="BUY", step_size=0.1)
        self.assertAlmostEqual(r["quantity"], 33.3)          # 33.333... arrondi au pas
        self.assertLessEqual(r["quantity"] * 3.0, r["risk_amount"] + 1e-9)

    def test_min_notional_reported(self):
        r = rm.compute_risk_based_quantity(balance=50, risk_pct=1.0, entry_price=100.0, sl_price=99.0,
                                           leverage=1, market_type="futures", direction="BUY", min_notional=100.0)
        self.assertFalse(r["ok"])

    def test_calculate_position_size_refuses_wrong_side_when_direction_given(self):
        from trading_config import TradingConfig
        cfg = TradingConfig(user_id=1, market_type="futures", leverage=5, risk_per_trade=1.0)
        with patch.object(rm, "get_account_balance", return_value=1000.0), \
             patch.object(rm, "get_available_balance", return_value=1000.0):
            with self.assertRaises(ValueError):
                rm.calculate_position_size(1, cfg, 100.0, 102.0, "futures", direction="BUY")
            # SELL avec SL au-dessus : valide
            q = rm.calculate_position_size(1, cfg, 100.0, 102.0, "futures", direction="SELL")
            self.assertGreater(q, 0)

    def test_pure_matches_calculate_position_size(self):
        from trading_config import TradingConfig
        cfg = TradingConfig(user_id=1, market_type="futures", leverage=50, risk_per_trade=1.0)
        with patch.object(rm, "get_account_balance", return_value=4525.82), \
             patch.object(rm, "get_available_balance", return_value=4525.82):
            q = rm.calculate_position_size(1, cfg, 3000.0, 2998.0, "futures", direction="BUY")
        r = rm.compute_risk_based_quantity(balance=4525.82, risk_pct=1.0, entry_price=3000.0, sl_price=2998.0,
                                           leverage=50, market_type="futures", direction="BUY")
        self.assertAlmostEqual(q, r["quantity"], places=6)


class PaperValidationTests(unittest.TestCase):
    def test_paper_refuses_inconsistent_sl_tp(self):
        from paper_trader import PaperTrader
        pt = PaperTrader.__new__(PaperTrader)
        for attr, val in (("capitals", {}), ("positions", {}), ("closed_positions", {})):
            setattr(pt, attr, val)
        pt._uid = lambda u: str(u)
        pt.init_capital = lambda u: pt.capitals.__setitem__(str(u), 10000.0)
        pos, err = pt.open_position(1, "BTCUSDT", 100.0, 105.0, 120.0, 1.0, side="BUY", leverage=1.0)
        self.assertIsNone(pos)
        self.assertIn("Stop Loss", err)
        pos, err = pt.open_position(1, "BTCUSDT", 100.0, 105.0, 90.0, 1.0, side="BUY", leverage=1.0)
        self.assertIn("Stop Loss", err)
        pos, err = pt.open_position(1, "BTCUSDT", 100.0, 98.0, 95.0, 1.0, side="BUY", leverage=1.0)
        self.assertIn("Take Profit", err)


class LiveRoundTickTests(unittest.TestCase):
    def test_round_tick_has_no_float_drift_or_scientific_notation(self):
        import live_trader as lt
        self.assertEqual(lt._round_tick(0.3, 0.1), 0.3)               # l'ancien floor donnait 0.2
        self.assertEqual(lt._round_tick(12345.67, 0.1), 12345.7)
        self.assertEqual(lt._round_tick(0.00001234, 0.00000001), 0.00001234)


if __name__ == "__main__":
    unittest.main()
