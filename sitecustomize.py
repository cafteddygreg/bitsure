"""
sitecustomize.py
----------------
Provides zero-dependency pure-Python fallbacks for third-party libraries
(numpy, pandas, requests, websocket, binance, telegram, apscheduler, yfinance)
ONLY when those packages are not installed in the system Python environment.
This guarantees that the existing Bitsure Python backend (SignalEngine, indicators,
DataFetcher, PaperTrader, BinanceManager, etc.) runs identically in all environments.
"""

import csv
import datetime as _dt
import json as _json
import math
import sys
import types
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union


def _is_nan(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float):
        return math.isnan(v)
    return False


def _is_inf(v: Any) -> bool:
    if isinstance(v, float):
        return math.isinf(v)
    return False


# =====================================================================
# 1. NUMPY FALLBACK
# =====================================================================
try:
    import numpy  # noqa: F401
except ImportError:
    np_mod = types.ModuleType("numpy")
    np_mod.nan = float("nan")
    np_mod.inf = float("inf")
    np_mod.float64 = float
    np_mod.int64 = int
    np_mod.bool_ = bool
    np_mod.ndarray = list

    def _np_isnan(x):
        if hasattr(x, "_values"):
            from pandas import Series
            return Series([_is_nan(v) for v in x._values], index=x.index)
        if isinstance(x, (list, tuple)):
            return [_is_nan(v) for v in x]
        return _is_nan(x)

    def _np_isinf(x):
        if hasattr(x, "_values"):
            from pandas import Series
            return Series([_is_inf(v) for v in x._values], index=x.index)
        if isinstance(x, (list, tuple)):
            return [_is_inf(v) for v in x]
        return _is_inf(x)

    def _np_where(cond, x, y):
        cond_vals = cond._values if hasattr(cond, "_values") else list(cond)
        n = len(cond_vals)
        x_vals = x._values if hasattr(x, "_values") else (list(x) if isinstance(x, (list, tuple)) else [x] * n)
        y_vals = y._values if hasattr(y, "_values") else (list(y) if isinstance(y, (list, tuple)) else [y] * n)
        return [xv if bool(cv) else yv for cv, xv, yv in zip(cond_vals, x_vals, y_vals)]

    def _np_array(seq, dtype=None):
        vals = list(seq._values if hasattr(seq, "_values") else seq)
        if dtype is float:
            return [float(v) if v is not None else float("nan") for v in vals]
        return vals

    def _to_np_list(x):
        if hasattr(x, "_values"):
            return list(x._values)
        if hasattr(x, "_data"):
            return list(x._data)
        if isinstance(x, (list, tuple)):
            return list(x)
        return [x]

    def _np_maximum(a, b):
        a_list = _to_np_list(a)
        b_list = _to_np_list(b) if isinstance(b, (list, tuple)) or hasattr(b, "_values") else [b] * len(a_list)
        res = [max(float(x), float(y)) for x, y in zip(a_list, b_list)]
        if hasattr(a, "index"):
            from pandas import Series
            return Series(res, index=a.index)
        return res

    def _np_minimum(a, b):
        a_list = _to_np_list(a)
        b_list = _to_np_list(b) if isinstance(b, (list, tuple)) or hasattr(b, "_values") else [b] * len(a_list)
        res = [min(float(x), float(y)) for x, y in zip(a_list, b_list)]
        if hasattr(a, "index"):
            from pandas import Series
            return Series(res, index=a.index)
        return res

    def _np_abs(a):
        if hasattr(a, "abs"):
            return a.abs()
        return [abs(float(x)) for x in _to_np_list(a)]

    np_mod.isnan = _np_isnan
    np_mod.isinf = _np_isinf
    np_mod.where = _np_where
    np_mod.array = _np_array
    np_mod.maximum = _np_maximum
    np_mod.minimum = _np_minimum
    np_mod.abs = _np_abs
    np_mod.arange = lambda n, dtype=float: [float(i) for i in range(int(n))]
    np_mod.sin = lambda arr: [math.sin(float(x)) for x in _to_np_list(arr)]
    np_mod.full = lambda n, val: [float(val) for _ in range(int(n))]
    np_mod.mean = lambda a: sum(a) / len(a) if len(a) else float("nan")
    np_mod.std = lambda a: math.sqrt(sum((x - (sum(a) / len(a))) ** 2 for x in a) / max(len(a) - 1, 1)) if len(a) > 1 else 0.0
    sys.modules["numpy"] = np_mod


# =====================================================================
# 2. PANDAS FALLBACK
# =====================================================================
try:
    import pandas  # noqa: F401
except ImportError:
    pd_mod = types.ModuleType("pandas")

    def _parse_dt(val: Any, unit: Optional[str] = None) -> _dt.datetime:
        if hasattr(val, "_dt") and isinstance(val._dt, _dt.datetime):
            return val._dt
        if isinstance(val, _dt.datetime):
            if val.tzinfo is not None:
                return val.astimezone(_dt.timezone.utc).replace(tzinfo=None)
            return val
        if isinstance(val, _dt.date):
            return _dt.datetime(val.year, val.month, val.day)
        if unit == "ms" or (isinstance(val, (int, float)) and val > 1e10):
            return _dt.datetime.fromtimestamp(float(val) / 1000.0, tz=_dt.timezone.utc).replace(tzinfo=None)
        if unit == "s" or isinstance(val, (int, float)):
            return _dt.datetime.fromtimestamp(float(val), tz=_dt.timezone.utc).replace(tzinfo=None)
        s = str(val).strip()
        if s.endswith("Z"):
            s = s[:-1]
        if "+" in s[10:]:
            s = s[: s.rfind("+")]
        s_clean = s.replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return _dt.datetime.strptime(s_clean[:19], fmt)
            except ValueError:
                continue
        try:
            return _dt.datetime.fromisoformat(s)
        except Exception:
            return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)

    class Timedelta:
        def __init__(self, value: Any = 0, unit: str = "min", **kwargs):
            if isinstance(value, Timedelta):
                self._seconds = float(value._seconds)
            elif isinstance(value, _dt.timedelta):
                self._seconds = float(value.total_seconds())
            elif kwargs:
                self._seconds = float(_dt.timedelta(**kwargs).total_seconds())
            else:
                u = str(unit).lower()
                mult = (
                    60.0 if u in ("m", "min", "minute", "minutes", "t")
                    else (3600.0 if u in ("h", "hour", "hours")
                    else (86400.0 if u in ("d", "day", "days")
                    else (0.001 if u == "ms" else 1.0)))
                )
                self._seconds = float(value) * mult

        def total_seconds(self) -> float:
            return self._seconds

        def _cmp_sec(self, other: Any) -> float:
            if isinstance(other, Timedelta):
                return other._seconds
            if isinstance(other, _dt.timedelta):
                return other.total_seconds()
            return float(other)

        def __gt__(self, other: Any) -> bool:
            return self._seconds > self._cmp_sec(other)

        def __ge__(self, other: Any) -> bool:
            return self._seconds >= self._cmp_sec(other)

        def __lt__(self, other: Any) -> bool:
            return self._seconds < self._cmp_sec(other)

        def __le__(self, other: Any) -> bool:
            return self._seconds <= self._cmp_sec(other)

        def __eq__(self, other: Any) -> bool:  # type: ignore[override]
            try:
                return abs(self._seconds - self._cmp_sec(other)) < 1e-9
            except Exception:
                return False

        def __repr__(self) -> str:
            return f"Timedelta({self._seconds}s)"

    class Timestamp:
        def __init__(self, ts: Any = None, unit: Optional[str] = None, tz: Any = None):
            if isinstance(ts, Timestamp):
                self._dt = ts._dt
            elif ts is None:
                self._dt = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
            else:
                self._dt = _parse_dt(ts, unit=unit)
            self.tz = None
            self.tzinfo = None

        @classmethod
        def utcnow(cls) -> "Timestamp":
            return cls(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))

        @classmethod
        def now(cls, tz: Any = None) -> "Timestamp":
            return cls(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))

        def tz_localize(self, tz: Any = None) -> "Timestamp":
            return self

        def tz_convert(self, tz: Any = None) -> "Timestamp":
            return self

        def strftime(self, fmt: str) -> str:
            return self._dt.strftime(fmt)

        def isoformat(self) -> str:
            return self._dt.isoformat()

        @property
        def year(self) -> int:
            return self._dt.year

        @property
        def month(self) -> int:
            return self._dt.month

        @property
        def day(self) -> int:
            return self._dt.day

        @property
        def hour(self) -> int:
            return self._dt.hour

        @property
        def minute(self) -> int:
            return self._dt.minute

        @property
        def second(self) -> int:
            return self._dt.second

        @property
        def microsecond(self) -> int:
            return self._dt.microsecond

        def replace(self, **kwargs) -> "Timestamp":
            clean_kw = {k: v for k, v in kwargs.items() if k != "tzinfo"}
            return Timestamp(self._dt.replace(**clean_kw))

        def timestamp(self) -> float:
            return self._dt.replace(tzinfo=_dt.timezone.utc).timestamp()

        def _other_dt(self, other: Any) -> _dt.datetime:
            if isinstance(other, Timestamp):
                return other._dt
            if isinstance(other, _dt.datetime):
                return _parse_dt(other)
            return _parse_dt(other)

        def __sub__(self, other: Any):
            if isinstance(other, (Timestamp, _dt.datetime)):
                other_dt = self._other_dt(other)
                return Timedelta((self._dt - other_dt).total_seconds(), unit="s")
            if isinstance(other, Timedelta):
                return Timestamp(self._dt - _dt.timedelta(seconds=other._seconds))
            if isinstance(other, _dt.timedelta):
                return Timestamp(self._dt - other)
            raise TypeError(f"Unsupported subtraction with {type(other)}")

        def __add__(self, other: Any) -> "Timestamp":
            if isinstance(other, Timedelta):
                return Timestamp(self._dt + _dt.timedelta(seconds=other._seconds))
            if isinstance(other, _dt.timedelta):
                return Timestamp(self._dt + other)
            raise TypeError(f"Unsupported addition with {type(other)}")

        def __gt__(self, other: Any) -> bool:
            return self._dt > self._other_dt(other)

        def __ge__(self, other: Any) -> bool:
            return self._dt >= self._other_dt(other)

        def __lt__(self, other: Any) -> bool:
            return self._dt < self._other_dt(other)

        def __le__(self, other: Any) -> bool:
            return self._dt <= self._other_dt(other)

        def __eq__(self, other: Any) -> bool:  # type: ignore[override]
            if not isinstance(other, (Timestamp, _dt.datetime, str)):
                return False
            try:
                return self._dt == self._other_dt(other)
            except Exception:
                return False

        def __hash__(self) -> int:
            return hash(self._dt)

        def __repr__(self) -> str:
            return self._dt.strftime("%Y-%m-%d %H:%M:%S")

        def __str__(self) -> str:
            return self.__repr__()

    class DatetimeIndex(list):
        def __init__(self, seq=()):
            super().__init__(x if isinstance(x, Timestamp) else Timestamp(x) for x in seq)
            self.tz = None
            self.tzinfo = None

        @property
        def is_monotonic_increasing(self) -> bool:
            return all(self[i] <= self[i + 1] for i in range(len(self) - 1))

        def to_series(self) -> "Series":
            return Series(list(self), index=DatetimeIndex(self))

        def difference(self, other) -> "DatetimeIndex":
            s = set(other)
            return DatetimeIndex([x for x in self if x not in s])

        def __getitem__(self, item):
            res = super().__getitem__(item)
            if isinstance(item, slice):
                return DatetimeIndex(res)
            return res

        def __add__(self, other):
            if isinstance(other, (Timedelta, _dt.timedelta)):
                return DatetimeIndex([x + other for x in self])
            return DatetimeIndex(super().__add__(other))

        def __sub__(self, other):
            if isinstance(other, (Timedelta, _dt.timedelta)):
                return DatetimeIndex([x - other for x in self])
            if isinstance(other, (Timestamp, _dt.datetime)):
                return Series([x - other for x in self], index=DatetimeIndex(self))
            raise TypeError(f"Unsupported subtraction on DatetimeIndex: {type(other)}")

        def __le__(self, other):
            if isinstance(other, (DatetimeIndex, Series, list, tuple)):
                return Series([a <= b for a, b in zip(self, other)], index=DatetimeIndex(self), dtype=bool)
            return Series([x <= other for x in self], index=DatetimeIndex(self), dtype=bool)

        def __lt__(self, other):
            if isinstance(other, (DatetimeIndex, Series, list, tuple)):
                return Series([a < b for a, b in zip(self, other)], index=DatetimeIndex(self), dtype=bool)
            return Series([x < other for x in self], index=DatetimeIndex(self), dtype=bool)

        def __ge__(self, other):
            if isinstance(other, (DatetimeIndex, Series, list, tuple)):
                return Series([a >= b for a, b in zip(self, other)], index=DatetimeIndex(self), dtype=bool)
            return Series([x >= other for x in self], index=DatetimeIndex(self), dtype=bool)

        def __gt__(self, other):
            if isinstance(other, (DatetimeIndex, Series, list, tuple)):
                return Series([a > b for a, b in zip(self, other)], index=DatetimeIndex(self), dtype=bool)
            return Series([x > other for x in self], index=DatetimeIndex(self), dtype=bool)

    class _DtAccessor:
        def __init__(self, series: "Series"):
            self._series = series

        def total_seconds(self) -> "Series":
            out = []
            for v in self._series._values:
                if isinstance(v, (Timedelta, _dt.timedelta)):
                    out.append(float(v.total_seconds()))
                elif hasattr(v, "total_seconds"):
                    out.append(float(v.total_seconds()))
                elif isinstance(v, (int, float)) and not _is_nan(v):
                    out.append(float(v))
                else:
                    out.append(float("nan"))
            return Series(out, index=self._series.index, dtype=float)

    class _SeriesIloc:
        def __init__(self, series: "Series"):
            self._s = series

        def __getitem__(self, item):
            if isinstance(item, slice):
                return Series(self._s._values[item], index=self._s._slice_index(item), dtype=self._s.dtype)
            return self._s._values[item]

    class _RollingSeries:
        def __init__(self, series: "Series", window: int, min_periods: Optional[int] = None, center: bool = False):
            self._s = series
            self._w = max(int(window), 1)
            self._mp = int(min_periods) if min_periods is not None else self._w
            self._center = bool(center)

        def _apply(self, fn: Callable[[List[float]], float]) -> "Series":
            vals = self._s._values
            n = len(vals)
            out = []
            half = self._w // 2
            for i in range(n):
                if self._center:
                    start, end = i - half, i + half + 1
                    if start < 0 or end > n:
                        out.append(float("nan"))
                        continue
                    raw_win = vals[start:end]
                else:
                    start = max(0, i - self._w + 1)
                    raw_win = vals[start : i + 1]
                win = [float(x) for x in raw_win if x is not None and not _is_nan(x)]
                if len(win) < self._mp or not win:
                    out.append(float("nan"))
                else:
                    out.append(fn(win))
            return Series(out, index=self._s.index, dtype=float)

        def mean(self) -> "Series":
            return self._apply(lambda w: sum(w) / len(w))

        def min(self) -> "Series":
            return self._apply(lambda w: min(w))

        def max(self) -> "Series":
            return self._apply(lambda w: max(w))

        def std(self) -> "Series":
            def _calc_std(w: List[float]) -> float:
                if len(w) < 2:
                    return float("nan")
                m = sum(w) / len(w)
                return math.sqrt(sum((x - m) ** 2 for x in w) / (len(w) - 1))
            return self._apply(_calc_std)

    class _EwmSeries:
        def __init__(self, series: "Series", span: Optional[float] = None, alpha: Optional[float] = None, min_periods: int = 1, adjust: bool = False):
            self._s = series
            if alpha is not None:
                self._alpha = float(alpha)
            elif span is not None:
                self._alpha = 2.0 / (float(span) + 1.0)
            else:
                self._alpha = 0.5
            self._min_p = int(min_periods or 1)

        def mean(self) -> "Series":
            vals = self._s._values
            out = []
            ema = None
            valid_count = 0
            alpha = self._alpha
            for v in vals:
                if v is None or _is_nan(v):
                    out.append(ema if (ema is not None and valid_count >= self._min_p) else float("nan"))
                    continue
                fv = float(v)
                valid_count += 1
                if ema is None or _is_nan(ema):
                    ema = fv
                else:
                    ema = alpha * fv + (1.0 - alpha) * ema
                out.append(ema if valid_count >= self._min_p else float("nan"))
            return Series(out, index=self._s.index, dtype=float)

    class _SeriesResampler:
        def __init__(self, series: "Series", rule: str, closed: str = "left", label: str = "left"):
            self._df_resampler = _Resampler(DataFrame({"_v": series._values}, index=series.index), rule, closed=closed, label=label)

        def count(self) -> "Series":
            buckets, bucket_order = self._df_resampler._build_buckets()
            return Series([len(buckets[b]["_v"]) for b in bucket_order], index=DatetimeIndex(bucket_order), dtype=float)

    class Series:
        def __init__(self, data=None, index=None, dtype=None):
            if isinstance(data, Series):
                vals = list(data._values)
                if index is None:
                    index = data.index
            elif data is None:
                vals = []
            elif isinstance(data, (list, tuple, DatetimeIndex)):
                vals = list(data)
            else:
                vals = list(data)

            if dtype is float:
                norm_vals = []
                for v in vals:
                    if v is None or (isinstance(v, float) and math.isnan(v)):
                        norm_vals.append(float("nan"))
                    else:
                        try:
                            norm_vals.append(float(v))
                        except Exception:
                            norm_vals.append(float("nan"))
                vals = norm_vals
            elif dtype is bool:
                vals = [bool(v) for v in vals]

            self._values = vals
            self.dtype = dtype
            if index is None:
                self.index = list(range(len(vals)))
            elif isinstance(index, DatetimeIndex) or (isinstance(index, list) and index and isinstance(index[0], (Timestamp, _dt.datetime))):
                self.index = DatetimeIndex(index)
            else:
                self.index = list(index)

        def _slice_index(self, sl: slice):
            sliced = self.index[sl]
            return DatetimeIndex(sliced) if isinstance(self.index, DatetimeIndex) else sliced

        @property
        def iloc(self) -> _SeriesIloc:
            return _SeriesIloc(self)

        @property
        def dt(self) -> _DtAccessor:
            return _DtAccessor(self)

        @property
        def empty(self) -> bool:
            return len(self._values) == 0

        @property
        def values(self) -> list:
            return self._values

        def copy(self) -> "Series":
            idx = DatetimeIndex(self.index) if isinstance(self.index, DatetimeIndex) else list(self.index)
            return Series(list(self._values), index=idx, dtype=self.dtype)

        def __len__(self) -> int:
            return len(self._values)

        def __iter__(self):
            return iter(self._values)

        def __getitem__(self, item):
            if isinstance(item, slice):
                return self.iloc[item]
            if isinstance(item, (Series, list, tuple)):
                mask = item._values if isinstance(item, Series) else list(item)
                if len(mask) == len(self._values) and all(isinstance(x, bool) for x in mask):
                    vals = [v for v, m in zip(self._values, mask) if m]
                    idx = [k for k, m in zip(self.index, mask) if m]
                    new_idx = DatetimeIndex(idx) if isinstance(self.index, DatetimeIndex) else idx
                    return Series(vals, index=new_idx, dtype=self.dtype)
            return self._values[item]

        def astype(self, dtype) -> "Series":
            if dtype is bool:
                return Series([bool(v) for v in self._values], index=self.index, dtype=bool)
            if dtype is int:
                return Series([int(v) if (v is not None and not _is_nan(v)) else 0 for v in self._values], index=self.index, dtype=int)
            return Series(self._values, index=self.index, dtype=dtype)

        def reindex(self, new_index) -> "Series":
            lookup = {k: v for k, v in zip(self.index, self._values)}
            vals = [lookup.get(k, float("nan")) for k in new_index]
            idx = DatetimeIndex(new_index) if isinstance(new_index, DatetimeIndex) else list(new_index)
            return Series(vals, index=idx, dtype=self.dtype)

        def resample(self, rule: str, closed: str = "left", label: str = "left") -> _SeriesResampler:
            return _SeriesResampler(self, rule, closed=closed, label=label)

        def where(self, cond, other=float("nan")) -> "Series":
            c_vals = cond._values if isinstance(cond, Series) else list(cond)
            o_vals = other._values if isinstance(other, Series) else [other] * len(self._values)
            out = [v if bool(c) else o for v, c, o in zip(self._values, c_vals, o_vals)]
            return Series(out, index=self.index, dtype=self.dtype)

        def diff(self, periods: int = 1) -> "Series":
            out = []
            vals = self._values
            for i in range(len(vals)):
                if i < periods:
                    if isinstance(vals[i], (Timestamp, _dt.datetime)):
                        out.append(None)
                    else:
                        out.append(float("nan"))
                else:
                    a, b = vals[i], vals[i - periods]
                    if a is None or b is None or _is_nan(a) or _is_nan(b):
                        out.append(None if isinstance(a, (Timestamp, _dt.datetime)) else float("nan"))
                    else:
                        out.append(a - b)
            return Series(out, index=self.index, dtype=self.dtype)

        def shift(self, periods: int = 1) -> "Series":
            vals = self._values
            n = len(vals)
            if periods <= 0:
                return Series(vals, index=self.index, dtype=self.dtype)
            out = [float("nan")] * min(periods, n) + vals[: max(0, n - periods)]
            return Series(out, index=self.index, dtype=self.dtype)

        def clip(self, lower: Optional[float] = None, upper: Optional[float] = None) -> "Series":
            out = []
            for v in self._values:
                if v is None or _is_nan(v):
                    out.append(float("nan"))
                    continue
                val = float(v)
                if lower is not None and val < lower:
                    val = float(lower)
                if upper is not None and val > upper:
                    val = float(upper)
                out.append(val)
            return Series(out, index=self.index, dtype=float)

        def rolling(self, window: int, min_periods: Optional[int] = None, center: bool = False) -> _RollingSeries:
            return _RollingSeries(self, window=window, min_periods=min_periods, center=center)

        def ewm(self, span: Optional[float] = None, alpha: Optional[float] = None, min_periods: int = 1, adjust: bool = False) -> _EwmSeries:
            return _EwmSeries(self, span=span, alpha=alpha, min_periods=min_periods, adjust=adjust)

        def replace(self, to_replace, value) -> "Series":
            targets = to_replace if isinstance(to_replace, (list, tuple, set)) else [to_replace]
            check_inf = any(_is_inf(t) for t in targets)
            out = []
            for v in self._values:
                matched = False
                if check_inf and _is_inf(v):
                    matched = True
                elif v in targets:
                    matched = True
                out.append(value if matched else v)
            return Series(out, index=self.index, dtype=self.dtype)

        def fillna(self, value) -> "Series":
            out = [value if (v is None or _is_nan(v)) else v for v in self._values]
            return Series(out, index=self.index, dtype=self.dtype)

        def dropna(self) -> "Series":
            vals = []
            idx = []
            for v, k in zip(self._values, self.index):
                if v is not None and not _is_nan(v):
                    vals.append(v)
                    idx.append(k)
            new_idx = DatetimeIndex(idx) if isinstance(self.index, DatetimeIndex) else idx
            return Series(vals, index=new_idx, dtype=self.dtype)

        def abs(self) -> "Series":
            return Series([abs(v) if (v is not None and not _is_nan(v)) else float("nan") for v in self._values], index=self.index, dtype=float)

        def min(self) -> float:
            valid = [float(v) for v in self._values if v is not None and not _is_nan(v)]
            return min(valid) if valid else float("nan")

        def max(self) -> float:
            valid = [float(v) for v in self._values if v is not None and not _is_nan(v)]
            return max(valid) if valid else float("nan")

        def mean(self) -> float:
            valid = [float(v) for v in self._values if v is not None and not _is_nan(v)]
            return sum(valid) / len(valid) if valid else float("nan")

        def sum(self) -> float:
            valid = [float(v) for v in self._values if v is not None and not _is_nan(v)]
            return sum(valid) if valid else 0.0

        def median(self) -> float:
            valid = sorted(
                (v.total_seconds() if isinstance(v, (Timedelta, _dt.timedelta)) else float(v))
                for v in self._values
                if v is not None and not _is_nan(v)
            )
            if not valid:
                return float("nan")
            mid = len(valid) // 2
            if len(valid) % 2 == 1:
                return valid[mid]
            return (valid[mid - 1] + valid[mid]) / 2.0

        def _binop(self, other, op: Callable[[Any, Any], Any], dtype=float) -> "Series":
            if isinstance(other, (Series, DatetimeIndex, list, tuple)):
                other_vals = other._values if isinstance(other, Series) else list(other)
            else:
                other_vals = [other] * len(self._values)
            out = []
            for a, b in zip(self._values, other_vals):
                if a is None or b is None or _is_nan(a) or _is_nan(b):
                    out.append(False if dtype is bool else float("nan"))
                else:
                    try:
                        out.append(op(a, b))
                    except ZeroDivisionError:
                        out.append(float("nan"))
            return Series(out, index=self.index, dtype=dtype)

        def __add__(self, other):
            return self._binop(other, lambda a, b: a + b)

        def __radd__(self, other):
            return self._binop(other, lambda a, b: b + a)

        def __sub__(self, other):
            return self._binop(other, lambda a, b: a - b)

        def __rsub__(self, other):
            return self._binop(other, lambda a, b: b - a)

        def __mul__(self, other):
            return self._binop(other, lambda a, b: a * b)

        def __rmul__(self, other):
            return self._binop(other, lambda a, b: b * a)

        def __truediv__(self, other):
            return self._binop(other, lambda a, b: a / b if b != 0 else float("nan"))

        def __rtruediv__(self, other):
            return self._binop(other, lambda a, b: b / a if a != 0 else float("nan"))

        def __neg__(self):
            return Series([-v if (v is not None and not _is_nan(v)) else float("nan") for v in self._values], index=self.index, dtype=self.dtype)

        def __gt__(self, other):
            return self._binop(other, lambda a, b: a > b, dtype=bool)

        def __ge__(self, other):
            return self._binop(other, lambda a, b: a >= b, dtype=bool)

        def __lt__(self, other):
            return self._binop(other, lambda a, b: a < b, dtype=bool)

        def __le__(self, other):
            return self._binop(other, lambda a, b: a <= b, dtype=bool)

        def __eq__(self, other):  # type: ignore[override]
            return self._binop(other, lambda a, b: a == b, dtype=bool)

        def __and__(self, other):
            return self._binop(other, lambda a, b: bool(a) and bool(b), dtype=bool)

        def __rand__(self, other):
            return self._binop(other, lambda a, b: bool(b) and bool(a), dtype=bool)

        def __or__(self, other):
            return self._binop(other, lambda a, b: bool(a) or bool(b), dtype=bool)

        def __ror__(self, other):
            return self._binop(other, lambda a, b: bool(b) or bool(a), dtype=bool)

    class _DataFrameIloc:
        def __init__(self, df: "DataFrame"):
            self._df = df

        def __getitem__(self, item):
            if isinstance(item, slice):
                new_cols = {c: self._df._data[c][item] for c in self._df.columns}
                new_idx = self._df.index[item]
                if isinstance(self._df.index, DatetimeIndex):
                    new_idx = DatetimeIndex(new_idx)
                res = DataFrame(new_cols, columns=self._df.columns, index=new_idx)
                res.attrs = dict(self._df.attrs)
                return res
            row = {c: self._df._data[c][item] for c in self._df.columns}
            return row

    class _Resampler:
        def __init__(self, df: "DataFrame", rule: str, closed: str = "left", label: str = "left"):
            self._df = df
            self._rule = rule.strip()
            self._closed = closed
            self._label = label

        def _bucket_dt(self, dt: Any) -> Timestamp:
            raw_dt = dt._dt if isinstance(dt, Timestamp) else (dt if isinstance(dt, _dt.datetime) else _parse_dt(dt))
            r = self._rule.lower()
            if r in ("5min", "5m", "5t"):
                b = raw_dt.replace(minute=(raw_dt.minute // 5) * 5, second=0, microsecond=0)
            elif r in ("15min", "15m", "15t"):
                b = raw_dt.replace(minute=(raw_dt.minute // 15) * 15, second=0, microsecond=0)
            elif r in ("1h", "60min", "60m"):
                b = raw_dt.replace(minute=0, second=0, microsecond=0)
            elif r in ("4h", "240min", "240m"):
                b = raw_dt.replace(hour=(raw_dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
            elif r in ("1d", "d", "1day", "1440m"):
                b = raw_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                b = raw_dt.replace(minute=0, second=0, microsecond=0)
            return Timestamp(b)

        def _build_buckets(self, cols: Optional[Iterable[str]] = None) -> Tuple[Dict[Timestamp, Dict[str, List[float]]], List[Timestamp]]:
            target_cols = list(cols) if cols is not None else list(self._df.columns)
            buckets: Dict[Timestamp, Dict[str, List[float]]] = {}
            bucket_order: List[Timestamp] = []
            for i, dt in enumerate(self._df.index):
                b = self._bucket_dt(dt)
                if b not in buckets:
                    buckets[b] = {c: [] for c in target_cols}
                    bucket_order.append(b)
                for col in target_cols:
                    if col in self._df._data:
                        val = self._df._data[col][i]
                        if val is not None and not _is_nan(val):
                            buckets[b][col].append(float(val))
            return buckets, bucket_order

        def count(self) -> "DataFrame":
            buckets, bucket_order = self._build_buckets()
            out_cols = {c: [float(len(buckets[b][c])) for b in bucket_order] for c in self._df.columns}
            return DataFrame(out_cols, index=DatetimeIndex(bucket_order))

        def agg(self, agg_map: Dict[str, str]) -> "DataFrame":
            buckets, bucket_order = self._build_buckets(agg_map.keys())
            out_cols: Dict[str, List[float]] = {c: [] for c in agg_map}
            out_idx: List[Timestamp] = []
            for b in bucket_order:
                col_lists = buckets[b]
                out_idx.append(b)
                for col, fn_name in agg_map.items():
                    vals = col_lists.get(col, [])
                    if not vals:
                        out_cols[col].append(float("nan"))
                    elif fn_name == "first":
                        out_cols[col].append(vals[0])
                    elif fn_name == "last":
                        out_cols[col].append(vals[-1])
                    elif fn_name == "max":
                        out_cols[col].append(max(vals))
                    elif fn_name == "min":
                        out_cols[col].append(min(vals))
                    elif fn_name == "sum":
                        out_cols[col].append(sum(vals))
                    else:
                        out_cols[col].append(vals[-1])
            return DataFrame(out_cols, index=DatetimeIndex(out_idx))

    class DataFrame:
        def __init__(self, data=None, columns: Optional[Sequence[str]] = None, index=None):
            self._data: Dict[str, List[Any]] = {}
            self._columns: List[str] = []
            self.attrs: Dict[str, Any] = {}
            n_rows = 0

            if isinstance(data, dict):
                self._columns = list(columns) if columns is not None else list(data.keys())
                for c in self._columns:
                    col_val = data.get(c, [])
                    if isinstance(col_val, Series):
                        self._data[c] = list(col_val._values)
                        if index is None:
                            index = col_val.index
                    elif isinstance(col_val, (list, tuple)):
                        self._data[c] = list(col_val)
                    else:
                        if index is not None:
                            self._data[c] = [col_val] * len(index)
                        else:
                            self._data[c] = [col_val]
                    n_rows = max(n_rows, len(self._data[c]))
            elif isinstance(data, list):
                if len(data) > 0 and isinstance(data[0], dict):
                    self._columns = list(columns) if columns is not None else list(data[0].keys())
                    for c in self._columns:
                        self._data[c] = [row.get(c) for row in data]
                    n_rows = len(data)
                else:
                    self._columns = list(columns or [])
                    for idx_c, c in enumerate(self._columns):
                        self._data[c] = [row[idx_c] if idx_c < len(row) else None for row in data]
                    n_rows = len(data)
            else:
                self._columns = list(columns or [])
                for c in self._columns:
                    self._data[c] = []

            if index is None:
                self.index = list(range(n_rows))
            elif isinstance(index, DatetimeIndex) or (isinstance(index, list) and index and isinstance(index[0], (Timestamp, _dt.datetime))):
                self.index = DatetimeIndex(index)
            else:
                self.index = list(index)

        @property
        def columns(self) -> List[str]:
            return self._columns

        @columns.setter
        def columns(self, new_cols: List[str]):
            new_cols = list(new_cols)
            if len(new_cols) == len(self._columns):
                new_data = {}
                for old_c, new_c in zip(self._columns, new_cols):
                    new_data[new_c] = self._data.get(old_c, [])
                self._data = new_data
            self._columns = new_cols

        @property
        def empty(self) -> bool:
            return len(self.index) == 0 or len(self.columns) == 0

        @property
        def iloc(self) -> _DataFrameIloc:
            return _DataFrameIloc(self)

        def copy(self) -> "DataFrame":
            new_data = {c: list(self._data[c]) for c in self.columns}
            new_idx = DatetimeIndex(self.index) if isinstance(self.index, DatetimeIndex) else list(self.index)
            res = DataFrame(new_data, columns=list(self.columns), index=new_idx)
            res.attrs = dict(self.attrs)
            return res

        def sort_index(self) -> "DataFrame":
            pairs = sorted(enumerate(self.index), key=lambda p: p[1])
            idxs = [p[0] for p in pairs]
            new_data = {c: [self._data[c][i] for i in idxs] for c in self.columns}
            new_idx_raw = [self.index[i] for i in idxs]
            new_idx = DatetimeIndex(new_idx_raw) if isinstance(self.index, DatetimeIndex) else new_idx_raw
            res = DataFrame(new_data, columns=list(self.columns), index=new_idx)
            res.attrs = dict(self.attrs)
            return res

        def __len__(self) -> int:
            return len(self.index)

        def __contains__(self, key) -> bool:
            if key in self._data:
                return True
            if isinstance(key, str):
                low = key.lower()
                for k in self._data:
                    if isinstance(k, str) and k.lower() == low:
                        return True
            return False

        def __getitem__(self, key):
            if isinstance(key, str):
                if key in self._data:
                    return Series(self._data[key], index=self.index)
                low = key.lower()
                for k in self._data:
                    if isinstance(k, str) and k.lower() == low:
                        return Series(self._data[k], index=self.index)
                raise KeyError(key)
            if isinstance(key, (Series, list, tuple)):
                mask = key._values if isinstance(key, Series) else list(key)
                if len(mask) == len(self.index) and all(isinstance(x, bool) for x in mask):
                    keep_indices = [i for i, flag in enumerate(mask) if flag]
                    new_data = {c: [self._data[c][i] for i in keep_indices] for c in self.columns}
                    new_idx_raw = [self.index[i] for i in keep_indices]
                    new_idx = DatetimeIndex(new_idx_raw) if isinstance(self.index, DatetimeIndex) else new_idx_raw
                    res = DataFrame(new_data, columns=list(self.columns), index=new_idx)
                    res.attrs = dict(self.attrs)
                    return res
                if isinstance(key, list):
                    sub = {}
                    for k in key:
                        if k in self._data:
                            sub[k] = list(self._data[k])
                        elif isinstance(k, str):
                            low = k.lower()
                            for orig_k in self._data:
                                if isinstance(orig_k, str) and orig_k.lower() == low:
                                    sub[k] = list(self._data[orig_k])
                                    break
                    res = DataFrame(sub, columns=key, index=self.index)
                    res.attrs = dict(self.attrs)
                    return res
            raise KeyError(key)

        def __setitem__(self, key: str, value):
            if isinstance(value, (Series, DatetimeIndex)):
                self._data[key] = list(value._values if isinstance(value, Series) else value)
            elif isinstance(value, (list, tuple)):
                self._data[key] = list(value)
            else:
                self._data[key] = [value] * len(self.index)
            if key not in self.columns:
                self.columns.append(key)

        def rename(self, columns: Optional[Dict[str, str]] = None) -> "DataFrame":
            if not columns:
                return self.copy()
            new_cols = [columns.get(c, c) for c in self.columns]
            new_data = {columns.get(c, c): list(self._data[c]) for c in self.columns}
            res = DataFrame(new_data, columns=new_cols, index=self.index)
            res.attrs = dict(self.attrs)
            return res

        def set_index(self, col: str, inplace: bool = False):
            vals = self._data.get(col, [])
            is_dt = len(vals) > 0 and isinstance(vals[0], (Timestamp, _dt.datetime))
            new_idx = DatetimeIndex(vals) if is_dt else list(vals)
            new_cols = [c for c in self.columns if c != col]
            new_data = {c: self._data[c] for c in new_cols}
            if inplace:
                self.columns = new_cols
                self._data = new_data
                self.index = new_idx
                return None
            res = DataFrame(new_data, columns=new_cols, index=new_idx)
            res.attrs = dict(self.attrs)
            return res

        def astype(self, dtype) -> "DataFrame":
            new_data = {}
            for c in self.columns:
                s = Series(self._data[c], index=self.index, dtype=dtype)
                new_data[c] = list(s._values)
            res = DataFrame(new_data, columns=self.columns, index=self.index)
            res.attrs = dict(self.attrs)
            return res

        def dropna(self, subset: Optional[Sequence[str]] = None) -> "DataFrame":
            check_cols = list(subset) if subset else self.columns
            keep_indices = []
            for i in range(len(self.index)):
                ok = True
                for c in check_cols:
                    v = self._data[c][i]
                    if v is None or _is_nan(v):
                        ok = False
                        break
                if ok:
                    keep_indices.append(i)
            new_data = {c: [self._data[c][i] for i in keep_indices] for c in self.columns}
            new_idx = [self.index[i] for i in keep_indices]
            if isinstance(self.index, DatetimeIndex):
                new_idx = DatetimeIndex(new_idx)
            res = DataFrame(new_data, columns=self.columns, index=new_idx)
            res.attrs = dict(self.attrs)
            return res

        def resample(self, rule: str, closed: str = "left", label: str = "left") -> _Resampler:
            return _Resampler(self, rule, closed=closed, label=label)

        def tail(self, n: int = 5) -> "DataFrame":
            return self.iloc[-n:]

        def head(self, n: int = 5) -> "DataFrame":
            return self.iloc[:n]

        def max(self, axis: int = 0) -> "Series":
            if axis == 1:
                out = []
                for i in range(len(self.index)):
                    row_vals = [float(self._data[c][i]) for c in self.columns if self._data[c][i] is not None and not _is_nan(self._data[c][i])]
                    out.append(max(row_vals) if row_vals else float("nan"))
                return Series(out, index=self.index, dtype=float)
            return Series([Series(self._data[c]).max() for c in self.columns], index=self.columns, dtype=float)

    def _pd_concat(objs: Sequence[Any], axis: int = 0):
        if not objs:
            return DataFrame()
        if axis == 1:
            data = {f"c{idx}": list(s._values if isinstance(s, Series) else s) for idx, s in enumerate(objs)}
            idx = objs[0].index if hasattr(objs[0], "index") else []
            return DataFrame(data, index=idx)
        if isinstance(objs[0], DataFrame):
            cols = list(objs[0].columns)
            merged_data: Dict[str, List[Any]] = {c: [] for c in cols}
            merged_idx: List[Any] = []
            for df in objs:
                merged_idx.extend(df.index)
                for c in cols:
                    merged_data[c].extend(df._data.get(c, [None] * len(df.index)))
            idx_out = DatetimeIndex(merged_idx) if isinstance(objs[0].index, DatetimeIndex) else merged_idx
            return DataFrame(merged_data, columns=cols, index=idx_out)
        vals = []
        idx = []
        for s in objs:
            vals.extend(s._values)
            idx.extend(s.index)
        return Series(vals, index=idx)

    def _pd_to_datetime(seq, unit: Optional[str] = None, utc: bool = False):
        if isinstance(seq, (Series, DatetimeIndex, list, tuple)):
            vals = seq._values if isinstance(seq, Series) else seq
            return DatetimeIndex(Timestamp(_parse_dt(x, unit=unit)) for x in vals)
        return Timestamp(_parse_dt(seq, unit=unit))

    def _pd_date_range(start: Any = None, end: Any = None, periods: int = 1, freq: str = "5min", tz: Any = None) -> DatetimeIndex:
        f = str(freq).lower()
        step_sec = (
            60 if f in ("1m", "1min")
            else (300 if "5" in f
            else (900 if "15" in f
            else (3600 if "1h" in f or "60" in f
            else (14400 if "4h" in f or "240" in f
            else 86400))))
        )
        if end is not None:
            end_ts = Timestamp(end)
            return DatetimeIndex([Timestamp(end_ts._dt - _dt.timedelta(seconds=step_sec * (periods - 1 - i))) for i in range(int(periods))])
        start_ts = Timestamp(start) if start is not None else Timestamp.utcnow()
        return DatetimeIndex([Timestamp(start_ts._dt + _dt.timedelta(seconds=step_sec * i)) for i in range(int(periods))])

    def _pd_read_csv(filepath: str) -> DataFrame:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return DataFrame()
        cols = list(rows[0].keys())
        data: Dict[str, List[Any]] = {c: [] for c in cols}
        for r in rows:
            for c in cols:
                v = r[c]
                try:
                    data[c].append(float(v))
                except (ValueError, TypeError):
                    data[c].append(v)
        return DataFrame(data, columns=cols)

    class _PdApiTypes:
        @staticmethod
        def is_numeric_dtype(arr_or_dtype: Any) -> bool:
            if arr_or_dtype in (int, float):
                return True
            vals = arr_or_dtype._values if isinstance(arr_or_dtype, Series) else (list(arr_or_dtype) if isinstance(arr_or_dtype, (list, tuple)) else [])
            non_null = [v for v in vals if v is not None and not _is_nan(v)]
            if not non_null:
                return getattr(arr_or_dtype, "dtype", None) in (int, float)
            return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null)

    class _PdApi:
        types = _PdApiTypes()

    pd_mod.Series = Series
    pd_mod.DataFrame = DataFrame
    pd_mod.DatetimeIndex = DatetimeIndex
    pd_mod.Timestamp = Timestamp
    pd_mod.Timedelta = Timedelta
    pd_mod.api = _PdApi()
    pd_mod.isna = _is_nan
    pd_mod.notna = lambda v: not _is_nan(v)
    pd_mod.concat = _pd_concat
    pd_mod.to_datetime = _pd_to_datetime
    pd_mod.date_range = _pd_date_range
    pd_mod.read_csv = _pd_read_csv
    sys.modules["pandas"] = pd_mod


# =====================================================================
# 3. REQUESTS FALLBACK (using built-in urllib.request)
# =====================================================================
try:
    import requests  # noqa: F401
except ImportError:
    req_mod = types.ModuleType("requests")

    class _Response:
        def __init__(self, status_code: int, body: bytes, headers: Optional[Dict[str, str]] = None):
            self.status_code = status_code
            self.content = body
            self.text = body.decode("utf-8", errors="replace")
            self.headers = headers or {}

        def json(self):
            return _json.loads(self.text)

    def _do_request(method: str, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None, timeout: float = 8.0, data: Any = None, json: Any = None) -> _Response:
        full_url = url
        if params:
            q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if q:
                sep = "&" if "?" in full_url else "?"
                full_url = f"{full_url}{sep}{q}"
        req_headers = {"User-Agent": "BitsureTeddy/2.0"}
        if headers:
            req_headers.update(headers)
        body_bytes = None
        if json is not None:
            body_bytes = _json.dumps(json).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif isinstance(data, str):
            body_bytes = data.encode("utf-8")
        elif isinstance(data, bytes):
            body_bytes = data

        req = urllib.request.Request(full_url, data=body_bytes, headers=req_headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, "status", 200)
                raw = resp.read()
                return _Response(code, raw, dict(resp.headers))
        except urllib.error.HTTPError as e:
            raw = e.read() if hasattr(e, "read") else str(e).encode("utf-8")
            return _Response(e.code, raw, {})
        except Exception as e:
            raise RuntimeError(f"Network request failed for {full_url}: {e}")

    class _Session:
        def __init__(self):
            self.headers: Dict[str, str] = {}

        def get(self, url: str, **kwargs) -> _Response:
            merged_headers = dict(self.headers)
            if kwargs.get("headers"):
                merged_headers.update(kwargs["headers"])
            kwargs["headers"] = merged_headers
            return _do_request("GET", url, **kwargs)

        def request(self, method: str, url: str, **kwargs) -> _Response:
            merged_headers = dict(self.headers)
            if kwargs.get("headers"):
                merged_headers.update(kwargs["headers"])
            kwargs["headers"] = merged_headers
            return _do_request(method, url, **kwargs)

    req_mod.get = lambda url, **kwargs: _do_request("GET", url, **kwargs)
    req_mod.post = lambda url, **kwargs: _do_request("POST", url, **kwargs)
    req_mod.request = lambda method, url, **kwargs: _do_request(method, url, **kwargs)
    req_mod.Session = _Session
    sys.modules["requests"] = req_mod


# =====================================================================
# 4. WEBSOCKET / BINANCE / TELEGRAM / YFINANCE / APSCHEDULER FALLBACKS
# =====================================================================
try:
    import websocket  # noqa: F401
except ImportError:
    ws_mod = types.ModuleType("websocket")
    class _WebSocketApp:
        def __init__(self, url, on_open=None, on_message=None, on_error=None, on_close=None):
            self.url = url
        def run_forever(self):
            pass
        def close(self):
            pass
    ws_mod.WebSocketApp = _WebSocketApp
    sys.modules["websocket"] = ws_mod

try:
    import binance.client  # noqa: F401
    import binance.exceptions  # noqa: F401
except ImportError:
    bin_mod = types.ModuleType("binance")
    bin_client_mod = types.ModuleType("binance.client")
    bin_exc_mod = types.ModuleType("binance.exceptions")

    class BinanceAPIException(Exception):
        def __init__(self, response=None, status_code=400, text="", code=-1000, message=""):
            msg = message or text or str(response or "Binance API error")
            super().__init__(msg)
            self.code = code
            self.status_code = status_code
            self.message = msg

    class BinanceOrderException(Exception):
        def __init__(self, code=-1000, message="Binance order error"):
            super().__init__(message)
            self.code = code
            self.message = message

    class Client:
        def __init__(self, api_key=None, api_secret=None, testnet=False):
            self.API_KEY = api_key or ""
            self.API_SECRET = api_secret or ""
            self.testnet = testnet
            import requests as _r
            self.session = _r.Session()

        def ping(self):
            return {}

    bin_client_mod.Client = Client
    bin_exc_mod.BinanceAPIException = BinanceAPIException
    bin_exc_mod.BinanceOrderException = BinanceOrderException
    bin_mod.client = bin_client_mod
    bin_mod.exceptions = bin_exc_mod
    sys.modules["binance"] = bin_mod
    sys.modules["binance.client"] = bin_client_mod
    sys.modules["binance.exceptions"] = bin_exc_mod

try:
    import telegram  # noqa: F401
    import telegram.ext  # noqa: F401
except ImportError:
    tg_mod = types.ModuleType("telegram")
    tg_mod.__path__ = []
    tg_ext_mod = types.ModuleType("telegram.ext")
    tg_const_mod = types.ModuleType("telegram.constants")
    tg_err_mod = types.ModuleType("telegram.error")

    class _DummyTelegramObj:
        def __init__(self, *args, **kwargs):
            pass

    class BadRequest(Exception):
        pass

    class TelegramError(Exception):
        pass

    class _ContextTypes:
        DEFAULT_TYPE = Any

    class _ParseMode:
        MARKDOWN = "Markdown"
        HTML = "HTML"

    tg_mod.Update = _DummyTelegramObj
    tg_mod.BotCommand = _DummyTelegramObj
    tg_mod.InlineKeyboardButton = _DummyTelegramObj
    tg_mod.InlineKeyboardMarkup = _DummyTelegramObj
    tg_mod.LabeledPrice = _DummyTelegramObj
    tg_ext_mod.ContextTypes = _ContextTypes
    tg_ext_mod.ApplicationBuilder = _DummyTelegramObj
    tg_ext_mod.CommandHandler = _DummyTelegramObj
    tg_ext_mod.CallbackQueryHandler = _DummyTelegramObj
    tg_ext_mod.MessageHandler = _DummyTelegramObj
    tg_ext_mod.PreCheckoutQueryHandler = _DummyTelegramObj
    tg_ext_mod.filters = _DummyTelegramObj()
    tg_const_mod.ParseMode = _ParseMode
    tg_err_mod.BadRequest = BadRequest
    tg_err_mod.TelegramError = TelegramError

    sys.modules["telegram"] = tg_mod
    sys.modules["telegram.ext"] = tg_ext_mod
    sys.modules["telegram.constants"] = tg_const_mod
    sys.modules["telegram.error"] = tg_err_mod


# =====================================================================
# 5. YFINANCE FALLBACK (Yahoo Finance v8/chart + Binance PAXG fallback)
# =====================================================================
try:
    import yfinance  # noqa: F401
except ImportError:
    yf_mod = types.ModuleType("yfinance")

    class _YFTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.fast_info = self._build_fast_info()

        def _build_fast_info(self) -> Dict[str, Any]:
            df = self.history(period="5d", interval="1h")
            if df is not None and not df.empty:
                return {"last_price": float(df["Close"].iloc[-1])}
            return {"last_price": None}

        def history(self, period: str = "60d", interval: str = "1h"):
            import pandas as pd
            import requests as _r
            # First try Yahoo Finance v8 chart API
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(self.symbol)}"
                resp = _r.get(url, params={"range": period, "interval": interval}, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                if resp.status_code == 200:
                    payload = resp.json()
                    result = (payload.get("chart", {}).get("result") or [None])[0]
                    if result:
                        timestamps = result.get("timestamp") or []
                        quote = ((result.get("indicators", {}).get("quote") or [{}])[0])
                        opens = quote.get("open") or []
                        highs = quote.get("high") or []
                        lows = quote.get("low") or []
                        closes = quote.get("close") or []
                        vols = quote.get("volume") or []
                        rows = []
                        idx = []
                        for i, ts in enumerate(timestamps):
                            o = opens[i] if i < len(opens) else None
                            h = highs[i] if i < len(highs) else None
                            l = lows[i] if i < len(lows) else None
                            c = closes[i] if i < len(closes) else None
                            v = vols[i] if i < len(vols) else 0.0
                            if o is not None and h is not None and l is not None and c is not None:
                                rows.append({"Open": float(o), "High": float(h), "Low": float(l), "Close": float(c), "Volume": float(v or 0.0)})
                                idx.append(_dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).replace(tzinfo=None))
                        if rows:
                            return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex(idx))
            except Exception:
                pass

            # Fallback to Binance public mirror (e.g., GC=F -> PAXGUSDT gold spot token)
            bin_map = {
                "GC=F": "PAXGUSDT",
                "XAUUSD=X": "PAXGUSDT",
            }
            bin_sym = bin_map.get(self.symbol.upper(), "BTCUSDT")
            bin_tf = interval if interval in ("1m", "5m", "15m", "1h", "4h", "1d") else "1h"
            try:
                resp = _r.get(
                    "https://data-api.binance.vision/api/v3/klines",
                    params={"symbol": bin_sym, "interval": bin_tf, "limit": 300},
                    timeout=6,
                )
                if resp.status_code == 200:
                    klines = resp.json()
                    if isinstance(klines, list) and klines:
                        rows = []
                        idx = []
                        for k in klines:
                            idx.append(_dt.datetime.fromtimestamp(float(k[0]) / 1000.0, tz=_dt.timezone.utc).replace(tzinfo=None))
                            rows.append({
                                "Open": float(k[1]),
                                "High": float(k[2]),
                                "Low": float(k[3]),
                                "Close": float(k[4]),
                                "Volume": float(k[5]),
                            })
                        return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex(idx))
            except Exception:
                pass
            return pd.DataFrame()

    yf_mod.Ticker = _YFTicker
    sys.modules["yfinance"] = yf_mod


# =====================================================================
# 6. APSCHEDULER & CRYPTOGRAPHY FALLBACKS
# =====================================================================
try:
    import apscheduler  # noqa: F401
except ImportError:
    aps_mod = types.ModuleType("apscheduler")
    aps_sched = types.ModuleType("apscheduler.schedulers")
    aps_async = types.ModuleType("apscheduler.schedulers.asyncio")
    aps_trig = types.ModuleType("apscheduler.triggers")
    aps_int = types.ModuleType("apscheduler.triggers.interval")
    aps_cron = types.ModuleType("apscheduler.triggers.cron")

    class _Job:
        def __init__(self, job_id: str, func=None, kwargs=None):
            self.id = job_id
            self.func = func
            self.kwargs = kwargs or {}
            self.next_run_time = _dt.datetime.now(_dt.timezone.utc)

        def remove(self):
            pass

    class AsyncIOScheduler:
        def __init__(self, *args, **kwargs):
            self._jobs: Dict[str, _Job] = {}
            self.running = True

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            self.running = False

        def add_job(self, func, trigger=None, id=None, replace_existing=True, kwargs=None, **extra):
            jid = id or getattr(func, "__name__", f"job_{len(self._jobs)}")
            job = _Job(jid, func=func, kwargs=kwargs)
            self._jobs[jid] = job
            return job

        def get_job(self, job_id: str):
            return self._jobs.get(job_id)

        def get_jobs(self):
            return list(self._jobs.values())

        def remove_job(self, job_id: str):
            self._jobs.pop(job_id, None)

    class IntervalTrigger:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class CronTrigger:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    aps_async.AsyncIOScheduler = AsyncIOScheduler
    aps_int.IntervalTrigger = IntervalTrigger
    aps_cron.CronTrigger = CronTrigger
    sys.modules["apscheduler"] = aps_mod
    sys.modules["apscheduler.schedulers"] = aps_sched
    sys.modules["apscheduler.schedulers.asyncio"] = aps_async
    sys.modules["apscheduler.triggers"] = aps_trig
    sys.modules["apscheduler.triggers.interval"] = aps_int
    sys.modules["apscheduler.triggers.cron"] = aps_cron

try:
    import cryptography.fernet  # noqa: F401
except ImportError:
    import base64
    import hashlib
    import hmac
    import os

    crypto_mod = types.ModuleType("cryptography")
    fernet_mod = types.ModuleType("cryptography.fernet")

    class InvalidToken(Exception):
        pass

    class Fernet:
        def __init__(self, key: bytes | str):
            if isinstance(key, str):
                key = key.encode("utf-8")
            self._key = hashlib.sha256(key).digest()

        @staticmethod
        def generate_key() -> bytes:
            return base64.urlsafe_b64encode(os.urandom(32))

        def encrypt(self, data: bytes | str) -> bytes:
            if isinstance(data, str):
                data = data.encode("utf-8")
            nonce = os.urandom(16)
            stream = b""
            counter = 0
            while len(stream) < len(data):
                stream += hashlib.sha256(self._key + nonce + counter.to_bytes(4, "big")).digest()
                counter += 1
            xored = bytes(a ^ b for a, b in zip(data, stream[:len(data)]))
            sig = hmac.new(self._key, nonce + xored, hashlib.sha256).digest()[:16]
            return base64.urlsafe_b64encode(nonce + sig + xored)

        def decrypt(self, token: bytes | str) -> bytes:
            if isinstance(token, str):
                token = token.encode("utf-8")
            try:
                raw = base64.urlsafe_b64decode(token)
                nonce, sig, xored = raw[:16], raw[16:32], raw[32:]
                expected = hmac.new(self._key, nonce + xored, hashlib.sha256).digest()[:16]
                if not hmac.compare_digest(sig, expected):
                    raise InvalidToken("HMAC mismatch")
                stream = b""
                counter = 0
                while len(stream) < len(xored):
                    stream += hashlib.sha256(self._key + nonce + counter.to_bytes(4, "big")).digest()
                    counter += 1
                return bytes(a ^ b for a, b in zip(xored, stream[:len(xored)]))
            except Exception as e:
                raise InvalidToken(str(e))

    fernet_mod.Fernet = Fernet
    fernet_mod.InvalidToken = InvalidToken
    crypto_mod.fernet = fernet_mod
    sys.modules["cryptography"] = crypto_mod
    sys.modules["cryptography.fernet"] = fernet_mod


# =====================================================================
# 7. PSYCOPG2 -> SQLITE3 SEAMLESS ADAPTER (when psycopg2 not installed)
# =====================================================================
try:
    import psycopg2  # noqa: F401
    import psycopg2.pool  # noqa: F401
    import psycopg2.extras  # noqa: F401
except ImportError:
    import os
    import re
    import sqlite3
    import threading

    pg_mod = types.ModuleType("psycopg2")
    pg_pool_mod = types.ModuleType("psycopg2.pool")
    pg_extras_mod = types.ModuleType("psycopg2.extras")

    _SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "/app/applet/bitsure_teddy.db")
    _sqlite_lock = threading.RLock()

    class RealDictCursor:
        pass

    class DictCursor:
        pass

    class _DictRow:
        """Emulates psycopg2.extras.DictRow (supports both integer index row[0] and key lookup row['col'])."""
        def __init__(self, cols: List[str], values: Tuple[Any, ...]):
            self._cols = list(cols)
            self._vals = list(values)
            self._map = dict(zip(self._cols, self._vals))

        def __getitem__(self, key):
            if isinstance(key, (int, slice)):
                return self._vals[key]
            return self._map[key]

        def __setitem__(self, key, value):
            if isinstance(key, int):
                self._vals[key] = value
                if 0 <= key < len(self._cols):
                    self._map[self._cols[key]] = value
            else:
                self._map[key] = value
                if key in self._cols:
                    self._vals[self._cols.index(key)] = value

        def __contains__(self, key):
            return key in self._map or key in self._vals

        def get(self, key, default=None):
            return self._map.get(key, default)

        def keys(self):
            return self._map.keys()

        def values(self):
            return self._map.values()

        def items(self):
            return self._map.items()

        def __iter__(self):
            return iter(self._vals)

        def __len__(self):
            return len(self._vals)

        def __repr__(self):
            return repr(self._map)

    def _translate_pg_to_sqlite(sql: str, params=None):
        s = sql.strip()
        # Handle pg_advisory_xact_lock
        if "pg_advisory_xact_lock" in s.lower():
            return "SELECT 1", ()

        # Translate DDL types
        s = re.sub(r"\bSERIAL\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", s, flags=re.IGNORECASE)
        s = re.sub(r"\bDOUBLE\s+PRECISION\b", "REAL", s, flags=re.IGNORECASE)
        s = re.sub(r"\bTIMESTAMPTZ\b", "TEXT", s, flags=re.IGNORECASE)
        s = re.sub(r"\bTIMESTAMP\b", "TEXT", s, flags=re.IGNORECASE)
        s = re.sub(r"\bNOW\(\)", "CURRENT_TIMESTAMP", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+FOR\s+UPDATE\b", "", s, flags=re.IGNORECASE)

        # Handle ALTER TABLE ... ADD COLUMN IF NOT EXISTS col_def
        m_alter = re.match(
            r"^\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(.+)$",
            s,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m_alter:
            tbl, col_def = m_alter.group(1), m_alter.group(2)
            s = f"ALTER TABLE {tbl} ADD COLUMN {col_def}"

        # Handle ANY(%s) where param is a list/tuple
        if params is not None:
            param_list = list(params) if isinstance(params, (list, tuple)) else [params]
            new_params = []
            parts = s.split("%s")
            if len(parts) - 1 == len(param_list):
                rebuilt = []
                for idx_p, p_val in enumerate(param_list):
                    prefix = parts[idx_p]
                    # Check if prefix ends with "= ANY(" and next part starts with ")"
                    if re.search(r"=\s*ANY\s*\(\s*$", prefix, flags=re.IGNORECASE) and parts[idx_p + 1].lstrip().startswith(")"):
                        prefix = re.sub(r"=\s*ANY\s*\(\s*$", "IN (", prefix, flags=re.IGNORECASE)
                        seq = list(p_val) if isinstance(p_val, (list, tuple, set)) else [p_val]
                        if not seq:
                            rebuilt.append(prefix + "NULL")
                        else:
                            placeholders = ", ".join(["?"] * len(seq))
                            rebuilt.append(prefix + placeholders)
                            new_params.extend(seq)
                    else:
                        rebuilt.append(prefix + "?")
                        if isinstance(p_val, bool):
                            new_params.append(1 if p_val else 0)
                        else:
                            new_params.append(p_val)
                rebuilt.append(parts[-1])
                s = "".join(rebuilt)
                return s, tuple(new_params)
            else:
                s = s.replace("%s", "?")
                return s, tuple(1 if isinstance(x, bool) else x for x in param_list)
        else:
            s = s.replace("%s", "?")
            return s, ()

    class _SQLiteCursorWrapper:
        def __init__(self, raw_conn: sqlite3.Connection, dict_mode: bool = False):
            self._conn = raw_conn
            self._dict_mode = dict_mode
            self._cur = raw_conn.cursor()
            self._last_rows = None
            self.rowcount = 0

        @property
        def description(self):
            return self._cur.description

        def execute(self, sql: str, params=None):
            translated_sql, translated_params = _translate_pg_to_sqlite(sql, params)
            try:
                with _sqlite_lock:
                    self._cur.execute(translated_sql, translated_params)
                    self.rowcount = self._cur.rowcount
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "duplicate column name" in msg or "already exists" in msg:
                    self.rowcount = 0
                    return
                raise

        def fetchone(self):
            row = self._cur.fetchone()
            if row is None:
                return None
            if self._dict_mode:
                cols = [d[0] for d in (self._cur.description or [])]
                return _DictRow(cols, row)
            return row

        def fetchall(self):
            rows = self._cur.fetchall()
            if self._dict_mode:
                cols = [d[0] for d in (self._cur.description or [])]
                return [_DictRow(cols, r) for r in rows]
            return rows

        def close(self):
            try:
                self._cur.close()
            except Exception:
                pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.close()

    class _SQLiteConnectionWrapper:
        def __init__(self, db_path: str, default_dict_cursor: bool = True):
            self._raw = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
            self._raw.execute("PRAGMA journal_mode=WAL")
            self._raw.execute("PRAGMA synchronous=NORMAL")
            self._raw.execute("PRAGMA foreign_keys=OFF")
            self._raw.create_function("LEAST", -1, lambda *args: min(x for x in args if x is not None) if any(x is not None for x in args) else None)
            self._raw.create_function("GREATEST", -1, lambda *args: max(x for x in args if x is not None) if any(x is not None for x in args) else None)
            self._default_dict = default_dict_cursor
            self.autocommit = False
            self.closed = False

        def cursor(self, cursor_factory=None):
            if cursor_factory is not None:
                is_dict = True
            else:
                is_dict = self._default_dict
            return _SQLiteCursorWrapper(self._raw, dict_mode=is_dict)

        def commit(self):
            with _sqlite_lock:
                self._raw.commit()

        def rollback(self):
            with _sqlite_lock:
                self._raw.rollback()

        def close(self):
            pass

    class ThreadedConnectionPool:
        def __init__(self, minconn=1, maxconn=20, dsn=None, **kwargs):
            self._conn = _SQLiteConnectionWrapper(_SQLITE_DB_PATH, default_dict_cursor=True)

        def getconn(self):
            return self._conn

        def putconn(self, conn, close=False):
            pass

        def closeall(self):
            pass

    def _connect(dsn=None, **kwargs):
        return _SQLiteConnectionWrapper(_SQLITE_DB_PATH, default_dict_cursor=True)

    class PoolError(Exception):
        pass

    pg_mod.connect = _connect
    pg_mod.Error = Exception
    pg_mod.OperationalError = sqlite3.OperationalError
    pg_mod.IntegrityError = sqlite3.IntegrityError
    pg_pool_mod.PoolError = PoolError
    pg_pool_mod.ThreadedConnectionPool = ThreadedConnectionPool
    pg_extras_mod.RealDictCursor = RealDictCursor
    pg_extras_mod.DictCursor = DictCursor
    pg_mod.pool = pg_pool_mod
    pg_mod.extras = pg_extras_mod

    sys.modules["psycopg2"] = pg_mod
    sys.modules["psycopg2.pool"] = pg_pool_mod
    sys.modules["psycopg2.extras"] = pg_extras_mod

