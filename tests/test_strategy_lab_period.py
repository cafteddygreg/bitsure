"""Régression : le choix d'une période de backtest (start/end) doit être respecté,
même lorsque la plage dépasse la « profondeur » en bougies (max_candles)."""

import time
import unittest
from unittest import mock

import strategy_lab

TF_MS = 15 * 60 * 1000


class _FakeCursor:
    def fetchall(self):
        return []


class _FakeDB:
    def execute(self, *args, **kwargs):
        return _FakeCursor()


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _fake_binance_get(url, params=None, timeout=None):
    start, end, limit = int(params["startTime"]), int(params["endTime"]), int(params["limit"])
    t = ((start + TF_MS - 1) // TF_MS) * TF_MS
    rows = []
    while t < end and len(rows) < limit:
        price = 50000.0 + (t // TF_MS) % 200
        rows.append([t, str(price), str(price + 20), str(price - 20), str(price + 5), "10", t + TF_MS - 1])
        t += TF_MS
    return _FakeResponse(rows)


def _iso(days_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days_ago * 86400))


class StrategyLabPeriodTests(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(strategy_lab, "get_db", lambda: _FakeDB()),
            mock.patch("requests.get", _fake_binance_get),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_period_longer_than_depth_is_not_truncated(self):
        df, _src, stats = strategy_lab.load_historical_candles(
            "BTCUSDT", "15m", "futures", start_date=_iso(30), max_candles=800, warmup_candles=300
        )
        span_days = (df.index[-1] - df.index[0]).total_seconds() / 86400
        # 30 jours demandés + warm-up : l'ancien code ne renvoyait que ~800 + 300 bougies (≈ 11 jours)
        self.assertGreater(span_days, 30)
        self.assertFalse(stats["period_clamped"])

    def test_huge_period_is_clamped_and_flagged(self):
        df, _src, stats = strategy_lab.load_historical_candles(
            "BTCUSDT", "15m", "futures", start_date=_iso(365), max_candles=800, warmup_candles=300
        )
        self.assertTrue(stats["period_clamped"])
        self.assertLessEqual(len(df), strategy_lab.LAB_MAX_PERIOD_CANDLES + 300)

    def test_backtest_simulates_requested_window(self):
        res = strategy_lab.run_backtest_experiment(
            "BTCUSDT", "15m", "day", "futures", "full", start_date=_iso(20), end_date=_iso(5), max_candles=800
        )
        self.assertGreater(res["candles_count"], 1300)  # ≈ 15 jours × 96 bougies
        self.assertLess(res["candles_count"], 1600)


if __name__ == "__main__":
    unittest.main()
