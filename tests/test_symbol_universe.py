"""
Tests de l'univers de symboles étendu (BTC, ETH, SOL, XRP, DOGE, ADA, LINK, SUI, BNB, ZEC + XAU).

Exécution : python -m unittest tests.test_symbol_universe   (ou pytest)
Les dépendances externes absentes de l'environnement (python-binance, websocket-client) sont remplacées par des
doublures UNIQUEMENT si elles ne sont pas installées ; aucun appel réseau ni base PostgreSQL n'est effectué ici.
"""
import importlib
import os
import re
import sys
import types
import unittest
from unittest import mock

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
from config import (  # noqa: E402
    BINANCE_CRYPTO_SYMBOLS,
    DOCUMENTED_SYMBOLS,
    DOCUMENTED_SYMBOLS_SQL,
    LEGACY_FALLBACK_SYMBOLS,
    SYMBOL_CONFIGS,
)
from utils import normalize_symbol  # noqa: E402

NEW_SYMBOLS = ("SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "SUIUSDT", "BNBUSDT", "ZECUSDT")
EXPECTED_CRYPTO = ("BTCUSDT", "ETHUSDT") + NEW_SYMBOLS

# Valeurs historiques gelées : toute modification des seuils BTC/ETH/XAU doit faire échouer ce test.
FROZEN_LEGACY_CONFIGS = {
    "BTCUSDT": {"adx_min": 22, "rsi_buy_low": 48, "rsi_buy_high": 66, "rsi_sell_low": 34, "rsi_sell_high": 52, "atr_max_pct": 4.5, "min_cond": 4},
    "ETHUSDT": {"adx_min": 22, "rsi_buy_low": 48, "rsi_buy_high": 66, "rsi_sell_low": 34, "rsi_sell_high": 52, "atr_max_pct": 4.8, "min_cond": 4},
    "XAUUSDT": {"adx_min": 22, "rsi_buy_low": 48, "rsi_buy_high": 66, "rsi_sell_low": 34, "rsi_sell_high": 52, "atr_max_pct": 2.5, "min_cond": 4},
}


def _install_stubs_if_missing():
    """Doublures minimales pour python-binance / websocket-client si non installés (tests hors réseau)."""
    try:
        import binance  # noqa: F401
    except ImportError:
        binance = types.ModuleType("binance")
        client_mod = types.ModuleType("binance.client")
        exc_mod = types.ModuleType("binance.exceptions")

        class _Client:  # pragma: no cover - simple placeholder
            def __init__(self, *a, **k):
                pass

        class BinanceAPIException(Exception):
            pass

        class BinanceOrderException(Exception):
            pass

        client_mod.Client = _Client
        exc_mod.BinanceAPIException = BinanceAPIException
        exc_mod.BinanceOrderException = BinanceOrderException
        binance.client = client_mod
        binance.exceptions = exc_mod
        sys.modules.update({"binance": binance, "binance.client": client_mod, "binance.exceptions": exc_mod})
    try:
        import websocket  # noqa: F401
    except ImportError:
        sys.modules["websocket"] = mock.MagicMock()


def _synthetic_ohlcv(n=320, start=1.0, drift=0.0006, seed=7):
    """Bougies horaires synthétiques (tendance + bruit) avec volume : aucune donnée de marché réelle."""
    rng = np.random.default_rng(seed)
    rets = drift + rng.normal(0, 0.004, n)
    close = start * np.exp(np.cumsum(rets))
    open_ = np.concatenate(([close[0]], close[:-1]))
    spread = np.abs(rng.normal(0, 0.003, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    vol = rng.uniform(900, 1500, n)
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=2), periods=n, freq="h")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=idx)


class UniverseConfigTests(unittest.TestCase):
    def test_ten_crypto_symbols_plus_gold_are_loaded(self):
        self.assertEqual(tuple(BINANCE_CRYPTO_SYMBOLS), EXPECTED_CRYPTO)
        self.assertEqual(tuple(DOCUMENTED_SYMBOLS), EXPECTED_CRYPTO + ("XAUUSDT",))
        self.assertEqual(len(set(DOCUMENTED_SYMBOLS)), len(DOCUMENTED_SYMBOLS), "doublons dans l'univers")
        self.assertTrue(set(BINANCE_CRYPTO_SYMBOLS) <= set(DOCUMENTED_SYMBOLS))

    def test_every_symbol_has_complete_valid_defaults(self):
        required = {"adx_min", "rsi_buy_low", "rsi_buy_high", "rsi_sell_low", "rsi_sell_high", "atr_max_pct", "min_cond"}
        for sym in DOCUMENTED_SYMBOLS:
            cfg = SYMBOL_CONFIGS[sym]
            self.assertTrue(required <= set(cfg), f"{sym}: clés manquantes {required - set(cfg)}")
            self.assertGreater(cfg["adx_min"], 0, sym)
            self.assertLess(cfg["rsi_buy_low"], cfg["rsi_buy_high"], sym)
            self.assertLess(cfg["rsi_sell_low"], cfg["rsi_sell_high"], sym)
            self.assertTrue(0 <= cfg["rsi_buy_low"] and cfg["rsi_buy_high"] <= 100, sym)
            self.assertTrue(0 <= cfg["rsi_sell_low"] and cfg["rsi_sell_high"] <= 100, sym)
            self.assertGreater(cfg["atr_max_pct"], 0, sym)
            self.assertTrue(1 <= cfg["min_cond"] <= 5, sym)

    def test_legacy_btc_eth_xau_thresholds_are_unchanged(self):
        for sym, expected in FROZEN_LEGACY_CONFIGS.items():
            self.assertEqual(SYMBOL_CONFIGS[sym], expected, f"seuils {sym} modifiés")

    def test_new_symbols_do_not_lower_global_thresholds(self):
        """Aucun nouveau symbole ne peut être plus permissif que la stratégie globale existante (ADX, RSI, conditions)."""
        base = FROZEN_LEGACY_CONFIGS["BTCUSDT"]
        for sym in NEW_SYMBOLS:
            cfg = SYMBOL_CONFIGS[sym]
            self.assertGreaterEqual(cfg["adx_min"], base["adx_min"], sym)
            self.assertGreaterEqual(cfg["min_cond"], base["min_cond"], sym)
            self.assertEqual(
                (cfg["rsi_buy_low"], cfg["rsi_buy_high"], cfg["rsi_sell_low"], cfg["rsi_sell_high"]),
                (base["rsi_buy_low"], base["rsi_buy_high"], base["rsi_sell_low"], base["rsi_sell_high"]),
                sym,
            )

    def test_sql_fragment_covers_whole_universe(self):
        listed = set(re.findall(r"'([A-Z0-9]+)'", DOCUMENTED_SYMBOLS_SQL))
        self.assertEqual(listed, set(DOCUMENTED_SYMBOLS))

    def test_no_runtime_module_keeps_a_hardcoded_three_symbol_sql_list(self):
        """Une liste SQL ('BTCUSDT','ETHUSDT','XAUUSDT') en dur purgerait les données des nouveaux symboles."""
        offenders = []
        for name in ("execution_engine.py", "history_manager.py", "alert_manager.py", "user_manager.py", "web_api_server.py"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
                text = fh.read()
            if re.search(r"\(\s*'BTCUSDT'\s*,\s*'ETHUSDT'\s*,\s*'XAUUSDT'\s*\)", text):
                offenders.append(name)
        self.assertEqual(offenders, [])

    def test_new_symbols_are_not_in_legacy_fallback_set(self):
        self.assertTrue(LEGACY_FALLBACK_SYMBOLS <= {"BTCUSDT", "ETHUSDT", "XAUUSDT"})
        for sym in NEW_SYMBOLS:
            self.assertNotIn(sym, LEGACY_FALLBACK_SYMBOLS)


class DocsAndUiConsistencyTests(unittest.TestCase):
    @staticmethod
    def _read(rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_readme_lists_every_documented_symbol_and_no_stale_count(self):
        readme = self._read("README.md")
        for sym in DOCUMENTED_SYMBOLS:
            self.assertIn(f"`{sym}`", readme, f"README: {sym} absent")
        self.assertNotIn("3 instruments officiels", readme)
        self.assertNotIn("4 / 6", readme)

    def test_xauusdt_is_flagged_unavailable_and_every_click_site_is_guarded(self):
        avail = self._read("src/symbolAvailability.ts")
        self.assertRegex(avail, r"UNAVAILABLE_SYMBOLS[^=]*=\s*new Set\(\[\s*'XAUUSDT'\s*\]\)")
        app = self._read("src/App.tsx")
        self.assertGreaterEqual(app.count("guardSymbol("), 8)  # 8 points d'entrée (clics et sélections)
        self.assertIn("isSymbolUnavailable", self._read("src/components/StrategyLabView.tsx"))

    def test_demo_and_default_watchlists_do_not_offer_the_unavailable_symbol(self):
        web = self._read("web_api_server.py")
        demo_line = [ln for ln in web.splitlines() if ln.startswith("DEMO_SYMBOLS")][0]
        demo_values = demo_line.split("#", 1)[0]  # on ignore le commentaire de fin de ligne
        self.assertNotIn("XAUUSDT", demo_values)
        self.assertNotIn('("BTCUSDT", "ETHUSDT", "XAUUSDT")', web)
        self.assertNotIn("XAUUSDT", self._read("src/components/DemoMode.tsx"))
        self.assertNotIn("XAUUSDT", self._read("src/components/BeginnerPath.tsx"))


class NormalizationTests(unittest.TestCase):
    def test_all_documented_symbols_and_short_tickers_resolve(self):
        for sym in DOCUMENTED_SYMBOLS:
            self.assertEqual(normalize_symbol(sym), sym)
            self.assertEqual(normalize_symbol(sym.lower()), sym)
        for sym in BINANCE_CRYPTO_SYMBOLS:
            self.assertEqual(normalize_symbol(sym[:-4]), sym)
            self.assertEqual(normalize_symbol(f"{sym[:-4]}/USDT"), sym)

    def test_undocumented_symbols_are_still_rejected(self):
        for raw in ("PEPEUSDT", "AVAXUSDT", "MOCAUSDT", "PAXGUSDT"):
            with self.assertRaises(ValueError):
                normalize_symbol(raw)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from signal_engine import SignalEngine

        cls.engine = SignalEngine

    def test_asset_profile_is_crypto_for_every_binance_crypto_symbol(self):
        for sym in BINANCE_CRYPTO_SYMBOLS:
            self.assertEqual(self.engine._asset_profile(sym)[0], "crypto", sym)
        self.assertEqual(self.engine._asset_profile("XAUUSDT")[0], "metal")

    def test_btc_eth_profile_parameters_unchanged(self):
        for sym in ("BTCUSDT", "ETHUSDT"):
            cls_name, rules = self.engine._asset_profile(sym)
            self.assertEqual(cls_name, "crypto")
            self.assertEqual(rules["min_sl_pct"], 0.0060)
            self.assertEqual(rules["atr_min_pct"], 0.0025)
            self.assertEqual(rules["pullback_pct"], 0.025)

    def test_analysis_runs_for_every_symbol_without_assuming_btc_or_eth(self):
        """Prix de départ très différents (de 0,1 à 600) : aucun calcul ne doit supposer un niveau de prix BTC/ETH."""
        starts = {"BTCUSDT": 60000, "ETHUSDT": 3000, "SOLUSDT": 150, "XRPUSDT": 0.6, "DOGEUSDT": 0.12,
                  "ADAUSDT": 0.45, "LINKUSDT": 14, "SUIUSDT": 1.8, "BNBUSDT": 600, "ZECUSDT": 45}
        for sym in BINANCE_CRYPTO_SYMBOLS:
            df = _synthetic_ohlcv(start=starts[sym])
            htf = {"1h": df, "4h": df.iloc[::4].copy(), "1d": df.iloc[::24].copy()}
            res = self.engine.analyze(df, "fr", symbol=sym, style="day", htf_data=htf, timeframe_minutes=60.0)
            self.assertIn(res["signal"], ("BUY", "SELL", "WAIT"), sym)
            self.assertNotIn("non documenté", str(res.get("reason", "")), sym)
            self.assertNotIn("non documenté", str(res.get("rejection_reason", "")), sym)
            price = res["indicators"].get("price")
            self.assertAlmostEqual(price, float(df["Close"].iloc[-1]), places=6, msg=sym)

    def test_missing_or_insufficient_data_returns_wait_not_crash(self):
        for sym in NEW_SYMBOLS:
            self.assertEqual(self.engine.analyze(None, "fr", symbol=sym)["signal"], "WAIT", sym)
            tiny = _synthetic_ohlcv(n=5)
            self.assertEqual(self.engine.analyze(tiny, "fr", symbol=sym)["signal"], "WAIT", sym)

    def test_unknown_symbol_is_refused_by_the_engine(self):
        res = self.engine.analyze(_synthetic_ohlcv(), "fr", symbol="PEPEUSDT")
        self.assertEqual(res["signal"], "WAIT")


class BinanceFiltersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stubs_if_missing()
        cls.bm = importlib.import_module("binance_manager")

    def _offline(self):
        """Simule exchangeInfo injoignable (miroirs publics + client authentifié)."""
        client = mock.MagicMock()
        client.futures_exchange_info.side_effect = RuntimeError("offline")
        client.get_exchange_info.side_effect = RuntimeError("offline")
        return client, mock.patch.object(self.bm.requests, "get", side_effect=RuntimeError("offline"))

    def test_new_symbols_refuse_orders_instead_of_guessing_precision(self):
        client, patcher = self._offline()
        with patcher:
            for sym in NEW_SYMBOLS:
                with self.assertRaises(self.bm.BinanceClientError, msg=sym):
                    self.bm.get_symbol_filters(client, sym, "futures")

    def test_legacy_symbols_keep_their_historical_fallback(self):
        client, patcher = self._offline()
        with patcher:
            btc = self.bm.get_symbol_filters(client, "BTCUSDT", "futures")
            eth = self.bm.get_symbol_filters(client, "ETHUSDT", "futures")
        self.assertEqual(btc["PRICE_FILTER"]["tickSize"], "0.10")
        self.assertEqual(eth["PRICE_FILTER"]["tickSize"], "0.01")

    def test_precision_is_read_from_binance_when_available(self):
        """Les filtres viennent d'exchangeInfo (tick fin de DOGE), jamais d'une valeur codée en dur."""
        payload = {"symbols": [{"symbol": "DOGEUSDT", "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.00001"},
            {"filterType": "LOT_SIZE", "stepSize": "1", "minQty": "1"},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ]}]}
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = payload
        with mock.patch.object(self.bm.requests, "get", return_value=resp):
            filters = self.bm.get_symbol_filters(mock.MagicMock(), "DOGEUSDT", "futures")
        self.assertEqual(filters["PRICE_FILTER"]["tickSize"], "0.00001")
        self.assertEqual(filters["LOT_SIZE"]["stepSize"], "1")


class KlinesCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stubs_if_missing()
        cls.bm = importlib.import_module("binance_manager")

    def setUp(self):
        self.bm._KLINES_CACHE.clear()

    @staticmethod
    def _rows(n=60):
        return [[1700000000000 + i * 3600000, "1", "2", "0.5", "1.5", "100", 0, 0, 0, 0, 0, 0] for i in range(n)]

    def test_repeated_reads_cost_one_request_and_return_independent_copies(self):
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = self._rows()
        with mock.patch.object(self.bm.requests, "get", return_value=resp) as getter:
            a = self.bm.get_klines_dataframe("DOGEUSDT", "1h", "spot", 500)
            a.iloc[-1, a.columns.get_loc("Close")] = 999.0  # l'appelant modifie sa copie (synchro prix live)
            b = self.bm.get_klines_dataframe("DOGEUSDT", "1h", "spot", 500)
        self.assertEqual(getter.call_count, 1)
        self.assertNotEqual(float(b["Close"].iloc[-1]), 999.0, "le cache ne doit jamais être corrompu par l'appelant")

    def test_failures_are_not_cached_and_symbols_are_isolated(self):
        client = mock.MagicMock()
        client.get_klines.side_effect = RuntimeError("offline")
        with mock.patch.object(self.bm.requests, "get", side_effect=RuntimeError("offline")), \
                mock.patch.object(self.bm, "_public_client", return_value=client):
            self.assertIsNone(self.bm.get_klines_dataframe("SUIUSDT", "1h", "spot", 500))
        self.assertEqual(self.bm._KLINES_CACHE, {})
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = self._rows()
        with mock.patch.object(self.bm.requests, "get", return_value=resp):
            self.assertIsNotNone(self.bm.get_klines_dataframe("SOLUSDT", "1h", "spot", 500))


class DataFetcherBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stubs_if_missing()
        cls.df_mod = importlib.import_module("data_fetcher")

    def _fetcher(self):
        return self.df_mod.DataFetcher()

    def _book(self, symbols):
        return [{"symbol": s, "bidPrice": "1.00", "askPrice": "1.02"} for s in symbols]

    def test_ten_symbols_cost_a_single_request_and_are_cached(self):
        fetcher = self._fetcher()
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = self._book(BINANCE_CRYPTO_SYMBOLS)
        with mock.patch.object(self.df_mod.requests, "get", return_value=resp) as getter:
            first = fetcher.get_binance_prices_batch(list(DOCUMENTED_SYMBOLS))
            second = fetcher.get_binance_prices_batch(list(DOCUMENTED_SYMBOLS))
        self.assertEqual(set(first), set(BINANCE_CRYPTO_SYMBOLS))  # l'or (Futures uniquement) n'est pas dans le lot Spot
        self.assertEqual(first, second)
        self.assertEqual(getter.call_count, 1, "10 symboles doivent coûter 1 requête, puis 0 pendant le micro-cache")
        self.assertAlmostEqual(first["DOGEUSDT"]["price"], 1.01)

    def test_batch_failure_returns_empty_without_raising(self):
        fetcher = self._fetcher()
        with mock.patch.object(self.df_mod.requests, "get", side_effect=RuntimeError("offline")):
            self.assertEqual(fetcher.get_binance_prices_batch(list(BINANCE_CRYPTO_SYMBOLS)), {})

    def test_one_missing_symbol_does_not_hide_the_others(self):
        fetcher = self._fetcher()
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = self._book([s for s in BINANCE_CRYPTO_SYMBOLS if s != "ZECUSDT"])
        with mock.patch.object(self.df_mod.requests, "get", return_value=resp):
            out = fetcher.get_binance_prices_batch(list(BINANCE_CRYPTO_SYMBOLS))
        self.assertNotIn("ZECUSDT", out)
        self.assertEqual(len(out), len(BINANCE_CRYPTO_SYMBOLS) - 1)


class SafeGuardsTests(unittest.TestCase):
    def test_execution_scan_universe_matches_config(self):
        _install_stubs_if_missing()
        try:
            ex = importlib.import_module("execution_engine")
        except Exception as exc:  # dépendances d'exécution (telegram, psycopg2...) absentes de cet environnement
            self.skipTest(f"execution_engine non importable ici: {exc}")
        self.assertEqual(set(ex.ALLOWED_DOCUMENTED_SYMBOLS_SET), set(DOCUMENTED_SYMBOLS))
        self.assertEqual(ex.DEFAULT_PERIODIC_SCAN_SYMBOLS, list(DOCUMENTED_SYMBOLS))

    def test_scan_loop_isolates_symbol_errors(self):
        """Le scan périodique entoure chaque symbole d'un try/except qui ne relance pas : un échec n'arrête pas les autres."""
        import ast

        with open(os.path.join(ROOT, "execution_engine.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        loops = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "symbol"
            and isinstance(n.iter, ast.Name) and n.iter.id == "symbols"
        ]
        self.assertTrue(loops, "boucle de scan introuvable")
        protected = []
        for loop in loops:
            for node in loop.body:
                if isinstance(node, ast.Try) and node.handlers:
                    reraises = any(isinstance(x, ast.Raise) for h in node.handlers for x in ast.walk(h))
                    protected.append(not reraises)
        self.assertTrue(protected and all(protected), "chaque symbole doit être isolé par un try/except sans re-raise")

    def test_no_fallback_candles_for_new_symbols(self):
        """Pas de bougies BTC/synthétiques étiquetées DOGE & co : la fonction de repli renvoie None => signal WAIT."""
        src_path = os.path.join(ROOT, "web_api_server.py")
        with open(src_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("if sym_clean not in LEGACY_FALLBACK_SYMBOLS:", text)
        guard = text[text.index("def _load_fallback_csv"): text.index("def _load_fallback_csv") + 900]
        self.assertIn("return None", guard)


if __name__ == "__main__":
    unittest.main()
