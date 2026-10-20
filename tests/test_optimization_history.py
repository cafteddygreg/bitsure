"""Profondeur historique de l'Optimization Lab : la période demandée doit réellement être chargée, simulée et rapportée.

Chaîne testée (sans réseau ni PostgreSQL) : plan_request -> job -> load_historical_candles (cache SQLite + faux Binance paginé)
-> nettoyage -> warm-up -> split 60/20/20 -> run_backtest_experiment -> rapport.
"""
import os
import sqlite3
import sys
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

import strategy_lab as sl  # noqa: E402
from optimization import engine, store  # noqa: E402
from optimization.space import SpaceError  # noqa: E402
from optimization.worker import worker_loop  # noqa: E402
from test_optimization_lab import FakeNotifier, SqliteDB  # noqa: E402

TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


def ms(date: str) -> int:
    return sl._parse_date_to_ms(date, 0)


def idx_ms(df) -> "np.ndarray":
    """Index -> millisecondes (indépendant de la résolution interne de pandas : ns, us ou ms)."""
    import pandas as pd
    return ((df.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(milliseconds=1)).to_numpy(dtype="int64")


class _Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._p, self.headers = status, payload, headers or {}

    def json(self):
        return self._p


class FakeBinance:
    """Imite /klines : pagination (limit), bougies clôturées uniquement, historique commençant à `listing_ms`."""

    def __init__(self, listing_ms=0, fail_status=None):
        self.listing_ms, self.fail_status, self.calls = listing_ms, fail_status, 0

    def __call__(self, url, params=None, timeout=None):
        self.calls += 1
        if self.fail_status:
            return _Resp(self.fail_status)
        tf = TF_MS[params["interval"]]
        start, end, limit = int(params["startTime"]), int(params["endTime"]), int(params["limit"])
        first = max(((max(start, self.listing_ms) + tf - 1) // tf) * tf, 0)
        last_open = min(end, int(time.time() * 1000) - tf)  # uniquement des bougies déjà clôturées
        n = min(limit, max(0, (last_open - first) // tf + 1))
        opens = first + tf * np.arange(n, dtype="int64")
        i = opens // tf
        price = 100 + 8 * np.sin(i / 90.0) + 3 * np.sin(i / 17.0) + (i % 5) * 0.05
        rows = [[int(o), f"{p:.4f}", f"{p + .6:.4f}", f"{p - .6:.4f}", f"{p + .2:.4f}", "10", int(o) + tf - 1] for o, p in zip(opens, price)]
        return _Resp(200, rows)


def make_db():
    db = SqliteDB()
    db.execute(
        """CREATE TABLE strategy_lab_ohlcv (market_type TEXT, symbol TEXT, timeframe TEXT, open_time_ms INTEGER, close_time_ms INTEGER,
           open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT, fetched_at REAL,
           PRIMARY KEY (market_type, symbol, timeframe, open_time_ms))"""
    )
    return db


class HistoryBase(unittest.TestCase):
    listing_ms = 0

    def setUp(self):
        self.db = make_db()
        self.net = FakeBinance(self.listing_ms)
        for p in (
            mock.patch.object(sl, "get_db", lambda: self.db),
            mock.patch("requests.get", self.net),
            mock.patch.object(sl.time, "sleep", lambda s: None),
        ):
            p.start()
            self.addCleanup(p.stop)

    def load(self, tf, start, end, warmup=150, **kw):
        return sl.load_historical_candles("BTCUSDT", tf, "futures", start_date=start, end_date=end, max_candles=4000,
                                          warmup_candles=warmup, max_period_candles=sl.OPT_MAX_PERIOD_CANDLES, **kw)


class LoaderTests(HistoryBase):
    # Test A — courte période : demandé = chargé = simulé (hors warm-up)
    def test_a_short_period_requested_equals_loaded(self):
        df, _src, st = self.load("15m", "2024-03-01", "2024-03-10", warmup=150)
        sim = df[df.index >= "2024-03-01"]
        self.assertEqual(sim.index[0].isoformat(), "2024-03-01T00:00:00+00:00")
        self.assertEqual(sim.index[-1].isoformat(), "2024-03-10T23:45:00+00:00")  # date de fin INCLUSIVE (jour entier)
        self.assertEqual(len(sim), 10 * 96)
        self.assertEqual(len(df) - len(sim), 150)  # warm-up exact, avant la date de début
        self.assertFalse(st["period_clamped"])
        self.assertFalse(st["fetch_incomplete"])

    def test_chronological_unique_and_gap_free(self):
        df, _s, _st = self.load("1h", "2023-01-01", "2023-06-30")
        self.assertTrue(df.index.is_monotonic_increasing)
        self.assertFalse(df.index.duplicated().any())
        self.assertEqual(set(np.diff(idx_ms(df))), {3_600_000})

    # Test B (chargeur) — 2022 -> 2026 ne retombe PAS sur 4000 bougies
    def test_b_long_period_not_truncated_1h(self):
        df, _s, st = self.load("1h", "2022-01-01", "2026-10-10", warmup=150)
        expected = (ms("2026-10-11") - ms("2022-01-01")) // TF_MS["1h"]
        sim = df[df.index >= "2022-01-01"]
        self.assertGreaterEqual(len(sim), expected - 1)
        self.assertGreater(len(df), 40_000)
        self.assertEqual(sim.index[0].isoformat(), "2022-01-01T00:00:00+00:00")
        self.assertFalse(st["period_clamped"])
        self.assertEqual(st["loaded_candles"], len(df))

    # Test C — plusieurs timeframes
    def test_c_timeframes(self):
        for tf, days in (("1m", 3), ("5m", 20), ("15m", 60), ("1h", 200), ("4h", 700)):
            with self.subTest(tf=tf):
                df, _s, st = self.load(tf, "2024-01-01", "2024-01-01" if False else f"2024-01-{min(days, 28):02d}" if days <= 28 else "2025-11-30", warmup=100)
                self.assertTrue(df.index.is_monotonic_increasing)
                self.assertEqual(int(np.median(np.diff(idx_ms(df)))), TF_MS[tf])
                self.assertEqual(df.index[0], df.index[0].floor(f"{TF_MS[tf] // 60_000}min"))
                self.assertGreater(st["loaded_candles"], 100)

    def test_cache_is_reused_without_network(self):
        self.load("1h", "2023-01-01", "2023-03-31")
        calls = self.net.calls
        df2, src, st = self.load("1h", "2023-01-01", "2023-03-31")
        self.assertEqual(self.net.calls, calls)  # aucun accès réseau : tout vient du cache
        self.assertEqual(st["fetched"], 0)
        self.assertIn("Cache", src)

    def test_missing_middle_range_is_refilled(self):
        df, _s, _st = self.load("1h", "2023-01-01", "2023-03-31")
        n = len(df)
        self.db.execute("DELETE FROM strategy_lab_ohlcv WHERE open_time_ms >= %s AND open_time_ms < %s", (ms("2023-02-01"), ms("2023-02-10")))
        df2, _s2, st2 = self.load("1h", "2023-01-01", "2023-03-31")
        self.assertEqual(len(df2), n)
        self.assertEqual(st2["fetched"], 9 * 24)

    def test_pagination_exceeds_single_request_limit(self):
        before = self.net.calls
        df, _s, st = self.load("15m", "2024-01-01", "2024-03-31")
        self.assertGreater(len(df), 8000)
        self.assertGreaterEqual(self.net.calls - before, len(df) // 1000)

    def test_rate_limited_download_is_flagged_incomplete_not_silent(self):
        self.net.fail_status = 429
        with self.assertRaises(ValueError):  # rien en cache et rien téléchargé : échec explicite
            self.load("1h", "2023-01-01", "2023-02-01")

    def test_default_depth_without_dates_honours_max_candles(self):
        df, _s, _st = sl.load_historical_candles("BTCUSDT", "15m", "futures", max_candles=4000, warmup_candles=100,
                                                 max_period_candles=sl.OPT_MAX_PERIOD_CANDLES)
        self.assertEqual(len(df), 4000 + 100)  # l'ancien code plafonnait silencieusement à 2500 + warm-up


class PlanValidationTests(unittest.TestCase):
    base = {"symbol": "BTCUSDT", "timeframe": "4h", "trading_style": "day", "method": "grid",
            "parameters": [{"key": "adx_min", "values": [16, 20]}]}

    def test_e_invalid_dates(self):
        for body, msg in (
            ({"start_date": "2024-02-01", "end_date": "2024-01-01"}, "postérieure"),
            ({"start_date": "2024-02-01T12:00:00", "end_date": "2024-02-01T12:00:00"}, "postérieure"),
            ({"start_date": "pas-une-date"}, "début invalide"),
            ({"start_date": "2024-01-01", "end_date": "n'importe quoi"}, "fin invalide"),
        ):
            with self.subTest(body=body), self.assertRaises(SpaceError) as ctx:
                engine.plan_request({**self.base, **body})
            self.assertIn(msg, str(ctx.exception))

    def test_b_long_period_accepted_when_within_budget(self):
        req, _plan = engine.plan_request({**self.base, "timeframe": "1h", "start_date": "2022-01-01", "end_date": "2026-10-10"})
        self.assertGreater(req["period_candles"], 40_000)  # et non 4000 / 12000
        req5, _ = engine.plan_request({**self.base, "timeframe": "5m", "start_date": "2022-01-01", "end_date": "2026-10-10"})
        self.assertGreater(req5["period_candles"], 400_000)

    def test_too_deep_period_is_refused_with_explanation_not_truncated(self):
        with self.assertRaises(SpaceError) as ctx:
            engine.plan_request({**self.base, "timeframe": "1m", "start_date": "2022-01-01", "end_date": "2026-10-10"})
        text = str(ctx.exception)
        self.assertIn("1m", text)
        self.assertIn("Timeframes compatibles", text)

    def test_time_budget_guard(self):
        with mock.patch.object(engine, "OPT_MAX_ESTIMATED_SECONDS", 60), self.assertRaises(SpaceError) as ctx:
            engine.plan_request({**self.base, "timeframe": "15m", "start_date": "2022-01-01", "end_date": "2026-10-10"})
        self.assertIn("Durée estimée", str(ctx.exception))

    def test_without_dates_max_candles_is_validated_against_new_limit(self):
        engine.plan_request({**self.base, "max_candles": 50_000})
        with self.assertRaises(SpaceError):
            engine.plan_request({**self.base, "max_candles": 100})


class JobEndToEndTests(HistoryBase):
    REQ = {"symbol": "BTCUSDT", "timeframe": "4h", "trading_style": "day", "market_type": "futures", "method": "grid",
           "min_trades": 5, "top_k": 3, "parameters": [{"key": "adx_min", "values": [16, 20]}]}

    def run_job(self, **over):
        store.ensure_schema(self.db)
        req, plan = engine.plan_request({**self.REQ, **over})
        job_id = store.create_job(7, req, plan, engine.estimate_total_steps(plan["n_configs"], req["top_k"]), db=self.db)
        worker_loop(once=True, db=self.db, notifier=FakeNotifier())
        return store.get_job(job_id, include_report=True, db=self.db)

    # Tests B + F — 2022 -> 2026 de bout en bout, split vérifié mathématiquement
    def test_b_f_2022_to_2026_end_to_end_report_proves_depth_and_split(self):
        job = self.run_job(start_date="2022-01-01", end_date="2026-10-10")
        self.assertEqual(job["status"], "completed", job.get("error"))
        per = job["summary"]["period"]
        self.assertGreater(per["simulated_candles"], 10_000)          # pas 4000
        self.assertTrue(per["loaded_start"].startswith("2021-12"))    # warm-up avant le 2022-01-01
        self.assertTrue(per["simulated_start"].startswith("2022-01-01"))
        self.assertTrue(per["simulated_end"].startswith("2026-10-10"))
        w = per["windows"]
        n = per["simulated_candles"]
        tr, va, oos = (w[k]["candles"] for k in ("training", "validation", "oos"))
        self.assertEqual(tr + va + oos, n)
        self.assertEqual(tr, int(n * 0.6))                 # mêmes bornes entières que le moteur de backtest
        self.assertEqual(va, int(n * 0.8) - int(n * 0.6))
        self.assertLessEqual(abs(tr - n * 0.6), 1)         # ≈ 60 % / 20 % / 20 % aux arrondis près
        self.assertLessEqual(abs(va - n * 0.2), 1)
        self.assertLessEqual(abs(oos - n * 0.2), 1.5)
        self.assertLess(w["training"]["end"], w["validation"]["start"])  # chronologique strict
        self.assertLess(w["validation"]["end"], w["oos"]["start"])
        self.assertEqual(w["training"]["start"], per["simulated_start"])
        self.assertEqual(w["oos"]["end"], per["simulated_end"])
        self.assertEqual(per["data_source"], "Binance USD-M Futures API")
        html = job["report_html"]
        for needle in ("Demandée", "Chargée", "Simulée", "Warm-up", "2022-01-01", "Binance USD-M Futures API"):
            self.assertIn(needle, html)
        self.assertEqual(per["warmup_required"] <= per["warmup_candles"], True)

    def test_a_short_period_job_windows_match_dates(self):
        job = self.run_job(timeframe="1h", start_date="2024-03-01", end_date="2024-05-31")
        self.assertEqual(job["status"], "completed", job.get("error"))
        per = job["summary"]["period"]
        self.assertTrue(per["simulated_start"].startswith("2024-03-01"))
        self.assertTrue(per["simulated_end"].startswith("2024-05-31T23:00"))
        self.assertEqual(per["simulated_candles"], 92 * 24)
        self.assertEqual(per["notes"], [])

    def test_job_without_dates_uses_requested_depth(self):
        job = self.run_job(max_candles=6000)
        self.assertEqual(job["status"], "completed", job.get("error"))
        per = job["summary"]["period"]
        self.assertEqual(per["simulated_candles"], 6000)

    def test_end_date_is_inclusive_of_whole_day(self):
        job = self.run_job(timeframe="1h", start_date="2024-03-01", end_date="2024-03-31")
        per = job["summary"]["period"]
        self.assertTrue(per["simulated_end"].startswith("2024-03-31T23:00"))


class RecentSymbolTests(HistoryBase):
    listing_ms = ms("2024-03-01")

    # Test D — historique inexistant avant la cotation : expliqué, jamais inventé
    def test_d_history_starts_after_requested_start_is_reported(self):
        store.ensure_schema(self.db)
        req, plan = engine.plan_request({**JobEndToEndTests.REQ, "timeframe": "1h", "start_date": "2022-01-01", "end_date": "2026-10-10"})
        job_id = store.create_job(7, req, plan, engine.estimate_total_steps(plan["n_configs"], req["top_k"]), db=self.db)
        worker_loop(once=True, db=self.db, notifier=FakeNotifier())
        job = store.get_job(job_id, include_report=True, db=self.db)
        self.assertEqual(job["status"], "completed", job.get("error"))
        per = job["summary"]["period"]
        self.assertTrue(per["loaded_start"] >= "2024-03-01")             # aucune donnée avant la cotation
        self.assertTrue(any("Historique indisponible" in n for n in per["notes"]))
        self.assertTrue(any("Historique indisponible" in w for w in job["summary"]["warnings"]))
        self.assertGreaterEqual(per["warmup_candles"], per["warmup_required"])  # indicateurs formés avant le 1er trade
        self.assertIn("Historique indisponible", job["report_html"])
        n = per["simulated_candles"]
        w = per["windows"]
        self.assertEqual(w["training"]["candles"] + w["validation"]["candles"] + w["oos"]["candles"], n)


class TooShortTests(HistoryBase):
    def test_e_insufficient_data_fails_cleanly(self):
        store.ensure_schema(self.db)
        req, plan = engine.plan_request({**JobEndToEndTests.REQ, "start_date": "2024-03-01", "end_date": "2024-03-05"})
        job_id = store.create_job(7, req, plan, engine.estimate_total_steps(plan["n_configs"], req["top_k"]), db=self.db)
        worker_loop(once=True, db=self.db, notifier=FakeNotifier())
        job = store.get_job(job_id, db=self.db)
        self.assertEqual(job["status"], "failed")
        self.assertIn("insuffisant", (job.get("error") or "").lower())


class ValidationVectorizedTests(unittest.TestCase):
    def test_vectorized_cleaning_matches_rules(self):
        import pandas as pd
        idx = pd.date_range("2024-01-01", periods=10, freq="1h", tz="UTC")
        df = pd.DataFrame({"Open": 10.0, "High": 11.0, "Low": 9.0, "Close": 10.5, "Volume": 5.0}, index=idx)
        df.iloc[3, df.columns.get_loc("High")] = 9.5       # High < Close : incohérent
        df.iloc[5, df.columns.get_loc("Open")] = -1.0      # prix négatif
        df = df.drop(df.index[7])                          # une lacune
        out, dq = sl.validate_and_clean_ohlcv(df, "1h", now_ms=ms("2025-01-01"))
        self.assertEqual(dq["invalid_ohlc_removed"], 2)
        self.assertEqual(len(out), 7)
        self.assertGreaterEqual(dq["missing_intervals_count"], 1)
        self.assertEqual(dq["first_candle_utc"][:10], "2024-01-01")
        # bougie non clôturée exclue
        out2, dq2 = sl.validate_and_clean_ohlcv(df, "1h", now_ms=ms("2024-01-01") + 3 * 3_600_000)
        self.assertGreater(dq2["unclosed_excluded"], 0)


if __name__ == "__main__":
    unittest.main()
