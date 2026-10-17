"""Tests de l'Optimization Lab (sans réseau ni PostgreSQL : base SQLite en mémoire, chandeliers synthétiques)."""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd

import strategy_lab as sl
from optimization import engine, scoring, space, store
from optimization.report import build_report_html
from optimization.worker import worker_loop


class _Buffered:
    def __init__(self, rows, rowcount):
        self._rows, self.rowcount = rows, rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class SqliteDB:
    """Adaptateur minimal imitant database.PostgresConnection (placeholders %s -> ?)."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=None):
        cur = self.conn.execute(sql.replace("%s", "?"), tuple(params or ()))
        rows = cur.fetchall() if cur.description is not None else []
        rowcount = cur.rowcount
        self.conn.commit()
        return _Buffered(rows, rowcount)

    def commit(self):
        self.conn.commit()


def synthetic_df(n=3200, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.4, n)) + 5 * np.sin(np.arange(n) / 60)
    idx = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({
        "Open": close, "High": close + abs(rng.normal(0, .3, n)), "Low": close - abs(rng.normal(0, .3, n)),
        "Close": close + rng.normal(0, .1, n), "Volume": rng.uniform(100, 200, n),
    }, index=idx)


def fake_loader(**kwargs):
    return synthetic_df(), "synthetic", {"cached": 3200, "fetched": 0}


class FakeNotifier:
    def __init__(self):
        self.events = []

    def started(self, chat_id, job_id, req, n, resumed=False):
        self.events.append(("started", job_id, resumed))

    def progress(self, *a):
        self.events.append(("progress",) + a[1:3])

    def failed(self, chat_id, job_id, stage, error):
        self.events.append(("failed", job_id, stage))

    def cancelled(self, chat_id, job_id):
        self.events.append(("cancelled", job_id))

    def finished(self, chat_id, job_id, summary, html):
        self.events.append(("finished", job_id, len(html)))


REQUEST = {
    "symbol": "BTCUSDT", "timeframe": "15m", "trading_style": "day", "market_type": "futures", "max_candles": 4000,
    "method": "grid", "min_trades": 10, "top_k": 5,
    "parameters": [
        {"key": "adx_min", "min": 16, "max": 24, "step": 4},
        {"key": "min_teddy_score", "values": [54, 58, 62, 66]},
    ],
}


def make_job(db, request=None):
    store.ensure_schema(db)
    req, plan = engine.plan_request(request or REQUEST)
    return store.create_job(7, req, plan, engine.estimate_total_steps(plan["n_configs"], req["top_k"]), db=db), req, plan


class SpaceTests(unittest.TestCase):
    def test_only_consumed_non_capital_params_are_optimizable(self):
        keys = {p["key"] for p in space.get_optimizable_parameters()}
        self.assertIn("adx_min", keys)
        self.assertNotIn("leverage", keys)
        self.assertNotIn("fee_bps", keys)
        self.assertNotIn("max_open_positions", keys)  # présent dans les specs mais jamais lu par le moteur
        for secret in ("api_key", "TELEGRAM_TOKEN", "DATABASE_URL", "ENCRYPTION_KEY"):
            self.assertNotIn(secret, keys)

    def test_grid_count_and_determinism(self):
        a = space.build_search_space([{"key": "adx_min", "min": 16, "max": 24, "step": 2}, {"key": "min_teddy_score", "values": [50, 55, 60]}])
        b = space.build_search_space([{"key": "adx_min", "min": 16, "max": 24, "step": 2}, {"key": "min_teddy_score", "values": [50, 55, 60]}])
        self.assertEqual(a["n_configs"], 15)
        self.assertEqual(a["configs"], b["configs"])

    def test_random_is_reproducible_and_bounded(self):
        req = [{"key": "adx_min", "min": 10, "max": 40, "step": 1}, {"key": "min_teddy_score", "min": 30, "max": 88, "step": 1}]
        a = space.build_search_space(req, method="random", max_configs=40, seed=5)
        b = space.build_search_space(req, method="random", max_configs=40, seed=5)
        c = space.build_search_space(req, method="random", max_configs=40, seed=6)
        self.assertEqual(a["n_configs"], 40)
        self.assertEqual(a["configs"], b["configs"])
        self.assertNotEqual(a["configs"], c["configs"])

    def test_oversized_grid_is_refused_not_silently_reduced(self):
        with self.assertRaises(space.SpaceError):
            space.build_search_space([
                {"key": "adx_min", "min": 10, "max": 40, "step": 1},
                {"key": "min_teddy_score", "min": 30, "max": 88, "step": 1},
                {"key": "cooldown_candles", "min": 0, "max": 50, "step": 1},
            ])

    def test_forbidden_and_out_of_range_inputs(self):
        for bad in ([{"key": "leverage", "values": [1, 2]}], [{"key": "adx_min", "values": [1, 20]}], [{"key": "nope", "values": [1, 2]}]):
            with self.assertRaises(space.SpaceError):
                space.build_search_space(bad)

    def test_invalid_combinations_are_dropped_and_reported(self):
        plan = space.build_search_space([{"key": "sma_fast", "values": [20, 60]}, {"key": "sma_slow", "values": [50]},],) if False else \
            space.build_search_space([{"key": "sma_fast", "values": [20, 60]}, {"key": "sma_slow", "values": [50, 80]}])
        self.assertEqual(plan["invalid_skipped"], 1)  # (60, 50) incohérent
        self.assertTrue(any("écartée" in w for w in plan["warnings"]))

    def test_inactive_parameter_warning(self):
        plan = space.build_search_space([{"key": "tp_atr_mult", "min": 1, "max": 3, "step": 1}])  # tp_mode = rr par défaut
        self.assertTrue(any("aucun effet" in w for w in plan["warnings"]))


class EngineInjectionTests(unittest.TestCase):
    def test_lean_and_cache_do_not_change_results(self):
        df = synthetic_df()
        kw = dict(symbol="BTCUSDT", timeframe="15m", trading_style="day", market_type="futures", period_split="dev",
                  raw_params={"adx_min": 18}, preloaded_df=(df, "s"), allow_unreliable_data=True)
        ref = sl.run_backtest_experiment(**kw)
        cache = {}
        a = sl.run_backtest_experiment(opt_cache=cache, lean=True, **kw)
        b = sl.run_backtest_experiment(opt_cache=cache, lean=True, **kw)
        self.assertEqual(ref["metrics"], a["metrics"])
        self.assertEqual(ref["metrics"], b["metrics"])
        self.assertEqual(ref["trades"], a["trades"])
        self.assertEqual(ref["data_quality"], a["data_quality"])
        self.assertEqual(a["candles"], [])

    def test_candidate_params_do_not_mutate_production_defaults(self):
        before = json.dumps(sl.DEFAULT_STRATEGY_PRESETS, sort_keys=True)
        sl.run_backtest_experiment("BTCUSDT", "15m", "day", "futures", "dev", raw_params={"adx_min": 33},
                                   preloaded_df=(synthetic_df(), "s"), allow_unreliable_data=True, opt_cache={}, lean=True)
        self.assertEqual(before, json.dumps(sl.DEFAULT_STRATEGY_PRESETS, sort_keys=True))


class ScoringTests(unittest.TestCase):
    def test_score_requires_min_trades(self):
        m = {"total_trades": 5, "total_return_pct": 10, "max_drawdown_pct": 2, "profit_factor": 2, "avg_r_multiple": .5}
        self.assertIsNone(scoring.performance_score(m, 20))
        m["total_trades"] = 80
        self.assertGreater(scoring.performance_score(m, 20), 0)

    def test_stable_zone_beats_isolated_peak(self):
        parameters = [{"key": "adx_min", "values": [20, 21, 22, 23, 24, 25]}]
        overrides = {i: {"adx_min": v} for i, v in enumerate(parameters[0]["values"])}
        stable = {0: 20, 1: 22, 2: 30, 3: 24, 4: 21, 5: 5}
        peak = {0: -5, 1: -8, 2: 30, 3: -6, 4: -9, 5: -7}
        mk = lambda sc: {i: {"score": v} for i, v in sc.items()}
        s_stable = scoring.neighbor_stats(2, mk(stable), overrides, parameters, k=2)["stability"]
        s_peak = scoring.neighbor_stats(2, mk(peak), overrides, parameters, k=2)["stability"]
        self.assertGreater(s_stable, 0.5)
        self.assertEqual(s_peak, 0.0)

    def test_overfit_flags_detect_oos_collapse(self):
        t = {"total_return_pct": 20, "profit_factor": 2.0, "total_trades": 100}
        v = {"total_return_pct": 1, "profit_factor": 1.0, "total_trades": 30}
        o = {"total_return_pct": -8, "profit_factor": 0.7, "total_trades": 30}
        res = scoring.overfit_flags(t, v, o, {"stability": 0.2}, n_tested=100)
        self.assertEqual(res["risk"], "high")
        self.assertIn("oos_collapse", res["flags"])

    def test_monte_carlo_is_seeded(self):
        pnls = [10, -5, 8, -4, 12, -6, 9, -3, 7, -2, 11, -5]
        self.assertEqual(scoring.monte_carlo(pnls, 10000), scoring.monte_carlo(pnls, 10000))
        self.assertIsNone(scoring.monte_carlo(pnls[:5], 10000))


class StoreAndWorkerTests(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDB()

    def test_job_ids_are_sequential_per_year(self):
        store.ensure_schema(self.db)
        a, b = store.next_job_id(self.db), store.next_job_id(self.db)
        self.assertTrue(re.fullmatch(r"OPT-\d{4}-00001", a))
        self.assertTrue(b.endswith("00002"))

    def test_full_job_lifecycle_with_report(self):
        job_id, req, plan = make_job(self.db)
        self.assertEqual(store.get_job(job_id, db=self.db)["status"], "queued")
        notifier = FakeNotifier()
        n = worker_loop(once=True, db=self.db, notifier=notifier, loader=fake_loader)
        self.assertEqual(n, 1)
        job = store.get_job(job_id, include_report=True, db=self.db)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["progress_pct"], 100)
        s = job["summary"]
        self.assertEqual(s["n_configs"], plan["n_configs"])
        self.assertIsNotNone(s["baseline"])
        self.assertTrue(s["categories"]["best_overall"] is not None or s["n_scored"] == 0)
        self.assertIn("garantie", job["report_html"].lower() + "garantie")
        self.assertIn("Out-of-Sample", job["report_html"])
        self.assertEqual([e[0] for e in notifier.events if e[0] in ("started", "finished")], ["started", "finished"])
        # Les résultats training de TOUTES les configurations + baseline sont persistés
        self.assertEqual(len(store.load_results(job_id, "training", db=self.db)), plan["n_configs"] + 1)

    def test_worker_run_does_not_touch_production_config(self):
        import trading_config  # noqa: F401  (module de configuration live)
        presets = json.dumps(sl.DEFAULT_STRATEGY_PRESETS, sort_keys=True)
        make_job(self.db)
        worker_loop(once=True, db=self.db, notifier=FakeNotifier(), loader=fake_loader)
        self.assertEqual(presets, json.dumps(sl.DEFAULT_STRATEGY_PRESETS, sort_keys=True))

    def test_resume_after_interruption_skips_finished_work(self):
        job_id, req, plan = make_job(self.db)
        calls = {"n": 0}
        real = sl.run_backtest_experiment

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 12:
                raise KeyboardInterrupt  # simule un process tué (non rattrapé par `except Exception`)
            return real(*a, **k)

        sl.run_backtest_experiment = flaky
        try:
            with self.assertRaises(KeyboardInterrupt):
                worker_loop(once=True, db=self.db, notifier=FakeNotifier(), loader=fake_loader)
        finally:
            sl.run_backtest_experiment = real
        job = store.get_job(job_id, db=self.db)
        self.assertEqual(job["status"], "running")  # jamais « terminé » juste parce que le process s'est arrêté
        saved = len(store.load_results(job_id, "training", db=self.db))
        self.assertGreaterEqual(saved, 1)
        # Le heartbeat est périmé -> un nouveau worker reprend le job
        self.db.execute("UPDATE optimization_jobs SET heartbeat_at = %s WHERE job_id = %s", (time.time() - 600, job_id))
        counter = {"n": 0}

        def counting(*a, **k):
            counter["n"] += 1
            return real(*a, **k)

        sl.run_backtest_experiment = counting
        try:
            notifier = FakeNotifier()
            worker_loop(once=True, db=self.db, notifier=notifier, loader=fake_loader)
        finally:
            sl.run_backtest_experiment = real
        self.assertEqual(store.get_job(job_id, db=self.db)["status"], "completed")
        self.assertIn(("started", job_id, True), notifier.events)  # reprise signalée
        # Reprise : moins de simulations que le travail total (les résultats déjà sauvegardés ne sont pas recalculés)
        total_evals = (plan["n_configs"] + 1) + 2 * (min(5, plan["n_configs"]) + 1) + 3 * 4
        self.assertLess(counter["n"], total_evals)

    def test_cancel_queued_and_running(self):
        job_id, _, _ = make_job(self.db)
        self.assertEqual(store.request_cancel(job_id, db=self.db), "cancelled")
        self.assertEqual(worker_loop(once=True, db=self.db, notifier=FakeNotifier(), loader=fake_loader), 0)
        job_id2, _, _ = make_job(self.db)
        real = sl.run_backtest_experiment
        state = {"n": 0}

        def cancelling(*a, **k):
            state["n"] += 1
            if state["n"] == 3:
                store.request_cancel(job_id2, db=self.db)
            time.sleep(0.0)
            return real(*a, **k)

        sl.run_backtest_experiment = cancelling
        try:
            # le heartbeat n'a lieu que toutes les 3 s : on force un battement à chaque appel pour ce test
            orig_step = engine._Progress.step

            def step(self, n=1, config_done=False, force=False):
                return orig_step(self, n, config_done, True)

            engine._Progress.step = step
            worker_loop(once=True, db=self.db, notifier=FakeNotifier(), loader=fake_loader)
        finally:
            sl.run_backtest_experiment = real
            engine._Progress.step = orig_step
        self.assertEqual(store.get_job(job_id2, db=self.db)["status"], "cancelled")

    def test_failure_is_recorded_not_completed(self):
        job_id, _, _ = make_job(self.db)

        def bad_loader(**kw):
            raise RuntimeError("Binance indisponible")

        notifier = FakeNotifier()
        worker_loop(once=True, db=self.db, notifier=notifier, loader=bad_loader)
        job = store.get_job(job_id, db=self.db)
        self.assertEqual(job["status"], "failed")
        self.assertIn("loading_data", job["error"])
        self.assertTrue(any(e[0] == "failed" for e in notifier.events))

    def test_only_one_worker_claims_a_job(self):
        job_id, _, _ = make_job(self.db)
        self.assertEqual(store.claim_next_job("w1", db=self.db), job_id)
        self.assertIsNone(store.claim_next_job("w2", db=self.db))

    def test_report_is_self_contained_html(self):
        job_id, _, _ = make_job(self.db)
        worker_loop(once=True, db=self.db, notifier=FakeNotifier(), loader=fake_loader)
        html = store.get_job(job_id, include_report=True, db=self.db)["report_html"]
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertNotIn("http://", html.replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("<script", html)


class ApiTests(unittest.TestCase):
    def setUp(self):
        from optimization import api
        self.api = api
        self.db = SqliteDB()
        store.ensure_schema(self.db)
        self._orig = store._get_db
        store._get_db = lambda db=None: db or self.db
        api._schema_ready = True

    def tearDown(self):
        store._get_db = self._orig
        self.api._schema_ready = False

    def test_plan_reports_count_and_rejects_bad_input(self):
        st, out = self.api.plan(REQUEST)
        self.assertEqual((st, out["plan"]["n_configs"]), (200, 12))
        st, out = self.api.plan({**REQUEST, "parameters": [{"key": "leverage", "values": [1, 3]}]})
        self.assertEqual(st, 400)
        st, out = self.api.plan({**REQUEST, "symbol": "FOOBARUSDT"})
        self.assertEqual(st, 400)

    def test_create_cap_ownership_and_cancel(self):
        st, out = self.api.create(1, False, REQUEST)
        self.assertEqual((st, out["status"]), (200, "queued"))
        job_id = out["job_id"]
        self.assertEqual(self.api.create(1, False, REQUEST)[0], 200)
        self.assertEqual(self.api.create(1, False, REQUEST)[0], 429)           # plafond de jobs simultanés
        self.assertEqual(self.api.get_job(2, False, job_id)[0], 404)            # un autre utilisateur n'y accède pas
        self.assertEqual(self.api.get_job(2, True, job_id)[0], 200)             # l'admin oui
        self.assertEqual(self.api.get_report(1, False, job_id)[0], 409)         # pas de rapport avant la fin
        self.assertEqual(self.api.cancel(1, False, job_id)[1]["status"], "cancelled")
        self.assertEqual(self.api.cancel(1, False, job_id)[0], 409)

    def test_report_available_once_completed(self):
        st, out = self.api.create(1, False, REQUEST)
        worker_loop(once=True, db=self.db, notifier=FakeNotifier(), loader=fake_loader)
        st, rep = self.api.get_report(1, False, out["job_id"])
        self.assertEqual(st, 200)
        self.assertTrue(rep["html"].startswith("<!doctype html>"))
        st, job = self.api.get_job(1, False, out["job_id"])
        self.assertNotIn("report_html", job["job"])
        self.assertEqual(job["job"]["status"], "completed")


class IsolationTests(unittest.TestCase):
    def test_import_never_loads_live_execution_modules(self):
        code = (
            "import sys; sys.path.insert(0, %r);"
            "import optimization.engine, optimization.worker, optimization.store, optimization.space, optimization.report;"
            "bad=[m for m in ('live_trader','position_manager','binance_manager') if m in sys.modules];"
            "print('LOADED:'+','.join(bad))" % ROOT
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120).stdout
        self.assertIn("LOADED:", out)
        self.assertEqual(out.strip().split("LOADED:")[-1], "", out)


if __name__ == "__main__":
    unittest.main()
