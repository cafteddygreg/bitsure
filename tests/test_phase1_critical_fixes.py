import datetime
import importlib
import math
import os
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")


def _install_minimal_scientific_shims_if_needed():
    """Provides functional pure-Python numpy/pandas/requests shims if the test runner container lacks pip packages."""
    installed = []
    try:
        import numpy  # noqa: F401
        import pandas  # noqa: F401
        return installed
    except ModuleNotFoundError:
        pass

    # --- Minimal NumPy shim ---
    np_mod = types.ModuleType("numpy")
    np_mod.nan = float("nan")
    np_mod.inf = float("inf")
    np_mod.isnan = lambda x: math.isnan(float(x)) if isinstance(x, (int, float)) else False
    np_mod.isinf = lambda x: math.isinf(float(x)) if isinstance(x, (int, float)) else False

    def _to_list(x):
        if hasattr(x, "_data"):
            return list(x._data)
        if isinstance(x, (list, tuple)):
            return list(x)
        return [x]

    def _np_where(cond, a, b):
        c_list = _to_list(cond)
        a_list = _to_list(a) if isinstance(a, (list, tuple)) or hasattr(a, "_data") else [a] * len(c_list)
        b_list = _to_list(b) if isinstance(b, (list, tuple)) or hasattr(b, "_data") else [b] * len(c_list)
        return [av if cv else bv for cv, av, bv in zip(c_list, a_list, b_list)]

    def _np_maximum(a, b):
        a_list = _to_list(a)
        b_list = _to_list(b) if isinstance(b, (list, tuple)) or hasattr(b, "_data") else [b] * len(a_list)
        res = [max(float(x), float(y)) for x, y in zip(a_list, b_list)]
        if hasattr(a, "_index"):
            return _Series(res, index=a._index)
        return res

    def _np_minimum(a, b):
        a_list = _to_list(a)
        b_list = _to_list(b) if isinstance(b, (list, tuple)) or hasattr(b, "_data") else [b] * len(a_list)
        res = [min(float(x), float(y)) for x, y in zip(a_list, b_list)]
        if hasattr(a, "_index"):
            return _Series(res, index=a._index)
        return res

    def _np_abs(a):
        if hasattr(a, "abs"):
            return a.abs()
        return [abs(float(x)) for x in _to_list(a)]

    np_mod.where = _np_where
    np_mod.maximum = _np_maximum
    np_mod.minimum = _np_minimum
    np_mod.abs = _np_abs
    np_mod.arange = lambda n, dtype=float: [float(i) for i in range(int(n))]
    np_mod.sin = lambda arr: [math.sin(float(x)) for x in _to_list(arr)]
    np_mod.full = lambda n, val: [float(val) for _ in range(int(n))]
    sys.modules["numpy"] = np_mod
    installed.append("numpy")

    # --- Minimal Pandas shim ---
    pd_mod = types.ModuleType("pandas")

    class _Timedelta:
        def __init__(self, value=0, unit="min", **kwargs):
            if isinstance(value, _Timedelta):
                self._seconds = value._seconds
            elif isinstance(value, datetime.timedelta):
                self._seconds = value.total_seconds()
            elif kwargs:
                self._seconds = datetime.timedelta(**kwargs).total_seconds()
            else:
                u = str(unit).lower()
                mult = 60.0 if u in ("m", "min", "minute", "minutes", "t") else (3600.0 if u in ("h", "hour", "hours") else (86400.0 if u in ("d", "day", "days") else (0.001 if u == "ms" else 1.0)))
                self._seconds = float(value) * mult

        def total_seconds(self):
            return self._seconds

        def __gt__(self, other):
            return self._seconds > (other._seconds if isinstance(other, _Timedelta) else float(other))

        def __ge__(self, other):
            return self._seconds >= (other._seconds if isinstance(other, _Timedelta) else float(other))

        def __lt__(self, other):
            return self._seconds < (other._seconds if isinstance(other, _Timedelta) else float(other))

        def __le__(self, other):
            return self._seconds <= (other._seconds if isinstance(other, _Timedelta) else float(other))

    class _Timestamp:
        def __init__(self, ts=None, unit=None, tz=None):
            if isinstance(ts, _Timestamp):
                self._dt = ts._dt
            elif isinstance(ts, datetime.datetime):
                self._dt = ts.replace(tzinfo=None)
            elif isinstance(ts, (int, float)):
                sec = float(ts) / 1000.0 if unit == "ms" else float(ts)
                self._dt = datetime.datetime.utcfromtimestamp(sec)
            elif isinstance(ts, str):
                s = ts.strip().replace("T", " ").replace("Z", "")
                self._dt = datetime.datetime.fromisoformat(s)
            else:
                self._dt = datetime.datetime.utcnow()
            self.tz = None
            self.tzinfo = None

        @classmethod
        def utcnow(cls):
            return cls(datetime.datetime.utcnow())

        @classmethod
        def now(cls, tz=None):
            return cls(datetime.datetime.utcnow())

        def tz_localize(self, tz):
            return self

        def tz_convert(self, tz):
            return self

        def __sub__(self, other):
            if isinstance(other, _Timestamp):
                return _Timedelta((self._dt - other._dt).total_seconds(), unit="s")
            if isinstance(other, _Timedelta):
                return _Timestamp(self._dt - datetime.timedelta(seconds=other._seconds))
            raise TypeError("Unsupported subtraction")

        def __add__(self, other):
            if isinstance(other, _Timedelta):
                return _Timestamp(self._dt + datetime.timedelta(seconds=other._seconds))
            raise TypeError("Unsupported addition")

        def __gt__(self, other):
            return self._dt > (_Timestamp(other)._dt if not isinstance(other, _Timestamp) else other._dt)

        def __ge__(self, other):
            return self._dt >= (_Timestamp(other)._dt if not isinstance(other, _Timestamp) else other._dt)

        def __lt__(self, other):
            return self._dt < (_Timestamp(other)._dt if not isinstance(other, _Timestamp) else other._dt)

        def __le__(self, other):
            return self._dt <= (_Timestamp(other)._dt if not isinstance(other, _Timestamp) else other._dt)

        def __eq__(self, other):
            if not isinstance(other, (_Timestamp, datetime.datetime, str)):
                return False
            return self._dt == _Timestamp(other)._dt

        def __hash__(self):
            return hash(self._dt)

        def __repr__(self):
            return self._dt.strftime("%Y-%m-%d %H:%M:%S")

        def __str__(self):
            return self.__repr__()

    class _Index(list):
        def __init__(self, seq=()):
            super().__init__(seq)
            self.tz = None
            self.tzinfo = None

        @property
        def is_monotonic_increasing(self):
            return all(self[i] <= self[i + 1] for i in range(len(self) - 1))

        def to_series(self):
            return _Series(list(self), index=list(self))

        def difference(self, other):
            s = set(other)
            return _Index([x for x in self if x not in s])

        def __add__(self, other):
            if isinstance(other, _Timedelta):
                return _Index([x + other for x in self])
            return super().__add__(other)

        def __le__(self, other):
            return _Series([x <= other for x in self], index=list(self))

        def __lt__(self, other):
            return _Series([x < other for x in self], index=list(self))

        def __ge__(self, other):
            return _Series([x >= other for x in self], index=list(self))

        def __gt__(self, other):
            return _Series([x > other for x in self], index=list(self))

    class _IlocSeries:
        def __init__(self, series):
            self._s = series

        def __getitem__(self, idx):
            if isinstance(idx, slice):
                return _Series(self._s._data[idx], index=self._s._index[idx])
            return self._s._data[idx]

    class _RollingSeries:
        def __init__(self, series, window, min_periods=None, center=False):
            self._s = series
            self._w = int(window)
            self._min_p = int(min_periods) if min_periods is not None else self._w
            self._center = bool(center)

        def mean(self):
            n = len(self._s._data)
            out = []
            for i in range(n):
                if i + 1 < self._w:
                    out.append(float("nan"))
                else:
                    vals = [float(x) for x in self._s._data[i - self._w + 1 : i + 1]]
                    out.append(float("nan") if any(math.isnan(v) for v in vals) else sum(vals) / self._w)
            return _Series(out, index=self._s._index)

        def std(self):
            n = len(self._s._data)
            out = []
            for i in range(n):
                if i + 1 < self._w:
                    out.append(float("nan"))
                else:
                    vals = [float(x) for x in self._s._data[i - self._w + 1 : i + 1]]
                    if any(math.isnan(v) for v in vals) or self._w <= 1:
                        out.append(float("nan"))
                    else:
                        m = sum(vals) / self._w
                        var = sum((v - m) ** 2 for v in vals) / (self._w - 1)
                        out.append(math.sqrt(var))
            return _Series(out, index=self._s._index)

        def max(self):
            n = len(self._s._data)
            out = []
            half = self._w // 2
            for i in range(n):
                if self._center:
                    start, end = i - half, i + half + 1
                    if start < 0 or end > n:
                        out.append(float("nan"))
                    else:
                        vals = [float(x) for x in self._s._data[start:end]]
                        out.append(max(vals))
                else:
                    if i + 1 < self._w:
                        out.append(float("nan"))
                    else:
                        out.append(max(float(x) for x in self._s._data[i - self._w + 1 : i + 1]))
            return _Series(out, index=self._s._index)

        def min(self):
            n = len(self._s._data)
            out = []
            half = self._w // 2
            for i in range(n):
                if self._center:
                    start, end = i - half, i + half + 1
                    if start < 0 or end > n:
                        out.append(float("nan"))
                    else:
                        vals = [float(x) for x in self._s._data[start:end]]
                        out.append(min(vals))
                else:
                    if i + 1 < self._w:
                        out.append(float("nan"))
                    else:
                        out.append(min(float(x) for x in self._s._data[i - self._w + 1 : i + 1]))
            return _Series(out, index=self._s._index)

    class _EwmSeries:
        def __init__(self, series, alpha=None, span=None, min_periods=1, adjust=False):
            self._s = series
            self._alpha = float(alpha) if alpha is not None else (2.0 / (float(span) + 1.0))
            self._min_p = int(min_periods or 1)

        def mean(self):
            out = []
            ema = None
            valid_count = 0
            for x in self._s._data:
                v = float(x)
                if math.isnan(v):
                    out.append(float("nan"))
                    continue
                valid_count += 1
                ema = v if ema is None else (self._alpha * v + (1.0 - self._alpha) * ema)
                out.append(ema if valid_count >= self._min_p else float("nan"))
            return _Series(out, index=self._s._index)

    class _Series:
        def __init__(self, data=None, index=None, dtype=None):
            if data is None:
                self._data = []
                self._index = _Index(index if index is not None else [])
            elif isinstance(data, _Series):
                self._data = list(data._data)
                self._index = _Index(index if index is not None else data._index)
            elif isinstance(data, (list, tuple)):
                self._data = list(data)
                self._index = _Index(index if index is not None else range(len(self._data)))
            else:
                idx = _Index(index if index is not None else [0])
                self._data = [data for _ in idx]
                self._index = idx

        @property
        def iloc(self):
            return _IlocSeries(self)

        @property
        def values(self):
            return list(self._data)

        @property
        def index(self):
            return self._index

        def __len__(self):
            return len(self._data)

        def __getitem__(self, key):
            if isinstance(key, (_Series, list, tuple)):
                mask = key._data if isinstance(key, _Series) else list(key)
                if len(mask) == len(self._data) and all(isinstance(x, bool) for x in mask):
                    idxs = [i for i, flag in enumerate(mask) if flag]
                    return _Series([self._data[i] for i in idxs], index=[self._index[i] for i in idxs])
            if isinstance(key, slice):
                return _Series(self._data[key], index=self._index[key])
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

        def _binop(self, other, fn):
            if isinstance(other, _Series):
                return _Series([fn(a, b) for a, b in zip(self._data, other._data)], index=self._index)
            if isinstance(other, (list, tuple)):
                return _Series([fn(a, b) for a, b in zip(self._data, other)], index=self._index)
            return _Series([fn(a, other) for a in self._data], index=self._index)

        def __add__(self, other): return self._binop(other, lambda a, b: a + b)
        def __radd__(self, other): return self._binop(other, lambda a, b: b + a)
        def __sub__(self, other): return self._binop(other, lambda a, b: a - b)
        def __rsub__(self, other): return self._binop(other, lambda a, b: b - a)
        def __mul__(self, other): return self._binop(other, lambda a, b: a * b)
        def __rmul__(self, other): return self._binop(other, lambda a, b: b * a)
        def __neg__(self):
            return _Series([(-v if (v is not None and not (isinstance(v, float) and math.isnan(v))) else float("nan")) for v in self._data], index=self._index)
        def clip(self, lower=None, upper=None):
            out = []
            for v in self._data:
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    out.append(float("nan"))
                else:
                    val = float(v)
                    if lower is not None and val < lower:
                        val = float(lower)
                    if upper is not None and val > upper:
                        val = float(upper)
                    out.append(val)
            return _Series(out, index=self._index)
        def __truediv__(self, other):
            def _div(a, b):
                try:
                    return float("nan") if b == 0 or math.isnan(float(a)) or math.isnan(float(b)) else a / b
                except Exception:
                    return float("nan")
            return self._binop(other, _div)
        def __rtruediv__(self, other):
            def _rdiv(a, b):
                try:
                    return float("nan") if a == 0 or math.isnan(float(a)) or math.isnan(float(b)) else b / a
                except Exception:
                    return float("nan")
            return self._binop(other, _rdiv)
        def __gt__(self, other): return self._binop(other, lambda a, b: bool(a > b) if not (isinstance(a, float) and math.isnan(a)) else False)
        def __ge__(self, other): return self._binop(other, lambda a, b: bool(a >= b) if not (isinstance(a, float) and math.isnan(a)) else False)
        def __lt__(self, other): return self._binop(other, lambda a, b: bool(a < b) if not (isinstance(a, float) and math.isnan(a)) else False)
        def __le__(self, other): return self._binop(other, lambda a, b: bool(a <= b) if not (isinstance(a, float) and math.isnan(a)) else False)
        def __eq__(self, other): return self._binop(other, lambda a, b: a == b)

        def diff(self, periods=1):
            out = []
            for i in range(len(self._data)):
                if i < periods:
                    if isinstance(self._data[i], _Timestamp):
                        out.append(None)
                    else:
                        out.append(float("nan"))
                else:
                    a, b = self._data[i], self._data[i - periods]
                    if a is None or b is None:
                        out.append(None)
                    else:
                        out.append(a - b)
            return _Series(out, index=self._index)

        def shift(self, periods=1):
            out = [float("nan")] * periods + self._data[:-periods] if periods > 0 else self._data
            return _Series(out, index=self._index)

        def where(self, cond, other=float("nan")):
            c_list = cond._data if isinstance(cond, _Series) else list(cond)
            o_list = other._data if isinstance(other, _Series) else [other] * len(self._data)
            return _Series([v if c else o for v, c, o in zip(self._data, c_list, o_list)], index=self._index)

        def rolling(self, window, min_periods=None, center=False):
            return _RollingSeries(self, window=window, min_periods=min_periods, center=center)

        def ewm(self, alpha=None, span=None, min_periods=1, adjust=False):
            return _EwmSeries(self, alpha=alpha, span=span, min_periods=min_periods, adjust=adjust)

        def dropna(self):
            pairs = [(idx, v) for idx, v in zip(self._index, self._data) if v is not None and not (isinstance(v, float) and math.isnan(v))]
            return _Series([p[1] for p in pairs], index=[p[0] for p in pairs])

        def abs(self):
            return _Series([abs(v) if v is not None else float("nan") for v in self._data], index=self._index)

        def median(self):
            vals = sorted([v for v in self._data if v is not None], key=lambda x: x.total_seconds() if isinstance(x, _Timedelta) else float(x))
            return vals[len(vals) // 2] if vals else None

        def mean(self):
            vals = [float(v) for v in self._data if v is not None and not math.isnan(float(v))]
            return sum(vals) / len(vals) if vals else float("nan")

        def max(self):
            vals = [float(v) for v in self._data if v is not None and not math.isnan(float(v))]
            return max(vals) if vals else float("nan")

        def min(self):
            vals = [float(v) for v in self._data if v is not None and not math.isnan(float(v))]
            return min(vals) if vals else float("nan")

        def replace(self, to_replace, value):
            targets = set(to_replace) if isinstance(to_replace, (list, tuple, set)) else {to_replace}
            return _Series([value if v in targets else v for v in self._data], index=self._index)

        @property
        def empty(self):
            return len(self._data) == 0

        @property
        def dt(self):
            s = self
            class _DtAccessor:
                def total_seconds(self_dt):
                    return _Series([v.total_seconds() if hasattr(v, "total_seconds") else float(v) for v in s._data], index=s._index)
            return _DtAccessor()

        def astype(self, dtype):
            return _Series([dtype(v) for v in self._data], index=self._index)

        def reindex(self, new_index):
            lookup = {idx: val for idx, val in zip(self._index, self._data)}
            return _Series([lookup.get(idx, float("nan")) for idx in new_index], index=list(new_index))

        def fillna(self, val):
            return _Series([val if (v is None or (isinstance(v, float) and math.isnan(v))) else v for v in self._data], index=self._index)

        def resample(self, rule, label="left", closed="left"):
            df_tmp = _DataFrame({"_v": self._data}, index=self._index)
            return _ResamplerSeries(df_tmp, rule)

        def __and__(self, other):
            o_list = other._data if isinstance(other, _Series) else list(other)
            return _Series([bool(a) and bool(b) for a, b in zip(self._data, o_list)], index=self._index)

        def __rand__(self, other):
            o_list = other._data if isinstance(other, _Series) else list(other)
            return _Series([bool(a) and bool(b) for a, b in zip(o_list, self._data)], index=self._index)

    class _ResamplerSeries:
        def __init__(self, df, rule):
            self._r = _Resampler(df, rule)

        def count(self):
            buckets = self._r._build_buckets()
            new_idx = sorted(buckets.keys(), key=lambda t: t._dt)
            return _Series([len(buckets[b_ts]) for b_ts in new_idx], index=new_idx)

    class _IlocDF:
        def __init__(self, df):
            self._df = df

        def __getitem__(self, idx):
            if isinstance(idx, slice):
                new_cols = {k: v[idx] for k, v in self._df._cols.items()}
                res = _DataFrame(new_cols, index=self._df._index[idx])
                res.attrs = dict(self._df.attrs)
                return res
            return {k: v[idx] for k, v in self._df._cols.items()}

    class _Resampler:
        def __init__(self, df, rule):
            self._df = df
            r = str(rule).lower()
            self._sec = 300 if "5min" in r else (900 if "15min" in r else (3600 if r == "1h" else (14400 if r == "4h" else (86400 if r in ("1d", "d") else 900))))

        def _build_buckets(self):
            buckets = {}
            for i, ts in enumerate(self._df._index):
                epoch = int((ts._dt - datetime.datetime(1970, 1, 1)).total_seconds())
                b_epoch = (epoch // self._sec) * self._sec
                b_ts = _Timestamp(datetime.datetime.utcfromtimestamp(b_epoch))
                buckets.setdefault(b_ts, []).append(i)
            return buckets

        def agg(self, spec):
            buckets = self._build_buckets()
            new_idx = sorted(buckets.keys(), key=lambda t: t._dt)
            new_cols = {col: [] for col in spec}
            for b_ts in new_idx:
                idxs = buckets[b_ts]
                for col, fn in spec.items():
                    vals = [self._df._cols[col][j] for j in idxs]
                    if fn == "first":
                        new_cols[col].append(vals[0])
                    elif fn == "last":
                        new_cols[col].append(vals[-1])
                    elif fn == "max":
                        new_cols[col].append(max(vals))
                    elif fn == "min":
                        new_cols[col].append(min(vals))
                    elif fn == "sum":
                        new_cols[col].append(sum(vals))
            return _DataFrame(new_cols, index=new_idx)

    class _DataFrame:
        def __init__(self, data=None, index=None, columns=None):
            self._cols = {}
            self.attrs = {}
            if isinstance(data, dict):
                first_val = next(iter(data.values()), [])
                n = len(first_val) if isinstance(first_val, (list, tuple, _Series)) else 1
                self._index = _Index([_Timestamp(x) if isinstance(x, (_Timestamp, datetime.datetime, str)) else x for x in (index if index is not None else range(n))])
                for k, v in data.items():
                    if isinstance(v, _Series):
                        self._cols[k] = list(v._data)
                    elif isinstance(v, (list, tuple)):
                        self._cols[k] = list(v)
                    else:
                        self._cols[k] = [v] * len(self._index)

        @property
        def index(self):
            return self._index

        @property
        def columns(self):
            return _Index(self._cols.keys())

        @property
        def empty(self):
            return len(self._index) == 0

        @property
        def iloc(self):
            return _IlocDF(self)

        def __len__(self):
            return len(self._index)

        def __getitem__(self, key):
            if isinstance(key, str):
                return _Series(self._cols[key], index=self._index)
            mask = key._data if isinstance(key, _Series) else list(key)
            idxs = [i for i, flag in enumerate(mask) if flag]
            new_cols = {k: [v[i] for i in idxs] for k, v in self._cols.items()}
            res = _DataFrame(new_cols, index=[self._index[i] for i in idxs])
            res.attrs = dict(self.attrs)
            return res

        def __setitem__(self, key, val):
            self._cols[key] = list(val._data) if isinstance(val, _Series) else list(val)

        def copy(self):
            res = _DataFrame({k: list(v) for k, v in self._cols.items()}, index=list(self._index))
            res.attrs = dict(self.attrs)
            return res

        def rename(self, columns=None):
            if not columns:
                return self.copy()
            new_cols = {columns.get(k, k): list(v) for k, v in self._cols.items()}
            res = _DataFrame(new_cols, index=list(self._index))
            res.attrs = dict(self.attrs)
            return res

        def sort_index(self):
            pairs = sorted(enumerate(self._index), key=lambda p: p[1])
            idxs = [p[0] for p in pairs]
            new_cols = {k: [v[i] for i in idxs] for k, v in self._cols.items()}
            res = _DataFrame(new_cols, index=[self._index[i] for i in idxs])
            res.attrs = dict(self.attrs)
            return res

        def dropna(self, subset=None):
            cols_to_check = subset if subset else list(self._cols.keys())
            idxs = []
            for i in range(len(self._index)):
                ok = True
                for c in cols_to_check:
                    val = self._cols[c][i]
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        ok = False
                        break
                if ok:
                    idxs.append(i)
            new_cols = {k: [v[i] for i in idxs] for k, v in self._cols.items()}
            res = _DataFrame(new_cols, index=[self._index[i] for i in idxs])
            res.attrs = dict(self.attrs)
            return res

        def resample(self, rule, label="left", closed="left"):
            return _Resampler(self, rule)

        def max(self, axis=0):
            if axis == 1:
                keys = list(self._cols.keys())
                n = len(self._index)
                return _Series([max(float(self._cols[k][i]) for k in keys) for i in range(n)], index=self._index)
            raise NotImplementedError

    def _concat(objs, axis=0):
        if axis == 1:
            cols = {str(i): s for i, s in enumerate(objs)}
            return _DataFrame(cols, index=objs[0].index)
        new_idx = []
        new_cols = {k: [] for k in objs[0].columns}
        for df in objs:
            new_idx.extend(df.index)
            for k in new_cols:
                new_cols[k].extend(df._cols[k])
        return _DataFrame(new_cols, index=new_idx)

    def _date_range(end, periods, freq="5min"):
        end_ts = _Timestamp(end)
        f = str(freq).lower()
        step_sec = 300 if "5" in f else (900 if "15" in f else (3600 if "1h" in f else (14400 if "4h" in f else 86400)))
        return _Index([_Timestamp(end_ts._dt - datetime.timedelta(seconds=step_sec * (periods - 1 - i))) for i in range(periods)])

    def _isna(x):
        if x is None:
            return True
        if isinstance(x, float):
            return math.isnan(x)
        return False

    pd_mod.Series = _Series
    pd_mod.DataFrame = _DataFrame
    pd_mod.Timestamp = _Timestamp
    pd_mod.Timedelta = _Timedelta
    pd_mod.DatetimeIndex = _Index
    pd_mod.concat = _concat
    pd_mod.date_range = _date_range
    pd_mod.isna = _isna
    pd_mod.notna = lambda x: not _isna(x)
    pd_mod.to_datetime = lambda x, unit=None: [_Timestamp(v, unit=unit) for v in x] if isinstance(x, (list, tuple, _Series)) else _Timestamp(x, unit=unit)
    sys.modules["pandas"] = pd_mod
    installed.append("pandas")

    if "requests" not in sys.modules:
        req_mod = types.ModuleType("requests")
        req_mod.Session = MagicMock
        req_mod.get = MagicMock()
        req_mod.request = MagicMock()
        sys.modules["requests"] = req_mod
        installed.append("requests")

    return installed


_SHIMS = _install_minimal_scientific_shims_if_needed()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def _make_ohlcv_df(
    n_bars: int,
    freq: str = "5min",
    end_time=None,
    trend_step: float = 0.5,
    base_price: float = 60000.0,
):
    if end_time is None:
        end_time = pd.Timestamp("2026-05-01 12:00:00")
    idx = pd.date_range(end=end_time, periods=n_bars, freq=freq)
    arr = np.arange(n_bars, dtype=float)
    sins = np.sin([x * 0.3 for x in arr])
    closes = [base_price + i * trend_step + s * 15.0 for i, s in zip(arr, sins)]
    opens = [c - trend_step * 0.4 for c in closes]
    highs = [max(o, c) + 10.0 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 10.0 for o, c in zip(opens, closes)]
    volumes = [150.0 for _ in range(n_bars)]
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=idx,
    )


class Phase1CriticalFixesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Save existing sys.modules state so other test files remain unaffected
        cls._saved_modules = dict(sys.modules)

        if "database" not in sys.modules:
            db_stub = types.ModuleType("database")
            db_stub.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("DB not available in unit test"))
            db_stub.get_db = lambda: None
            sys.modules["database"] = db_stub

        if "binance" not in sys.modules:
            b_stub = types.ModuleType("binance")
            b_exc = types.ModuleType("binance.exceptions")

            class _APIExc(Exception):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args)
                    self.message = str(args[0]) if args else ""
                    self.code = kwargs.get("code", -1000)

            class _OrdExc(Exception):
                pass

            b_exc.BinanceAPIException = _APIExc
            b_exc.BinanceOrderException = _OrdExc
            b_cli = types.ModuleType("binance.client")

            class _Client:
                def __init__(self, *a, **k):
                    pass

            b_cli.Client = _Client
            sys.modules["binance"] = b_stub
            sys.modules["binance.exceptions"] = b_exc
            sys.modules["binance.client"] = b_cli

        # Load real signal_engine and binance_manager
        sys.modules.pop("signal_engine", None)
        sys.modules.pop("binance_manager", None)
        sys.modules.pop("position_manager", None)
        sys.modules.pop("execution_engine", None)
        sys.modules.pop("log_doctor", None)
        cls.signal_engine_mod = importlib.import_module("signal_engine")
        cls.binance_manager_mod = importlib.import_module("binance_manager")
        cls.trading_config_mod = importlib.import_module("trading_config")
        cls.position_manager_mod = importlib.import_module("position_manager")
        cls.execution_engine_mod = importlib.import_module("execution_engine")
        cls.log_doctor_mod = importlib.import_module("log_doctor")

    @classmethod
    def tearDownClass(cls):
        # Restore sys.modules so subsequent test files see their expected stubs
        for k in list(sys.modules.keys()):
            if k not in cls._saved_modules:
                sys.modules.pop(k, None)
        sys.modules.update(cls._saved_modules)

    def test_unclosed_candle_is_excluded_and_does_not_alter_signal_or_indicators(self):
        """Modifying the currently forming (unclosed) candle must not change any indicator, score, SL/TP, or signal."""
        SignalEngine = self.signal_engine_mod.SignalEngine
        now = pd.Timestamp("2026-05-01 12:03:00")
        df_closed_only = _make_ohlcv_df(120, freq="5min", end_time=pd.Timestamp("2026-05-01 11:55:00"))

        unclosed_normal = pd.DataFrame(
            {"Open": [60060.0], "High": [60080.0], "Low": [60040.0], "Close": [60070.0], "Volume": [200.0]},
            index=[pd.Timestamp("2026-05-01 12:00:00")],
        )
        df_with_normal_unclosed = pd.concat([df_closed_only, unclosed_normal])

        unclosed_extreme = pd.DataFrame(
            {"Open": [60060.0], "High": [95000.0], "Low": [25000.0], "Close": [30000.0], "Volume": [9999999.0]},
            index=[pd.Timestamp("2026-05-01 12:00:00")],
        )
        df_with_extreme_unclosed = pd.concat([df_closed_only, unclosed_extreme])

        res_closed = SignalEngine.analyze(
            df_closed_only, "fr", symbol="BTCUSDT", style="scalping", now=now, timeframe_minutes=5.0
        )
        res_normal = SignalEngine.analyze(
            df_with_normal_unclosed, "fr", symbol="BTCUSDT", style="scalping", now=now, timeframe_minutes=5.0
        )
        res_extreme = SignalEngine.analyze(
            df_with_extreme_unclosed, "fr", symbol="BTCUSDT", style="scalping", now=now, timeframe_minutes=5.0
        )

        # No unintended shift on closed-only DataFrame
        filtered_closed = SignalEngine.filter_closed_candles(df_closed_only, timeframe_minutes=5.0, now=now)
        self.assertEqual(len(filtered_closed), len(df_closed_only))
        self.assertEqual(filtered_closed.index[-1], pd.Timestamp("2026-05-01 11:55:00"))

        # Unclosed candle is stripped from df_with_extreme_unclosed
        filtered_extreme = SignalEngine.filter_closed_candles(df_with_extreme_unclosed, timeframe_minutes=5.0, now=now)
        self.assertEqual(len(filtered_extreme), len(df_closed_only))
        self.assertEqual(filtered_extreme.index[-1], pd.Timestamp("2026-05-01 11:55:00"))

        # Signal, score, SL, TP, and all key indicators are 100% identical
        self.assertEqual(res_closed["signal"], res_extreme["signal"])
        self.assertEqual(res_normal["signal"], res_extreme["signal"])
        self.assertEqual(res_closed["teddy_score"], res_extreme["teddy_score"])
        self.assertEqual(res_closed["sl"], res_extreme["sl"])
        self.assertEqual(res_closed["tp"], res_extreme["tp"])
        for key in ("price", "rsi", "macd", "macd_signal", "adx", "atr", "sma20", "sma50", "bb_upper", "bb_lower", "support", "resistance"):
            self.assertEqual(
                res_closed["indicators"][key],
                res_extreme["indicators"][key],
                f"Indicator {key} was affected by unclosed candle!",
            )

    def test_mtf_never_fakes_4h_or_1d_from_short_5m_window(self):
        """A 500-bar 5m DataFrame (~41 hours) does not have 50 bars of 4h or 1d and must never label 15m/1h as 4h/1d."""
        SignalEngine = self.signal_engine_mod.SignalEngine
        now = pd.Timestamp("2026-05-10 12:00:00")
        df_5m = _make_ohlcv_df(500, freq="5min", end_time=pd.Timestamp("2026-05-10 11:55:00"), trend_step=1.0)

        mtf = SignalEngine._compute_timeframe_trends(df_5m, now=now)
        self.assertEqual(mtf["4h"], "NEUTRE")
        self.assertEqual(mtf["1d"], "NEUTRE")

    def test_mtf_uses_real_htf_data_and_excludes_unclosed_htf_candles(self):
        """When real 1h, 4h, 1d DataFrames are provided, MTF computes true trends and ignores unclosed HTF candles."""
        SignalEngine = self.signal_engine_mod.SignalEngine
        now = pd.Timestamp("2026-05-10 14:30:00")
        df_5m = _make_ohlcv_df(120, freq="5min", end_time=pd.Timestamp("2026-05-10 14:25:00"), trend_step=1.0)

        df_1h = _make_ohlcv_df(80, freq="1h", end_time=pd.Timestamp("2026-05-10 13:00:00"), trend_step=10.0)
        df_4h = _make_ohlcv_df(80, freq="4h", end_time=pd.Timestamp("2026-05-10 08:00:00"), trend_step=40.0)
        df_1d = _make_ohlcv_df(80, freq="1D", end_time=pd.Timestamp("2026-05-09 00:00:00"), trend_step=200.0)

        # Append an unclosed 4h candle (opened at 12:00:00, closes at 16:00:00 > now=14:30:00) with a massive crash
        unclosed_4h_crash = pd.DataFrame(
            {"Open": [63000.0], "High": [63000.0], "Low": [1000.0], "Close": [1000.0], "Volume": [50000.0]},
            index=[pd.Timestamp("2026-05-10 12:00:00")],
        )
        df_4h_with_unclosed = pd.concat([df_4h, unclosed_4h_crash])

        mtf = SignalEngine._compute_timeframe_trends(
            df_5m,
            htf_data={"1h": df_1h, "4h": df_4h_with_unclosed, "1d": df_1d},
            now=now,
        )
        self.assertEqual(mtf["1h"], "HAUSSIER")
        self.assertEqual(mtf["4h"], "HAUSSIER")
        self.assertEqual(mtf["1d"], "HAUSSIER")

    def test_spot_blocks_short_and_uses_spot_api_with_fill_price(self):
        bm = self.binance_manager_mod
        mock_client = MagicMock()
        mock_client.create_order.return_value = {
            "orderId": 77701,
            "clientOrderId": "spot_cid_1",
            "executedQty": "0.05",
            "cummulativeQuoteQty": "3255.0",
            "fills": [{"price": "65100.0", "qty": "0.05"}],
        }

        with patch.object(bm, "_assert_order_context_allowed", return_value=None), \
             patch.object(bm, "_client_for_user", return_value=mock_client), \
             patch.object(bm, "get_symbol_filters", return_value={
                 "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
                 "PRICE_FILTER": {"tickSize": "0.10"},
                 "MIN_NOTIONAL": {"notional": "5.0"},
             }), \
             patch.object(bm, "get_price", return_value=65000.0):

            with self.assertRaises(bm.BinanceClientError):
                bm.open_position(
                    user_id=1,
                    symbol="BTCUSDT",
                    direction="SELL",
                    quantity=0.05,
                    sl_price=66000.0,
                    tp_price=63000.0,
                    market_type="spot",
                    leverage=5,
                    execution_context=bm.ORDER_CONTEXT_AUTOTRADE,
                )

            res = bm.open_position(
                user_id=1,
                symbol="BTCUSDT",
                direction="BUY",
                quantity=0.05,
                sl_price=64000.0,
                tp_price=67000.0,
                market_type="spot",
                leverage=10,
                execution_context=bm.ORDER_CONTEXT_AUTOTRADE,
            )
            mock_client.create_order.assert_called_once()
            mock_client.futures_create_order.assert_not_called()
            self.assertEqual(res["order_id"], 77701)
            self.assertAlmostEqual(res["executed_price"], 65100.0)

    def test_futures_open_position_places_sl_tp_and_extracts_avg_price(self):
        bm = self.binance_manager_mod
        mock_client = MagicMock()
        mock_client.futures_create_order.side_effect = [
            {"orderId": 88801, "clientOrderId": "fut_cid_1", "avgPrice": "64980.50"},
            {"orderId": 88802},
            {"orderId": 88803},
        ]

        with patch.object(bm, "_assert_order_context_allowed", return_value=None), \
             patch.object(bm, "_client_for_user", return_value=mock_client), \
             patch.object(bm, "get_open_binance_positions", return_value=[]), \
             patch.object(bm, "set_leverage", return_value=None) as mock_lev, \
             patch.object(bm, "get_symbol_filters", return_value={
                 "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
                 "PRICE_FILTER": {"tickSize": "0.10"},
                 "MIN_NOTIONAL": {"notional": "5.0"},
             }), \
             patch.object(bm, "get_price", return_value=65000.0):

            res = bm.open_position(
                user_id=1,
                symbol="BTCUSDT",
                direction="SELL",
                quantity=0.05,
                sl_price=66000.0,
                tp_price=63000.0,
                market_type="futures",
                leverage=5,
                execution_context=bm.ORDER_CONTEXT_AUTOTRADE,
            )
            mock_lev.assert_called_once_with(1, "BTCUSDT", 5)
            self.assertEqual(mock_client.futures_create_order.call_count, 3)
            self.assertEqual(res["order_id"], 88801)
            self.assertEqual(res["sl_order_id"], 88802)
            self.assertEqual(res["tp_order_id"], 88803)
            self.assertAlmostEqual(res["executed_price"], 64980.50)

    def test_live_mode_never_uses_testnet_fallback_credentials(self):
        """When user config has testnet=False (Live), get_binance_credentials must not return Testnet env keys."""
        tc = self.trading_config_mod

        class EmptyCursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *args, **kwargs): pass
            def fetchone(self): return None

        class EmptyConn:
            def cursor(self): return EmptyCursor()
            def close(self): pass

        live_cfg = tc.TradingConfig(user_id=99, market_type="futures", testnet=False)
        with patch.object(tc, "get_connection", return_value=EmptyConn()), \
             patch.object(tc, "get_config", return_value=live_cfg), \
             patch.object(tc, "BINANCE_TESTNET", True), \
             patch.object(tc, "DEFAULT_BINANCE_TESTNET_API_KEY", "testnet_key"), \
             patch.object(tc, "DEFAULT_BINANCE_TESTNET_API_SECRET", "testnet_secret"):
            creds = tc.get_binance_credentials(99, market_type="futures")
            self.assertIsNone(creds)

    def test_ensure_config_row_does_not_overwrite_user_settings(self):
        """ensure_config_row must only INSERT ON CONFLICT DO NOTHING and never execute a blanket UPDATE."""
        tc = self.trading_config_mod
        executed_queries = []

        class SpyCursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=None):
                executed_queries.append(sql.strip())

        class SpyConn:
            def cursor(self): return SpyCursor()
            def commit(self): pass
            def close(self): pass

        with patch.object(tc, "get_connection", return_value=SpyConn()):
            tc.ensure_config_row(42)

        self.assertEqual(len(executed_queries), 1)
        self.assertIn("ON CONFLICT (user_id) DO NOTHING", executed_queries[0])
        for q in executed_queries:
            self.assertNotIn("UPDATE trading_config", q)

    def test_trading_config_testnet_field_and_restart_survival(self):
        """TradingConfig uses 'testnet' (no duplicate 'is_testnet'), log_doctor reads cfg.testnet, and config survives restart."""
        tc = self.trading_config_mod
        ld = self.log_doctor_mod

        cfg = tc.TradingConfig(user_id=77, testnet=True)
        self.assertTrue(hasattr(cfg, "testnet"))
        self.assertFalse(hasattr(cfg, "is_testnet"))

        # Simulate DB persistence across restart: update_config -> ensure_config_row on restart -> get_config
        db_state = {
            "row": [
                77, False, 5, 1.5, 2, 72, 4.0, True, 1.2, False, 3, 2.0,
                "BTCUSDT,ETHUSDT", "", "futures", "swing", "1h", 15, False,
                120, 0.0, True, False, None, None, False, None, None, 3600,
            ]
        }

        class StatefulCursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=None):
                q = sql.strip().upper()
                if q.startswith("INSERT INTO TRADING_CONFIG") and "ON CONFLICT (USER_ID) DO NOTHING" in q:
                    # Must not overwrite existing row
                    pass
                elif q.startswith("UPDATE TRADING_CONFIG SET"):
                    # Apply testnet update if present
                    if "TESTNET = %S" in q and params:
                        db_state["row"][18] = bool(params[0])
            def fetchone(self):
                return tuple(db_state["row"])

        class StatefulConn:
            def cursor(self): return StatefulCursor()
            def commit(self): pass
            def close(self): pass

        with patch.object(tc, "get_connection", side_effect=StatefulConn):
            # Simulated restart calls ensure_config_row then get_config
            tc.ensure_config_row(77)
            loaded = tc.get_config(77)
            self.assertEqual(loaded.testnet, False)
            self.assertEqual(loaded.leverage, 5)
            self.assertEqual(loaded.trading_style, "swing")
            self.assertEqual(loaded.symbol_whitelist, ["BTCUSDT", "ETHUSDT"])

            # Verify log_doctor diagnostic reads cfg.testnet without AttributeError
            diag = ld.analyze_logs_locally([], user_id=77)
            checks_text = "\n".join(diag.get("user_checks", []))
            self.assertNotIn("has no attribute 'is_testnet'", checks_text)
            self.assertIn("LIVE RÉEL", checks_text)

    def test_protective_sl_trailing_conflict_with_existing_close_position_order(self):
        """Reproduces 'An open stop or take profit order with GTE and closePosition in the direction is existing'."""
        bm = self.binance_manager_mod
        pm = self.position_manager_mod
        BinanceAPIException = sys.modules["binance.exceptions"].BinanceAPIException

        open_orders_state = [
            {
                "orderId": 5001,
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "STOP_MARKET",
                "stopPrice": "63500.0",
                "closePosition": True,
                "status": "NEW",
            },
            {
                "orderId": 5002,
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": "68000.0",
                "closePosition": True,
                "status": "NEW",
            },
        ]

        mock_client = MagicMock()

        def fake_get_open_orders(symbol=None):
            return [dict(o) for o in open_orders_state if symbol is None or o["symbol"] == symbol]

        def fake_cancel_order(symbol, orderId):
            oid_str = str(orderId)
            open_orders_state[:] = [o for o in open_orders_state if str(o["orderId"]) != oid_str]
            return {"orderId": orderId, "status": "CANCELED"}

        def fake_create_order(**kwargs):
            # Reproduce exact Binance Futures constraint: reject if an open STOP_MARKET with closePosition in same side already exists
            if kwargs.get("type") == "STOP_MARKET" and kwargs.get("closePosition"):
                for existing in open_orders_state:
                    if (
                        existing["symbol"] == kwargs.get("symbol")
                        and existing["side"] == kwargs.get("side")
                        and existing["type"] == "STOP_MARKET"
                        and existing.get("closePosition")
                    ):
                        raise BinanceAPIException(
                            "An open stop or take profit order with GTE and closePosition in the direction is existing.",
                            code=-4130,
                        )
            new_order = {
                "orderId": 5099,
                "symbol": kwargs["symbol"],
                "side": kwargs["side"],
                "type": kwargs["type"],
                "stopPrice": str(kwargs.get("stopPrice")),
                "closePosition": bool(kwargs.get("closePosition")),
                "status": "NEW",
            }
            open_orders_state.append(new_order)
            return new_order

        mock_client.futures_get_open_orders.side_effect = fake_get_open_orders
        mock_client.futures_cancel_order.side_effect = fake_cancel_order
        mock_client.futures_create_order.side_effect = fake_create_order

        with patch.object(bm, "_assert_order_context_allowed", return_value=None), \
             patch.object(bm, "_client_for_user", return_value=mock_client), \
             patch.object(bm, "get_symbol_filters", return_value={
                 "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
                 "PRICE_FILTER": {"tickSize": "0.10"},
                 "MIN_NOTIONAL": {"notional": "5.0"},
             }):
            # Even if old_sl_order_id passed is stale/None while order 5001 exists on Binance,
            # replace_futures_stop_loss_order must detect 5001, cancel it, create 5099, and confirm 5099 is in open_orders.
            new_oid = bm.replace_futures_stop_loss_order(
                user_id=1,
                symbol="BTCUSDT",
                direction="BUY",
                new_sl_price=64200.0,
                old_sl_order_id=None,
                execution_context=bm.ORDER_CONTEXT_AUTOTRADE,
            )
            self.assertEqual(new_oid, "5099")
            active_sl_ids = [o["orderId"] for o in open_orders_state if o["type"] == "STOP_MARKET"]
            self.assertEqual(active_sl_ids, [5099])
            # TP order 5002 must remain untouched
            active_tp_ids = [o["orderId"] for o in open_orders_state if o["type"] == "TAKE_PROFIT_MARKET"]
            self.assertEqual(active_tp_ids, [5002])

            # Also verify that if creation genuinely fails, safety_warn is engaged and NOT cleared in monitor_open_positions
            import asyncio
            trade_row = {
                "id": 11,
                "user_id": 1,
                "symbol": "BTCUSDT",
                "direction": "BUY",
                "entry_price": 64000.0,
                "sl_price": 63500.0,
                "tp_price": 68000.0,
                "quantity": 0.05,
                "leverage": 5,
                "market_type": "futures",
                "sl_order_id": "5099",
                "tp_order_id": "5002",
            }
            cfg = self.trading_config_mod.TradingConfig(user_id=1, auto_trade=True, trailing_stop=True, safety_warn=True)
            warn_calls = []
            clear_calls = []
            async def _noop_flush(*a, **k):
                return None

            with patch.object(pm, "flush_safety_notifications", side_effect=_noop_flush), \
                 patch.object(pm, "get_open_trades", return_value=[trade_row]), \
                 patch.object(pm, "get_config", return_value=cfg), \
                 patch.object(pm, "get_price", return_value=65500.0), \
                 patch.object(pm, "update_trailing_stop", return_value=64800.0), \
                 patch.object(pm, "replace_futures_stop_loss_order", side_effect=bm.BinanceClientError("SL update failed")), \
                 patch.object(pm, "engage_safety_warn", side_effect=lambda uid, msg, context=None: warn_calls.append(msg)), \
                 patch.object(pm, "clear_safety_warn", side_effect=lambda uid: clear_calls.append(uid)):
                asyncio.run(pm.monitor_open_positions(None))
            self.assertEqual(len(warn_calls), 1)
            self.assertEqual(len(clear_calls), 0)

    def test_real_execution_price_used_when_different_from_signal_price(self):
        """Position entry_price and closed PnL must use actual Binance executed_price when signal_price != execution_price."""
        ee = self.execution_engine_mod
        pm = self.position_manager_mod
        tc = self.trading_config_mod

        signal_price = 65000.0
        execution_price = 65125.50
        exit_execution_price = 66125.50

        signal = {
            "id": "manual-execprice1",
            "user_id": 42,
            "symbol": "BTCUSDT",
            "direction": "BUY",
            "entry_price": signal_price,
            "sl": 64000.0,
            "tp": 68000.0,
            "score": 85,
            "created_at": 1700000000.0,
        }
        config = tc.TradingConfig(user_id=42, auto_trade=False, market_type="futures", leverage=2)

        inserted_rows = []
        with patch.object(ee, "calculate_position_size", return_value=0.1), \
             patch.object(ee, "open_position", return_value={
                 "quantity": 0.1,
                 "executed_price": execution_price,
                 "order_id": "9001",
                 "client_order_id": "cid_9001",
                 "sl_order_id": "9002",
                 "tp_order_id": "9003",
             }), \
             patch.object(ee, "mark_signal_status", return_value=None), \
             patch.object(ee, "insert_trade_row", side_effect=lambda **kw: inserted_rows.append(kw) or 55):
            trade = ee.execute_signal(signal, config)

        self.assertNotEqual(signal_price, execution_price)
        self.assertAlmostEqual(trade["entry_price"], execution_price)
        self.assertAlmostEqual(inserted_rows[0]["entry_price"], execution_price)

        # Verify PnL calculation uses the stored real execution_price (65125.50) and real exit price (66125.50)
        # PnL USDT = (66125.50 - 65125.50) * 0.1 = 100.0 USDT (NOT (66125.50 - 65000.0) * 0.1 = 112.55)
        class DummyCursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *args, **kwargs): pass

        class DummyConn:
            def cursor(self): return DummyCursor()
            def commit(self): pass
            def close(self): pass

        with patch.object(pm, "get_connection", return_value=DummyConn()), \
             patch.object(pm, "record_trade_loss", return_value=0.0):
            pnl_usdt, pnl_pct = pm.close_trade(trade, "TP", exit_execution_price)

        self.assertAlmostEqual(pnl_usdt, 100.0, places=4)

    def test_reconciliation_engages_safety_lock_on_critical_divergence(self):
        """A remote Binance position without local DB trade must engage safety_lock."""
        pm = self.position_manager_mod
        lock_calls = []

        with patch.object(pm, "get_open_trades", return_value=[]), \
             patch.object(pm, "get_open_binance_positions", return_value=[{
                 "symbol": "BTCUSDT",
                 "direction": "BUY",
                 "quantity": 0.05,
                 "entry_price": 65000.0,
                 "mark_price": 65100.0,
             }]), \
             patch.object(pm, "get_open_binance_orders", return_value=[]), \
             patch.object(pm, "engage_safe_mode", side_effect=lambda uid, reason, context=None: lock_calls.append((uid, reason))):
            report = pm.reconcile_user_positions(42, startup_mode=False)

        self.assertEqual(report["missing_local"], [("BTCUSDT", "BUY")])
        self.assertEqual(len(lock_calls), 1)
        self.assertEqual(lock_calls[0][0], 42)
        self.assertIn("Divergence critique", lock_calls[0][1])


if __name__ == "__main__":
    unittest.main()
