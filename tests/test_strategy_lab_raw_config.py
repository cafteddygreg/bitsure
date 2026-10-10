import unittest
import strategy_lab


class TestStrategyLabRawConfigAndModels(unittest.TestCase):
    def setUp(self):
        self.base_params = strategy_lab.normalize_lab_params(None, style="day")

    def test_valid_raw_config_parsing_and_pipeline_convergence(self):
        """1. Valid Raw Config produces the exact same normalized config as Visual Config."""
        raw_text = """
        # Signal & Confluence
        min_teddy_score=65
        adx_min=24.5
        # Indicators
        rsi_oversold=28.0
        rsi_overbought=72.0
        """
        res = strategy_lab.parse_and_validate_raw_config(
            raw_text=raw_text,
            reference_params=self.base_params,
            selected_models=["confluence", "indicators", "exits", "capital"],
            trading_style="day",
        )
        self.assertTrue(res["ok"], f"Expected valid config, got errors: {res['errors']}")
        self.assertEqual(res["changes_count"], 4)
        self.assertEqual(res["params"]["min_teddy_score"], 65)
        self.assertAlmostEqual(res["params"]["adx_min"], 24.5)
        self.assertAlmostEqual(res["params"]["rsi_oversold"], 28.0)
        self.assertAlmostEqual(res["params"]["rsi_overbought"], 72.0)

        # Compare with Visual Config validation
        visual_candidate = dict(self.base_params)
        visual_candidate["min_teddy_score"] = 65
        visual_candidate["adx_min"] = 24.5
        visual_candidate["rsi_oversold"] = 28.0
        visual_candidate["rsi_overbought"] = 72.0
        vis_res = strategy_lab.validate_partial_model_update(
            candidate_params=visual_candidate,
            reference_params=self.base_params,
            selected_models=["confluence", "indicators", "exits", "capital"],
            trading_style="day",
        )
        self.assertTrue(vis_res["ok"])
        self.assertEqual(res["params"], vis_res["params"])

    def test_unknown_parameter_strictly_rejected(self):
        """2. Any unknown parameter (e.g., FAKE_PARAMETER=123) is strictly rejected without creating a variable."""
        raw_text = """
        min_teddy_score=60
        FAKE_PARAMETER=123
        """
        res = strategy_lab.parse_and_validate_raw_config(
            raw_text=raw_text,
            reference_params=self.base_params,
            selected_models=["confluence", "indicators"],
            trading_style="day",
        )
        self.assertFalse(res["ok"])
        self.assertTrue(
            any("Unknown parameter: FAKE_PARAMETER" in err for err in res["errors"]),
            f"Expected Unknown parameter error, got: {res['errors']}",
        )
        self.assertNotIn("fake_parameter", res["params"])
        self.assertNotIn("FAKE_PARAMETER", res["params"])

    def test_invalid_parameter_type_and_out_of_bounds_rejected(self):
        """3. Invalid types or out-of-range values are rejected."""
        raw_bad_type = "min_teddy_score=not_an_int"
        res1 = strategy_lab.parse_and_validate_raw_config(
            raw_text=raw_bad_type,
            reference_params=self.base_params,
            selected_models=["confluence"],
        )
        self.assertFalse(res1["ok"])
        self.assertTrue(any("Invalid integer value" in e for e in res1["errors"]))

        raw_out_of_bounds = "min_teddy_score=999"
        res2 = strategy_lab.parse_and_validate_raw_config(
            raw_text=raw_out_of_bounds,
            reference_params=self.base_params,
            selected_models=["confluence"],
        )
        self.assertFalse(res2["ok"])
        self.assertTrue(any("out of range" in e for e in res2["errors"]))

    def test_single_model_selected_and_unselected_models_preserved(self):
        """4, 5, 6, 7. Selecting 1 or 2 models allows editing their params, preserves unselected models, and rejects edits to unselected models."""
        # Select only 'confluence' and 'indicators' (leave 'exits' and 'capital' unselected)
        selected = ["confluence", "indicators"]
        raw_valid_partial = """
        min_teddy_score=64
        rsi_oversold=29.0
        """
        res = strategy_lab.parse_and_validate_raw_config(
            raw_text=raw_valid_partial,
            reference_params=self.base_params,
            selected_models=selected,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["selected_models_count"], 2)
        self.assertEqual(res["params"]["min_teddy_score"], 64)
        self.assertEqual(res["params"]["rsi_oversold"], 29.0)
        # Verify 'exits' and 'capital' parameters are 100% preserved from reference_params
        self.assertEqual(res["params"]["sl_atr_mult"], self.base_params["sl_atr_mult"])
        self.assertEqual(res["params"]["tp_mode"], self.base_params["tp_mode"])
        self.assertEqual(res["params"]["initial_capital"], self.base_params["initial_capital"])
        self.assertEqual(res["params"]["risk_per_trade_pct"], self.base_params["risk_per_trade_pct"])

        # Now try to modify an unselected model parameter ('sl_atr_mult' belongs to 'exits')
        raw_forbidden_model = """
        min_teddy_score=64
        sl_atr_mult=3.2
        """
        res_forbidden = strategy_lab.parse_and_validate_raw_config(
            raw_text=raw_forbidden_model,
            reference_params=self.base_params,
            selected_models=selected,
        )
        self.assertFalse(res_forbidden["ok"])
        self.assertTrue(
            any("unselected model" in e for e in res_forbidden["errors"]),
            f"Expected unselected model error, got: {res_forbidden['errors']}",
        )

    def test_diff_generation_and_no_changes_detected(self):
        """8. Diff before backtest accurately reports changed parameters or zero changes."""
        raw_unchanged = strategy_lab.format_raw_config(
            self.base_params,
            selected_models=["confluence", "indicators"],
        )
        res_same = strategy_lab.parse_and_validate_raw_config(
            raw_text=raw_unchanged,
            reference_params=self.base_params,
            selected_models=["confluence", "indicators"],
        )
        self.assertTrue(res_same["ok"])
        self.assertEqual(res_same["changes_count"], 0)
        self.assertEqual(res_same["changes"], [])

    def test_ai_prompt_generator_local_and_self_contained(self):
        """9. AI Prompt Generator produces a self-contained prompt with real parameters and rules without external calls."""
        prompt_res = strategy_lab.generate_external_ai_prompt(
            params=self.base_params,
            selected_models=["confluence", "indicators"],
            symbol="BTCUSDT",
            market_type="futures",
            timeframe="15m",
            trading_style="day",
            start_date="2026-01-01",
            end_date="2026-09-30",
            max_candles=600,
            active_run={
                "start_date": "2026-01-01",
                "end_date": "2026-09-30",
                "candles_count": 600,
                "data_source": "Binance Historical Closed Candles",
                "metrics": {
                    "net_profit_usdt": 1240.5,
                    "total_return_pct": 12.41,
                    "buy_hold_return_pct": 5.2,
                    "alpha_vs_buy_hold_pct": 7.21,
                    "total_trades": 42,
                    "winning_trades": 25,
                    "losing_trades": 17,
                    "win_rate_pct": 59.52,
                    "profit_factor": 1.68,
                    "max_drawdown_pct": 4.35,
                    "max_drawdown_usdt": 435.0,
                    "expectancy_usdt": 29.54,
                    "avg_r_multiple": 0.62,
                    "avg_win_usdt": 122.0,
                    "avg_loss_usdt": -78.0,
                    "payoff_ratio": 1.56,
                    "best_trade_usdt": 340.0,
                    "worst_trade_usdt": -135.0,
                    "sharpe_ratio": 1.85,
                    "sortino_ratio": 2.41,
                    "calmar_ratio": 2.85,
                    "total_fees_usdt": 68.4,
                    "long_trades": 24,
                    "long_win_rate_pct": 62.5,
                    "long_pnl_usdt": 820.0,
                    "short_trades": 18,
                    "short_win_rate_pct": 55.5,
                    "short_pnl_usdt": 420.5,
                },
            },
        )
        self.assertTrue(prompt_res["ok"])
        prompt_text = prompt_res["prompt"]
        self.assertIn("Do not invent new parameters.", prompt_text)
        self.assertIn("Do not rename existing parameters.", prompt_text)
        self.assertIn("PROPOSED CHANGES", prompt_text)
        self.assertIn("REASONING", prompt_text)
        self.assertIn("min_teddy_score=58", prompt_text)
        self.assertIn("rsi_oversold=32.0", prompt_text)
        self.assertIn("Win Rate (%): 59.52%", prompt_text)

        # Verify that pasting an AI response formatted per the prompt works directly in Raw Config
        ai_response_paste = """
PROPOSED CHANGES
min_teddy_score=62
rsi_oversold=30.0

REASONING
min_teddy_score:
Raise entry confluence threshold slightly to filter out marginal signals.
rsi_oversold:
Tighten oversold threshold for deeper pullbacks.
"""
        parsed_ai = strategy_lab.parse_and_validate_raw_config(
            raw_text=ai_response_paste,
            reference_params=self.base_params,
            selected_models=["confluence", "indicators"],
        )
        self.assertTrue(parsed_ai["ok"], f"Failed to parse AI output format: {parsed_ai['errors']}")
        self.assertEqual(parsed_ai["changes_count"], 2)
        self.assertEqual(parsed_ai["params"]["min_teddy_score"], 62)
        self.assertEqual(parsed_ai["params"]["rsi_oversold"], 30.0)


if __name__ == "__main__":
    unittest.main()
