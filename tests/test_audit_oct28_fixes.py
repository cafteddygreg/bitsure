"""Non-régression : correctifs issus de l'audit du 27-28 oct. (alias legacy, OOS négatif)."""
import unittest

import strategy_lab as sl
from optimization import scoring


class LegacyAliasTests(unittest.TestCase):
    def test_canonicalize_converts_ema_to_sma_and_drops_removed(self):
        out = sl.canonicalize_legacy_params({"ema_fast": 12, "ema_trend": 200, "risk_per_trade_pct": 1.0})
        self.assertEqual(out, {"sma_fast": 12, "risk_per_trade_pct": 1.0})

    def test_explicit_current_name_wins_over_alias(self):
        self.assertEqual(sl.canonicalize_legacy_params({"ema_fast": 12, "sma_fast": 20})["sma_fast"], 20)

    def test_partial_update_accepts_legacy_key(self):
        res = sl.validate_partial_model_update({"ema_fast": 15}, {}, None, "day")
        self.assertTrue(res["ok"], res.get("errors"))
        self.assertEqual(res["params"]["sma_fast"], 15)
        self.assertNotIn("ema_fast", res["params"])

    def test_truly_unknown_key_still_rejected(self):
        res = sl.validate_partial_model_update({"totally_unknown": 1}, {}, None, "day")
        self.assertFalse(res["ok"])


class OosNegativeTests(unittest.TestCase):
    def test_negative_oos_is_high_risk_even_if_training_not_positive(self):
        train = {"total_return_pct": 0.0, "profit_factor": 1.0, "total_trades": 200}
        val = {"total_return_pct": 1.0}
        oos = {"total_return_pct": -4.0, "profit_factor": 0.7, "total_trades": 40}
        flags = scoring.overfit_flags(train, val, oos, {"stability": 0.9}, n_tested=10, min_trades=30)
        self.assertIn("oos_negative", flags["flags"])
        self.assertEqual(flags["risk"], "high")

    def test_collapse_still_reported_when_training_positive(self):
        train = {"total_return_pct": 10.0, "profit_factor": 1.5, "total_trades": 200}
        oos = {"total_return_pct": -2.0, "profit_factor": 0.8, "total_trades": 40}
        flags = scoring.overfit_flags(train, {"total_return_pct": 8.0}, oos, {"stability": 0.9}, n_tested=10, min_trades=30)
        self.assertIn("oos_collapse", flags["flags"])


if __name__ == "__main__":
    unittest.main()
