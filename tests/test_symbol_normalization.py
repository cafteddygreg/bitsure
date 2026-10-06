"""
tests/test_symbol_normalization.py
------------------------------------
Unit tests for the canonical normalize_symbol() function in utils.py.
These act as the contract specification for symbol normalization across
the entire bot codebase.

Run with:
    python -m pytest tests/test_symbol_normalization.py -v
    or
    python -m unittest tests/test_symbol_normalization.py -v
"""

import contextlib
import os
import re
import sys
import unittest

try:
    import pytest
except ImportError:
    class _PytestStub:
        class mark:
            @staticmethod
            def parametrize(*args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator

        @staticmethod
        def raises(exc_type, match=None):
            @contextlib.contextmanager
            def _ctx():
                try:
                    yield
                except exc_type as e:
                    if match and not re.search(match, str(e)):
                        raise AssertionError(f"{e!r} does not match {match!r}")
                    return
                raise AssertionError(f"{exc_type} not raised")
            return _ctx()

    pytest = _PytestStub()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import normalize_symbol, is_valid_symbol


# ---------------------------------------------------------------------------
# Valid canonical conversions
# ---------------------------------------------------------------------------

VALID_CASES = [
    # Slash separator
    ("BTC/USD",   "BTCUSD"),
    ("ETH/USD",   "ETHUSD"),
    ("BTC/USDT",  "BTCUSDT"),
    ("ETH/USDT",  "ETHUSDT"),
    # Space separator
    ("BTC USD",   "BTCUSD"),
    ("ETH USD",   "ETHUSD"),
    # Dash separator
    ("BTC-USD",   "BTCUSD"),
    ("ETH-USD",   "ETHUSD"),
    # Lowercase
    ("btcusd",    "BTCUSD"),
    ("eth/usd",   "ETHUSD"),
    ("btc/usdt",  "BTCUSDT"),
    # Already canonical — no-op
    ("BTCUSDT",   "BTCUSDT"),
    ("ETHUSDT",   "ETHUSDT"),
    ("BTCUSD",    "BTCUSD"),
    ("ETHUSD",    "ETHUSD"),
    # Dash between base and USDT
    ("ETH-USDT",  "ETHUSDT"),
    ("BTC-USDT",  "BTCUSDT"),
    # Perp / Futures suffixes
    ("btcusdt_perp", "BTCUSDT"),
    # Precious metals / documented pairs
    ("XAU/USD",   "XAUUSD"),
    ("xauusd",    "XAUUSD"),
    # Leading / trailing whitespace
    ("  BTCUSDT  ", "BTCUSDT"),
    ("  btc/usd  ", "BTCUSD"),
]


@pytest.mark.parametrize("raw, expected", VALID_CASES)
def test_normalize_symbol_valid(raw, expected):
    assert normalize_symbol(raw) == expected


# ---------------------------------------------------------------------------
# Invalid or undocumented inputs must raise ValueError
# ---------------------------------------------------------------------------

INVALID_CASES = [
    "",
    "   ",
    "!!!",
    "@#$%",
    "VERYLONGSYMBOLNAME123456",   # >20 chars after strip
    "SOLUSDT",                    # undocumented symbol
    "PAXGUSDT",                   # undocumented symbol
    "MOCAUSDT",                   # undocumented symbol
    "NOTUSDT",                    # undocumented symbol
]


@pytest.mark.parametrize("raw", INVALID_CASES)
def test_normalize_symbol_invalid(raw):
    with pytest.raises(ValueError):
        normalize_symbol(raw)


# ---------------------------------------------------------------------------
# is_valid_symbol — boolean wrapper
# ---------------------------------------------------------------------------

IS_VALID_CASES = [
    ("BTCUSDT",  True),
    ("BTC/USD",  True),
    ("btcusd",   True),
    ("ETH USD",  True),
    ("XAU/USD",  True),
    ("",         False),
    ("!!!",      False),
    ("SOLUSDT",  False),
    ("PAXGUSDT", False),
    ("VERYLONGSYMBOLNAME123456", False),
]


@pytest.mark.parametrize("raw, expected", IS_VALID_CASES)
def test_is_valid_symbol(raw, expected):
    assert is_valid_symbol(raw) == expected


# ---------------------------------------------------------------------------
# normalize_symbol is idempotent on already-canonical documented symbols
# ---------------------------------------------------------------------------

IDEMPOTENT_CASES = [
    "BTCUSDT", "ETHUSDT",
    "BTCUSD", "ETHUSD", "XAUUSD",
]


@pytest.mark.parametrize("symbol", IDEMPOTENT_CASES)
def test_normalize_symbol_idempotent(symbol):
    assert normalize_symbol(normalize_symbol(symbol)) == normalize_symbol(symbol)


class SymbolNormalizationUnitTests(unittest.TestCase):
    def test_valid_conversions(self):
        for raw, expected in VALID_CASES:
            self.assertEqual(normalize_symbol(raw), expected)

    def test_invalid_inputs_raise_value_error(self):
        for raw in INVALID_CASES:
            with self.assertRaises(ValueError):
                normalize_symbol(raw)

    def test_is_valid_symbol_wrapper(self):
        for raw, expected in IS_VALID_CASES:
            self.assertEqual(is_valid_symbol(raw), expected)

    def test_idempotence(self):
        for sym in IDEMPOTENT_CASES:
            self.assertEqual(normalize_symbol(normalize_symbol(sym)), normalize_symbol(sym))


if __name__ == "__main__":
    unittest.main()
