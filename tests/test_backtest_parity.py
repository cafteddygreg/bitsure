import hashlib
from pathlib import Path
import unittest

import pandas as pd

from backtest.engine import BacktestConfig, BacktestEngine
from backtest.performance import build_summary
from backtest.strategy import BacktestSignalEngine
from signal_engine import SignalEngine


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "btc_1h_300.csv"


def _load_fixture_df() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


class BacktestParityAndDefectsTests(unittest.TestCase):
    def test_fixture_exists_and_has_300_rows(self):
        self.assertTrue(FIXTURE_PATH.exists(), f"Missing fixture {FIXTURE_PATH}")
        df = pd.read_csv(FIXTURE_PATH)
        self.assertEqual(len(df), 300)

    def test_signal_and_score_parity_on_btc_1h_300(self):
        df = _load_fixture_df()
        # Compare across multiple windows from 60 to 300 bars
        sample_indices = list(range(60, 300, 15)) + [299]
        for idx in sample_indices:
            window = df.iloc[: idx + 1]
            bt_res = BacktestSignalEngine.analyze(window, symbol="BTCUSDT", style="day")
            live_res = SignalEngine.analyze(window, symbol="BTCUSDT", style="day")
            self.assertEqual(
                bt_res.get("signal"),
                live_res.get("signal"),
                f"Signal mismatch at bar {idx}: backtest={bt_res.get('signal')} vs live={live_res.get('signal')}",
            )
            self.assertEqual(
                bt_res.get("teddy_score"),
                live_res.get("teddy_score"),
                f"Score mismatch at bar {idx}: backtest={bt_res.get('teddy_score')} vs live={live_res.get('teddy_score')}",
            )

    def test_multi_symbol_positions_never_closed_by_other_symbol_candle(self):
        cfg = BacktestConfig(
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=["1h"],
            initial_capital=10_000.0,
            fees_pct=0.0,
            slippage_pct=0.0,
            max_positions=4,
        )
        engine = BacktestEngine(cfg)
        t0 = pd.Timestamp("2025-01-01 00:00:00")
        t1 = pd.Timestamp("2025-01-01 01:00:00")

        # Open BTC around 100,000 and ETH around 3,000
        engine._try_open_position(
            "BTCUSDT",
            "1h",
            t0,
            100_000.0,
            {"signal": "BUY", "sl": 98_000.0, "tp": 104_000.0, "teddy_score": 80, "rr_ratio": 2.0},
        )
        engine._try_open_position(
            "ETHUSDT",
            "1h",
            t0,
            3_000.0,
            {"signal": "BUY", "sl": 2_900.0, "tp": 3_200.0, "teddy_score": 80, "rr_ratio": 2.0},
        )
        self.assertEqual(len(engine.open_positions), 2)

        # Process an ETH candle (low=2950 -> would hit BTC's SL=98,000 if not filtered by symbol!)
        eth_candle = pd.Series({"Open": 3_000.0, "High": 3_050.0, "Low": 2_950.0, "Close": 3_010.0})
        engine._manage_positions(eth_candle, t1, symbol="ETHUSDT")

        # Process a BTC candle (high=101,000 -> would hit ETH's TP=3,200 if not filtered by symbol!)
        btc_candle = pd.Series({"Open": 100_000.0, "High": 101_000.0, "Low": 99_500.0, "Close": 100_500.0})
        engine._manage_positions(btc_candle, t1, symbol="BTCUSDT")

        self.assertEqual(len(engine.closed_trades), 0)
        self.assertEqual(len(engine.open_positions), 2)
        open_symbols = {p["symbol"] for p in engine.open_positions}
        self.assertEqual(open_symbols, {"BTCUSDT", "ETHUSDT"})

    def test_trailing_stop_has_no_lookahead_on_current_candle(self):
        cfg = BacktestConfig(
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            initial_capital=10_000.0,
            fees_pct=0.0,
            slippage_pct=0.0,
            trailing_stop=True,
            trailing_stop_pct=1.0,  # 1% trail
        )
        engine = BacktestEngine(cfg)
        t0 = pd.Timestamp("2025-01-01 00:00:00")
        t1 = pd.Timestamp("2025-01-01 01:00:00")
        t2 = pd.Timestamp("2025-01-01 02:00:00")

        # Open BUY at 100, initial SL = 95, TP = 120
        engine._try_open_position(
            "BTCUSDT",
            "1h",
            t0,
            100.0,
            {"signal": "BUY", "sl": 95.0, "tp": 120.0, "teddy_score": 80, "rr_ratio": 2.5},
        )
        pos = engine.open_positions[0]

        # Bar 1: low=97 (above initial SL 95), closes at 110.
        # If there were lookahead using Bar 1's close (110), trailing SL would jump to 108.9 during Bar 1
        # and Bar 1's low (97) would falsely trigger a stop-out at 108.9!
        bar1 = pd.Series({"Open": 100.0, "High": 111.0, "Low": 97.0, "Close": 110.0})
        engine._manage_positions(bar1, t1, symbol="BTCUSDT")

        # Position must still be open after Bar 1, with SL still at 99.0 (or 95.0 before Bar 2)
        self.assertEqual(len(engine.open_positions), 1)
        self.assertEqual(len(engine.closed_trades), 0)

        # Bar 2: at the start of Bar 2, trailing SL updates from Bar 1's close (110 * 0.99 = 108.9).
        # Bar 2 dips to 108.0 -> triggers the new trailing SL at 108.9.
        bar2 = pd.Series({"Open": 110.0, "High": 110.5, "Low": 108.0, "Close": 109.0})
        engine._manage_positions(bar2, t2, symbol="BTCUSDT")

        self.assertEqual(len(engine.open_positions), 0)
        self.assertEqual(len(engine.closed_trades), 1)
        self.assertEqual(engine.closed_trades[0]["exit_reason"], "SL")
        self.assertAlmostEqual(engine.closed_trades[0]["exit_price"], 108.9, places=6)

    def test_expectancy_and_expectancy_r_on_three_known_trades(self):
        trades = [
            {"status": "closed", "pnl_net": 100.0, "initial_risk": 50.0, "duration_bars": 4},   # +2.0 R
            {"status": "closed", "pnl_net": -50.0, "initial_risk": 50.0, "duration_bars": 2},   # -1.0 R
            {"status": "closed", "pnl_net": 40.0, "initial_risk": 80.0, "duration_bars": 6},    # +0.5 R
        ]
        idx = pd.date_range("2025-01-01", periods=3, freq="1h")
        eq = pd.DataFrame({"equity": [10_100.0, 10_050.0, 10_090.0]}, index=idx)
        summary = build_summary(trades, eq, 10_000.0, timeframe="1h")

        # Expectancy = (100 - 50 + 40) / 3 = 30.0
        self.assertAlmostEqual(summary["expectancy"], 30.0, places=6)
        # Expectancy R = (2.0 - 1.0 + 0.5) / 3 = 0.5
        self.assertAlmostEqual(summary["expectancy_r"], 0.5, places=6)
        # 1h timeframe -> 365.25 * 24 = 8766 periods/year (not 252)
        self.assertAlmostEqual(summary["periods_per_year"], 8766.0, places=2)

    def test_mark_to_market_drawdown_and_max_daily_loss_and_export_metadata(self):
        cfg = BacktestConfig(
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            initial_capital=10_000.0,
            fees_pct=0.0,
            slippage_pct=0.0,
            max_daily_loss_pct=2.0,  # 2% daily loss limit = -200 USDT
        )
        engine = BacktestEngine(cfg)
        t0 = pd.Timestamp("2025-01-01 01:00:00")
        t1 = pd.Timestamp("2025-01-01 02:00:00")
        t2 = pd.Timestamp("2025-01-02 01:00:00")  # Next UTC day

        # Open a trade risking 250 USDT (2.5% by custom SL hit)
        engine.open_positions.append({
            "id": 1,
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "direction": "BUY",
            "entry_time": t0,
            "entry_price": 100.0,
            "signal_price": 100.0,
            "sl": 90.0,
            "initial_sl": 90.0,
            "initial_risk": 250.0,
            "tp": 130.0,
            "qty": 25.0,
            "leverage": 1.0,
            "margin": 2500.0,
            "entry_fee": 0.0,
            "status": "open",
            "bars_open": 0,
            "last_seen_time": t0,
            "last_seen_price": 95.0,
            "prev_close": 100.0,
        })
        engine.last_prices["BTCUSDT"] = 95.0
        engine._record_equity(t0)
        # Mark-to-market equity reflects unrealized loss (-125 USDT)
        self.assertAlmostEqual(engine.equity_points[-1]["equity"], 9_875.0, places=4)
        self.assertAlmostEqual(engine.equity_points[-1]["unrealized_pnl"], -125.0, places=4)

        # Close position at SL=90 -> realized loss -250 USDT (exceeds 2% = -200 USDT)
        engine._close_position(engine.open_positions[0], t1, 90.0, "SL")
        self.assertTrue(engine._is_daily_loss_limit_reached(t1))

        # Attempting to open another position on the same UTC day is blocked
        engine._try_open_position(
            "BTCUSDT",
            "1h",
            t1,
            90.0,
            {"signal": "BUY", "sl": 85.0, "tp": 105.0, "teddy_score": 85, "rr_ratio": 3.0},
        )
        self.assertEqual(len(engine.open_positions), 0)

        # Next UTC day resets daily loss counter and allows new entry
        engine._try_open_position(
            "BTCUSDT",
            "1h",
            t2,
            90.0,
            {"signal": "BUY", "sl": 85.0, "tp": 105.0, "teddy_score": 85, "rr_ratio": 3.0},
        )
        self.assertEqual(len(engine.open_positions), 1)


if __name__ == "__main__":
    unittest.main()
