import math
import random
import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

import strategy_lab


def build_synthetic_ohlcv(
    n_candles: int = 1200,
    seed: int = 42,
    timeframe_minutes: int = 15,
    base_price: float = 50000.0,
    drift: float = 0.0005,
    volatility: float = 0.004,
) -> pd.DataFrame:
    """Builds a 100% deterministic synthetic closed-candle OHLCV DataFrame in UTC."""
    rng = random.Random(seed)
    start_dt = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = []
    price = base_price
    for i in range(n_candles):
        ts = start_dt + timedelta(minutes=i * timeframe_minutes)
        ret = drift + rng.gauss(0.0, volatility)
        open_p = price
        close_p = max(10.0, open_p * (1.0 + ret))
        wick_up = abs(rng.gauss(0.0, volatility * 0.6))
        wick_dn = abs(rng.gauss(0.0, volatility * 0.6))
        high_p = max(open_p, close_p) * (1.0 + wick_up)
        low_p = min(open_p, close_p) * max(0.01, (1.0 - wick_dn))
        vol = float(100.0 + abs(rng.gauss(50.0, 25.0)))
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "Open": round(open_p, 4),
                "High": round(high_p, 4),
                "Low": round(low_p, 4),
                "Close": round(close_p, 4),
                "Volume": round(vol, 2),
            }
        )
        price = close_p
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.set_index("timestamp", inplace=True)
    return df


class TestD1IndicatorWarmup(unittest.TestCase):
    def test_d1_ema_trend_warmup_convergence_and_split_continuity(self):
        """
        D1: The EMA(ema_trend=200) at the first simulated candle must differ by < 0.1%
        from a reference EMA computed on a long history, both on 'full' and 'test' splits.
        Also verifies explicit warning when history is shorter than 3 * ema_trend.
        """
        df_long = build_synthetic_ohlcv(n_candles=1200, seed=101, drift=0.0005, volatility=0.004)
        params = strategy_lab.normalize_lab_params({"ema_trend": 200}, style="day")

        # Reference EMA200 computed over the full 1200-candle history
        ref_ind = strategy_lab._compute_lab_indicators(df_long, params)
        ref_ts_to_ema = {
            (ts.isoformat() if hasattr(ts, "isoformat") else str(ts)): float(val)
            for ts, val in zip(ref_ind.index, ref_ind["LAB_EMA_TREND"])
        }

        # 1. Sub-history starting at bar 200 (1000 bars total):
        # At the first simulated candle of res_sub, the EMA200 must have warmed up over >= 600 bars
        # so its value differs by < 0.1% from the reference EMA200 that started 200 bars earlier.
        df_sub = df_long.iloc[200:].copy()
        res_sub = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            period_split="full",
            raw_params=params,
            preloaded_df=(df_sub, "SyntheticSub"),
        )
        first_c_sub = res_sub["candles"][0]
        ts_sub = first_c_sub["timestamp"]
        ref_ema_true = ref_ts_to_ema[ts_sub]
        sim_ema_sub = float(first_c_sub["ema_trend"])
        rel_diff_pct = abs(sim_ema_sub - ref_ema_true) / ref_ema_true * 100.0
        self.assertLess(
            rel_diff_pct,
            0.1,
            f"EMA200 at first simulated candle differs by {rel_diff_pct:.4f}% (>= 0.1%) from long-history reference",
        )

        # 2. On 'test' split (last 20%), indicators must be computed on the full history BEFORE slicing
        res_test_split = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            period_split="test",
            raw_params=params,
            preloaded_df=(df_long, "SyntheticDeterministic"),
        )
        first_c_test = res_test_split["candles"][0]
        ts_test = first_c_test["timestamp"]
        ref_ema_test = ref_ts_to_ema[ts_test]
        sim_ema_test = float(first_c_test["ema_trend"])
        rel_diff_test_pct = abs(sim_ema_test - ref_ema_test) / ref_ema_test * 100.0
        self.assertLess(
            rel_diff_test_pct,
            0.01,
            f"Test split EMA200 was recomputed on isolated slice! Diff={rel_diff_test_pct:.4f}%",
        )

    def test_d1_insufficient_warmup_warning_reported(self):
        """
        D1: If the loaded history is shorter than the required warm-up (3 * ema_trend),
        an explicit warning must be added to data_quality['warnings'] and result['warnings']
        without fabricating data.
        """
        df_short = build_synthetic_ohlcv(n_candles=250, seed=102)
        params = strategy_lab.normalize_lab_params({"ema_trend": 200}, style="day")
        res = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            period_split="full",
            raw_params=params,
            preloaded_df=(df_short, "SyntheticShort"),
        )
        dq_warnings = res.get("data_quality", {}).get("warnings", [])
        res_warnings = res.get("warnings", [])
        self.assertTrue(
            any("warm-up" in w.lower() or "warmup" in w.lower() or "ema" in w.lower() for w in dq_warnings),
            f"Expected warm-up warning in data_quality['warnings'], got: {dq_warnings}",
        )
        self.assertTrue(
            any("warm-up" in w.lower() or "warmup" in w.lower() or "ema" in w.lower() for w in res_warnings),
            f"Expected warm-up warning in result['warnings'], got: {res_warnings}",
        )


class TestD2CircuitBreakerMaxConsecutiveLosses(unittest.TestCase):
    def test_d2_circuit_breaker_blocks_all_remaining_signals_until_next_utc_day(self):
        """
        D2: After N consecutive losses (e.g. max_consecutive_losses=2), NO trade may be opened
        for the remainder of the UTC day even if multiple valid entry signals occur on subsequent candles.
        Trading may only resume on the next UTC day.
        """
        # Construct deterministic series where every BUY entry immediately hits its tight stop-loss on the next candle
        start_dt = datetime(2025, 3, 10, 0, 0, tzinfo=timezone.utc)
        rows = []
        price = 50000.0
        for i in range(700):
            ts = start_dt + timedelta(minutes=i * 15)
            # Gentle uptrend for warmup and bullish alignment, with deep low wicks during day 2025-03-16
            open_p = price
            close_p = price * 1.0008
            high_p = close_p * 1.001
            # Deep downward spike on every candle after warmup (i >= 600) so any open LONG hits SL immediately
            low_p = open_p * (0.975 if i >= 600 else 0.999)
            rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "Open": round(open_p, 4),
                    "High": round(high_p, 4),
                    "Low": round(low_p, 4),
                    "Close": round(close_p, 4),
                    "Volume": 250.0,
                }
            )
            price = close_p

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.set_index("timestamp", inplace=True)

        params = strategy_lab.normalize_lab_params(
            {
                "ema_trend": 200,
                "min_teddy_score": 25,
                "adx_min": 5.0,
                "min_atr_pct": 0.0,
                "min_volume_ratio": 0.0,
                "require_ema_alignment": False,
                "require_macd_confirmation": False,
                "allow_long": True,
                "allow_short": False,
                "cooldown_candles": 0,
                "max_trades_per_day": 50,
                "max_consecutive_losses": 2,
                "sl_mode": "fixed_pct",
                "sl_fixed_pct": 0.5,
                "tp_mode": "fixed_pct",
                "tp_fixed_pct": 5.0,
                "min_rr_ratio": 1.5,
            },
            style="day",
        )

        res = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            period_split="full",
            raw_params=params,
            preloaded_df=(df, "SyntheticCircuitBreaker"),
        )
        trades = res["trades"]
        self.assertGreaterEqual(len(trades), 2, "Expected at least 2 losing trades to trigger circuit breaker")

        # Group trades by UTC day of entry_time
        trades_by_day = {}
        for t in trades:
            day = t["entry_time"][:10]
            trades_by_day.setdefault(day, []).append(t)

        # Since every trade loses on the very next bar and max_consecutive_losses=2,
        # no single UTC day can have more than 2 losing trades opened!
        for day, day_trades in trades_by_day.items():
            self.assertLessEqual(
                len(day_trades),
                2,
                f"Circuit breaker max_consecutive_losses=2 failed on {day}: {len(day_trades)} trades were opened!",
            )


class TestD3RiskTargetActualAndLeverageCap(unittest.TestCase):
    def test_d3_leverage_cap_hit_and_actual_risk_exposed(self):
        """
        D3: In low-volatility / tight-SL conditions where notional exceeds balance * leverage * 0.95,
        the trade must expose leverage_cap_hit=True and risk_actual_usdt < risk_target_usdt,
        and metrics must expose leverage_capped_trades_pct and median_actual_risk_usdt.
        """
        df = build_synthetic_ohlcv(n_candles=750, seed=303, drift=0.0003, volatility=0.0008)
        params = strategy_lab.normalize_lab_params(
            {
                "position_sizing_mode": "risk_pct",
                "risk_per_trade_pct": 2.0,   # target ~200 USDT risk on 10,000 USDT
                "leverage": 1.0,             # max notional = 9,500 USDT
                "sl_mode": "fixed_pct",
                "sl_fixed_pct": 0.25,        # 0.25% SL on 9,500 USDT -> actual risk ~23.75 USDT < 200 USDT
                "min_teddy_score": 25,
                "adx_min": 5.0,
                "min_atr_pct": 0.0,
                "min_volume_ratio": 0.0,
                "require_ema_alignment": False,
                "require_macd_confirmation": False,
            },
            style="day",
        )
        res = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            period_split="full",
            raw_params=params,
            preloaded_df=(df, "SyntheticLowVol"),
        )
        trades = res["trades"]
        self.assertGreater(len(trades), 0, "Expected at least 1 executed trade")
        t0 = trades[0]
        self.assertIn("risk_target_usdt", t0)
        self.assertIn("risk_actual_usdt", t0)
        self.assertIn("leverage_cap_hit", t0)
        self.assertTrue(t0["leverage_cap_hit"], f"Expected leverage_cap_hit=True, got {t0}")
        self.assertLess(
            t0["risk_actual_usdt"],
            t0["risk_target_usdt"],
            f"Expected risk_actual_usdt ({t0['risk_actual_usdt']}) < risk_target_usdt ({t0['risk_target_usdt']})",
        )

        metrics = res["metrics"]
        self.assertIn("leverage_capped_trades_pct", metrics)
        self.assertIn("median_actual_risk_usdt", metrics)
        self.assertGreater(metrics["leverage_capped_trades_pct"], 0.0)
        self.assertLess(metrics["median_actual_risk_usdt"], t0["risk_target_usdt"])


class TestD4SlippageAndGrossPnlAccounting(unittest.TestCase):
    def test_d4_gross_pnl_equals_net_pnl_plus_fees_plus_slippage(self):
        """
        D4: Each trade and summary metrics must expose gross_pnl_usdt and slippage_cost_usdt
        (plus total_slippage_usdt and total_execution_costs_usdt in metrics),
        satisfying gross_pnl_usdt == net_pnl_usdt + fees_usdt + slippage_cost_usdt within rounding tolerance.
        """
        df = build_synthetic_ohlcv(n_candles=750, seed=404, drift=0.0004, volatility=0.004)
        params = strategy_lab.normalize_lab_params(
            {
                "fee_bps": 4.0,
                "slippage_bps": 3.0,
                "min_teddy_score": 30,
                "adx_min": 10.0,
                "partial_tp_enabled": True,
                "partial_tp_rr": 1.0,
            },
            style="day",
        )
        res = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            period_split="full",
            raw_params=params,
            preloaded_df=(df, "SyntheticCosts"),
        )
        trades = res["trades"]
        self.assertGreater(len(trades), 0, "Expected trades to verify cost accounting")

        for t in trades:
            self.assertIn("gross_pnl_usdt", t)
            self.assertIn("slippage_cost_usdt", t)
            self.assertGreater(t["slippage_cost_usdt"], 0.0)
            reconstructed_gross = t["pnl_usdt"] + t["fees_usdt"] + t["slippage_cost_usdt"]
            self.assertAlmostEqual(
                t["gross_pnl_usdt"],
                reconstructed_gross,
                delta=0.05,
                msg=f"Trade #{t['id']} gross_pnl_usdt ({t['gross_pnl_usdt']}) != pnl + fees + slippage ({reconstructed_gross})",
            )

        m = res["metrics"]
        self.assertIn("gross_pnl_usdt", m)
        self.assertIn("total_slippage_usdt", m)
        self.assertIn("total_execution_costs_usdt", m)
        self.assertGreater(m["total_slippage_usdt"], 0.0)

        sum_net_trades = sum(t["pnl_usdt"] for t in trades)
        reconstructed_total_gross = sum_net_trades + m["total_fees_usdt"] + m["total_slippage_usdt"]
        self.assertAlmostEqual(
            m["gross_pnl_usdt"],
            reconstructed_total_gross,
            delta=0.15,
            msg=f"Metrics gross_pnl_usdt ({m['gross_pnl_usdt']}) != sum_net + total_fees + total_slippage ({reconstructed_total_gross})",
        )


class TestD5OpenPositionAtEndOfBacktest(unittest.TestCase):
    def test_d5_open_position_force_closed_with_end_of_backtest_and_consistent_accounting(self):
        """
        D5: If a position is still open on the final simulated candle, it must be closed
        with exit_reason='END_OF_BACKTEST' (including exit fee and slippage), so that:
        final_capital - initial_capital == sum(t['pnl_usdt'] for t in trades).
        """
        df = build_synthetic_ohlcv(n_candles=650, seed=505, drift=0.0003, volatility=0.0015)
        params = strategy_lab.normalize_lab_params(
            {
                "min_teddy_score": 25,
                "adx_min": 5.0,
                "min_atr_pct": 0.0,
                "min_volume_ratio": 0.0,
                "require_ema_alignment": False,
                "require_macd_confirmation": False,
                "sl_mode": "fixed_pct",
                "sl_fixed_pct": 15.0,        # Wide SL so position stays open until end
                "tp_mode": "fixed_pct",
                "tp_fixed_pct": 40.0,        # Wide TP so position stays open until end
                "min_rr_ratio": 1.0,
                "partial_tp_enabled": False,
                "breakeven_enabled": False,
                "trailing_stop_enabled": False,
                "exit_on_opposite_signal": False,
                "max_bars_in_trade": 1000,   # Won't hit time stop in 50 simulated bars
            },
            style="day",
        )
        res = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            period_split="full",
            raw_params=params,
            preloaded_df=(df, "SyntheticOpenAtEnd"),
        )
        trades = res["trades"]
        self.assertGreater(len(trades), 0, "Expected open position to be force-closed at END_OF_BACKTEST")
        last_trade = trades[-1]
        self.assertEqual(
            last_trade["exit_reason"],
            "END_OF_BACKTEST",
            f"Expected exit_reason='END_OF_BACKTEST', got {last_trade['exit_reason']}",
        )

        m = res["metrics"]
        sum_trades_pnl = round(sum(t["pnl_usdt"] for t in trades), 2)
        capital_diff = round(m["final_capital"] - m["initial_capital"], 2)
        self.assertAlmostEqual(
            capital_diff,
            sum_trades_pnl,
            delta=0.05,
            msg=f"Accounting mismatch: final_capital - initial_capital ({capital_diff}) != sum(trades pnl) ({sum_trades_pnl})",
        )


class TestD6PartialTpConservativeOrderingAndSlippage(unittest.TestCase):
    def test_d6_partial_tp_applies_slippage_and_does_not_activate_be_on_same_candle(self):
        """
        D6: When partial TP triggers on candle k:
        1. Partial TP exit price must include unfavorable slippage (slippage_bps > 0).
        2. Neither Break-Even nor Trailing Stop may be activated on that exact same candle k
           (no intra-bar ordering assumption that High was reached before Low or Close).
        """
        start_dt = datetime(2025, 4, 1, 0, 0, tzinfo=timezone.utc)
        rows = []
        price = 50000.0
        for i in range(620):
            ts = start_dt + timedelta(minutes=i * 15)
            open_p = price
            close_p = price * 1.001
            high_p = close_p * 1.001
            low_p = open_p * 0.999
            if i == 601:
                # Bar right after entry at i=600: reaches +1.3R (triggers partial TP at 1.0R),
                # then on i=602 drops back to initial SL!
                high_p = open_p * 1.015
                close_p = open_p * 1.002
            elif i == 602:
                # Drops to hit initial SL (-1.0%), which would have been BREAKEVEN_SL if BE activated on i=601!
                low_p = open_p * 0.982
                close_p = open_p * 0.985
            rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "Open": round(open_p, 4),
                    "High": round(high_p, 4),
                    "Low": round(low_p, 4),
                    "Close": round(close_p, 4),
                    "Volume": 300.0,
                }
            )
            price = close_p

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.set_index("timestamp", inplace=True)

        base_cfg = {
            "min_teddy_score": 25,
            "adx_min": 5.0,
            "min_atr_pct": 0.0,
            "min_volume_ratio": 0.0,
            "require_ema_alignment": False,
            "require_macd_confirmation": False,
            "allow_long": True,
            "allow_short": False,
            "sl_mode": "fixed_pct",
            "sl_fixed_pct": 1.0,
            "tp_mode": "fixed_pct",
            "tp_fixed_pct": 4.0,
            "min_rr_ratio": 1.0,
            "partial_tp_enabled": True,
            "partial_tp_rr": 1.0,
            "partial_tp_close_pct": 50.0,
            "breakeven_enabled": True,
            "breakeven_trigger_rr": 1.0,
            "trailing_stop_enabled": True,
            "trailing_activation_rr": 1.1,
            "exit_on_opposite_signal": False,
        }
        res_with_slip = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            raw_params={**base_cfg, "slippage_bps": 10.0},
            preloaded_df=(df, "SyntheticD6"),
        )
        t_slip = res_with_slip["trades"][0]
        self.assertEqual(t_slip["entry_index"], 600)
        self.assertTrue(t_slip["partial_taken"], "Expected partial_taken=True on candle 601")
        # Because BE and Trailing Stop must NOT activate on the same candle as Partial TP (601),
        # the drop on candle 602 must hit initial STOP_LOSS, not BREAKEVEN_SL or TRAILING_SL!
        self.assertEqual(
            t_slip["exit_reason"],
            "STOP_LOSS",
            f"BE or Trailing Stop activated on the exact same candle as Partial TP! Got exit_reason={t_slip['exit_reason']}",
        )
        # Also verify that partial TP slippage is accounted for in slippage_cost_usdt
        # Entry + Partial Exit (50%) + Final Exit (50%) => total slippage > Entry + 50% Final Exit alone
        entry_and_rem_slip_only = t_slip["notional_usdt"] * 0.0010 * 1.5
        self.assertGreater(
            t_slip["slippage_cost_usdt"],
            entry_and_rem_slip_only * 1.15,
            f"Partial TP did not include slippage! slippage_cost_usdt={t_slip['slippage_cost_usdt']} vs {entry_and_rem_slip_only}",
        )


class TestD7SameBarReEntryBlocked(unittest.TestCase):
    def test_d7_no_entry_on_same_candle_index_as_exit(self):
        """
        D7: Even with cooldown_candles=0, a new position must NEVER be opened on the same
        candle index i where the previous position was closed.
        """
        df = build_synthetic_ohlcv(n_candles=700, seed=707, drift=0.0004, volatility=0.006)
        params = strategy_lab.normalize_lab_params(
            {
                "cooldown_candles": 0,
                "min_teddy_score": 25,
                "adx_min": 5.0,
                "min_atr_pct": 0.0,
                "min_volume_ratio": 0.0,
                "require_ema_alignment": False,
                "require_macd_confirmation": False,
                "sl_mode": "fixed_pct",
                "sl_fixed_pct": 0.3,
                "tp_mode": "fixed_pct",
                "tp_fixed_pct": 0.6,
                "min_rr_ratio": 1.5,
                "max_trades_per_day": 100,
                "max_consecutive_losses": 50,
            },
            style="day",
        )
        res = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            raw_params=params,
            preloaded_df=(df, "SyntheticD7"),
        )
        trades = res["trades"]
        self.assertGreater(len(trades), 2)
        for k in range(1, len(trades)):
            prev_exit_idx = trades[k - 1]["exit_index"]
            curr_entry_idx = trades[k]["entry_index"]
            self.assertGreater(
                curr_entry_idx,
                prev_exit_idx,
                f"Trade #{trades[k]['id']} entered on bar {curr_entry_idx}, same bar where Trade #{trades[k-1]['id']} exited ({prev_exit_idx})!",
            )


class TestD8RsiWilderConvergence(unittest.TestCase):
    def test_d8_rsi_uses_wilder_smoothing(self):
        """
        D8: indicators.rsi must use Wilder smoothing (_wilder_smooth, alpha=1/period)
        consistent with ADX and ATR, rather than a simple rolling mean.
        """
        df = build_synthetic_ohlcv(n_candles=300, seed=808)
        close = df["Close"].astype(float)
        period = 14
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain_wilder = gain.ewm(alpha=1.0 / period, adjust=False).mean()
        avg_loss_wilder = loss.ewm(alpha=1.0 / period, adjust=False).mean()
        rs_ref = avg_gain_wilder / avg_loss_wilder
        rsi_ref = 100.0 - (100.0 / (1.0 + rs_ref))

        computed_rsi = strategy_lab.calc_rsi(close, period=period)
        # Compare on the last 50 bars after warmup
        for idx in range(-50, 0):
            self.assertAlmostEqual(
                float(computed_rsi.iloc[idx]),
                float(rsi_ref.iloc[idx]),
                places=4,
                msg=f"RSI at index {idx} does not match Wilder RSI!",
            )


class TestD9StandardSortinoDownsideDeviation(unittest.TestCase):
    def test_d9_sortino_uses_zero_target_downside_deviation_over_all_periods(self):
        """
        D9: Sortino ratio must compute downside deviation with target=0 over ALL N returns:
        downside_dev = sqrt(sum(min(0, r)^2 for r in rets) / len(rets)),
        not the sample standard deviation around mean(downside) over negative returns only.
        Specifically, when all negative returns are identical (e.g. -0.001), std(downside) was 0
        giving Sortino=0.0, whereas true downside deviation is > 0 and Sortino is well-defined.
        """
        # Construct an equity curve where negative returns are all identical (-0.1%) and positive returns are +0.3%
        equity_curve = []
        eq = 10000.0
        for k in range(40):
            if k > 0:
                ret = -0.001 if (k % 3 == 0) else 0.0025
                eq = eq * (1.0 + ret)
            equity_curve.append(
                {
                    "timestamp": f"2025-01-01T{k // 4:02d}:{(k % 4) * 15:02d}:00+00:00",
                    "equity": round(eq, 4),
                    "balance": round(eq, 4),
                    "drawdown_pct": 0.0,
                    "drawdown_usdt": 0.0,
                    "price": 50000.0,
                }
            )

        eq_vals = [float(pt["equity"]) for pt in equity_curve]
        rets = [(eq_vals[k] - eq_vals[k - 1]) / eq_vals[k - 1] for k in range(1, len(eq_vals))]
        periods_per_year = (365.0 * 86400.0) / 900.0
        mean_r = sum(rets) / len(rets)
        expected_downside_dev = math.sqrt(sum(min(0.0, r) ** 2 for r in rets) / len(rets))
        expected_sortino = round((mean_r / expected_downside_dev) * math.sqrt(periods_per_year), 2)

        metrics = strategy_lab._compute_backtest_metrics(
            initial_capital=10000.0,
            final_equity=eq,
            closed_trades=[],
            equity_curve=equity_curve,
            timeframe="15m",
        )
        self.assertGreater(expected_sortino, 0.0)
        self.assertAlmostEqual(
            metrics["sortino_ratio"],
            expected_sortino,
            places=2,
            msg=f"Sortino ratio ({metrics['sortino_ratio']}) does not match standard formula ({expected_sortino})",
        )


class TestD10SweepValidationAndEngineVersion(unittest.TestCase):
    def test_d10_parameter_sweep_validates_values_and_engine_version_is_2_2_0(self):
        """
        D10: run_parameter_sweep must validate sweep values via _coerce_strict_param_value
        (rejecting out-of-bounds or invalid values instead of silently clamping them),
        and ENGINE_VERSION must be '2.2.0' in every run result.
        """
        self.assertEqual(strategy_lab.ENGINE_VERSION, "2.2.0")
        df = build_synthetic_ohlcv(n_candles=650, seed=1010)
        res = strategy_lab.run_backtest_experiment(
            symbol="BTCUSDT",
            timeframe="15m",
            trading_style="day",
            preloaded_df=(df, "SyntheticD10"),
        )
        self.assertEqual(res["engine_version"], "2.2.0")

        # Out-of-bounds value (e.g. min_teddy_score=999 or 'invalid') must raise ValueError in run_parameter_sweep
        with self.assertRaises(ValueError):
            strategy_lab.run_parameter_sweep(
                symbol="BTCUSDT",
                timeframe="15m",
                trading_style="day",
                base_params=strategy_lab.normalize_lab_params(None, style="day"),
                param_name="min_teddy_score",
                values=[55, 999],
            )


if __name__ == "__main__":
    unittest.main()






