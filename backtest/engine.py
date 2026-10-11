"""Chronological backtest engine independent from the live bot."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

if __package__:
    from .performance import build_summary, export_results
    from .risk_manager import RiskSettings, apply_slippage, calculate_quantity, fee
    from .strategy import BacktestSignalEngine
else:
    from performance import build_summary, export_results
    from risk_manager import RiskSettings, apply_slippage, calculate_quantity, fee
    from strategy import BacktestSignalEngine


def _resolve_git_commit() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
            text=True,
        ).strip()
        return out or None
    except Exception:
        return None


def _utc_day_str(timestamp: Any) -> str:
    try:
        ts = pd.Timestamp(timestamp)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC")
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return str(timestamp)[:10]


@dataclass
class BacktestConfig:
    symbols: List[str]
    timeframes: List[str]
    data_dir: str = "data/binance_futures"
    results_dir: str = "backtest/results"
    style: str = "day"
    initial_capital: float = 10_000.0
    risk_per_trade_pct: float = 1.0
    leverage: float = 1.0
    max_positions: int = 3
    max_daily_loss_pct: float = 5.0
    fees_pct: float = 0.04
    slippage_pct: float = 0.02
    trailing_stop: bool = False
    trailing_stop_pct: float = 1.0
    min_history_bars: int = 60
    same_bar_exit_policy: str = "conservative"
    debug_compare: bool = False
    output_subdir: Optional[str] = None
    extra: Dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict) -> "BacktestConfig":
        known = {field.name for field in cls.__dataclass_fields__.values()}
        values = {k: v for k, v in raw.items() if k in known}
        values["extra"] = {k: v for k, v in raw.items() if k not in known}
        return cls(**values)


class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.risk = RiskSettings(
            initial_capital=config.initial_capital,
            risk_per_trade_pct=config.risk_per_trade_pct,
            leverage=config.leverage,
            max_positions=config.max_positions,
            max_daily_loss_pct=config.max_daily_loss_pct,
            fees_pct=config.fees_pct,
            slippage_pct=config.slippage_pct,
            trailing_stop=config.trailing_stop,
            trailing_stop_pct=config.trailing_stop_pct,
        )
        self.equity = config.initial_capital
        self.open_positions: List[Dict] = []
        self.closed_trades: List[Dict] = []
        self.equity_points: List[Dict] = []
        self.debug_rows: List[Dict] = []
        self.dataset_hashes: Dict[str, str] = {}
        self.last_prices: Dict[str, float] = {}
        self._daily_pnl_day: str = ""
        self._daily_realized_pnl: float = 0.0
        self._day_start_equity: float = config.initial_capital

    def run(self) -> Dict:
        for timeframe in self.config.timeframes:
            datasets: Dict[str, pd.DataFrame] = {}
            for symbol in self.config.symbols:
                df = self._load_data(symbol, timeframe)
                if not df.empty:
                    datasets[symbol] = df
            if datasets:
                self._run_merged_timeline(timeframe, datasets)

        self._close_remaining_positions()
        equity_curve = self._equity_curve()
        primary_tf = self.config.timeframes[0] if self.config.timeframes else None
        metadata = {
            "csv_sha256": dict(self.dataset_hashes),
            "parameters": asdict(self.config),
            "git_commit": _resolve_git_commit(),
        }
        summary = build_summary(
            self.closed_trades,
            equity_curve,
            self.config.initial_capital,
            timeframe=primary_tf,
            metadata=metadata,
        )
        results_dir = self._results_dir()
        export_results(results_dir, self.closed_trades, equity_curve, summary)
        if self.debug_rows:
            pd.DataFrame(self.debug_rows).to_csv(results_dir / "debug_signal_compare.csv", index=False)
        return {
            "summary": summary,
            "trades": self.closed_trades,
            "equity_curve": equity_curve,
            "results_dir": str(results_dir),
        }

    def _resolve_csv_path(self, symbol: str, timeframe: str) -> Optional[Path]:
        candidates = [
            Path(self.config.data_dir) / symbol / f"{symbol}_{timeframe}.csv",
            Path(self.config.data_dir) / f"{symbol}_{timeframe}.csv",
            Path("data") / f"{symbol.replace('USDT', 'USD')}_{timeframe}.csv",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    def _load_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        path = self._resolve_csv_path(symbol, timeframe)
        if path is None or not path.exists():
            return pd.DataFrame()
        try:
            self.dataset_hashes[f"{symbol}_{timeframe}"] = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            pass
        df = pd.read_csv(path)
        date_col = next(
            (c for c in df.columns if c.lower() in {"date", "datetime", "timestamp", "open_time", "opentime"}),
            None,
        )
        if date_col:
            if pd.api.types.is_numeric_dtype(df[date_col]):
                unit = "ms" if df[date_col].astype(float).median() > 10_000_000_000 else "s"
                df[date_col] = pd.to_datetime(df[date_col], unit=unit)
            else:
                df[date_col] = pd.to_datetime(df[date_col])
            df.set_index(date_col, inplace=True)
        rename = {c: c.capitalize() for c in df.columns if c.lower() in ["open", "high", "low", "close", "volume"]}
        df = df.rename(columns=rename)
        return df[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]].astype(float).sort_index()

    def _run_merged_timeline(self, timeframe: str, datasets: Dict[str, pd.DataFrame]) -> None:
        events: List[Tuple[Any, str, int]] = []
        for symbol, df in datasets.items():
            start_idx = min(self.config.min_history_bars, len(df))
            for i in range(start_idx, len(df)):
                events.append((df.index[i], symbol, i))

        events.sort(key=lambda item: (item[0], item[1]))

        for timestamp, symbol, idx in events:
            df = datasets[symbol]
            window = df.iloc[: idx + 1]
            candle = df.iloc[idx]
            self._rollover_utc_day(timestamp)
            self._manage_positions(candle, timestamp, symbol=symbol)
            result = BacktestSignalEngine.analyze(window, symbol=symbol, style=self.config.style)
            self._debug_compare(symbol, timeframe, timestamp, window, result)
            if result.get("signal") in ("BUY", "SELL"):
                self._try_open_position(symbol, timeframe, timestamp, float(candle["Close"]), result)
            self._record_equity(timestamp)

    def _run_market(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        self._run_merged_timeline(timeframe, {symbol: df})

    def _rollover_utc_day(self, timestamp: Any) -> None:
        day_str = _utc_day_str(timestamp)
        if day_str != self._daily_pnl_day:
            self._daily_pnl_day = day_str
            self._daily_realized_pnl = 0.0
            self._day_start_equity = max(self._mark_to_market_equity(), self.equity, self.config.initial_capital * 0.01)

    def _is_daily_loss_limit_reached(self, timestamp: Any) -> bool:
        self._rollover_utc_day(timestamp)
        max_loss_pct = float(getattr(self.risk, "max_daily_loss_pct", 0.0) or 0.0)
        if max_loss_pct <= 0:
            return False
        ref_equity = max(self._day_start_equity, self.equity)
        if ref_equity <= 0:
            return True
        max_loss_usdt = (max_loss_pct / 100.0) * ref_equity
        return self._daily_realized_pnl <= -max_loss_usdt

    def _try_open_position(self, symbol: str, timeframe: str, timestamp, close_price: float, signal: Dict) -> None:
        if len(self.open_positions) >= self.config.max_positions:
            return
        if self._is_daily_loss_limit_reached(timestamp):
            return
        side = signal["signal"]
        entry_side = "BUY" if side == "BUY" else "SELL"
        entry_price = apply_slippage(close_price, entry_side, self.config.slippage_pct)
        sl, tp = float(signal["sl"]), float(signal["tp"])
        qty = calculate_quantity(self.equity, self.config.risk_per_trade_pct, entry_price, sl)
        if qty <= 0:
            return
        notional = entry_price * qty
        margin = notional / self.config.leverage
        entry_fee = fee(notional, self.config.fees_pct)
        if margin + entry_fee > self.equity:
            return
        self.equity -= entry_fee
        initial_risk = abs(entry_price - sl) * qty
        self.last_prices[symbol] = close_price
        self.open_positions.append({
            "id": len(self.closed_trades) + len(self.open_positions) + 1,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": side,
            "entry_time": timestamp,
            "entry_price": entry_price,
            "signal_price": close_price,
            "sl": sl,
            "initial_sl": sl,
            "initial_risk": initial_risk,
            "tp": tp,
            "qty": qty,
            "leverage": self.config.leverage,
            "margin": margin,
            "entry_fee": entry_fee,
            "score": signal.get("teddy_score"),
            "rr_ratio": signal.get("rr_ratio"),
            "status": "open",
            "bars_open": 0,
            "last_seen_time": timestamp,
            "last_seen_price": close_price,
            "prev_close": close_price,
        })

    def _manage_positions(self, candle: pd.Series, timestamp, symbol: Optional[str] = None) -> None:
        high, low, close = float(candle["High"]), float(candle["Low"]), float(candle["Close"])
        if symbol is not None:
            self.last_prices[symbol] = close
        for pos in list(self.open_positions):
            if symbol is not None and pos.get("symbol") != symbol:
                continue
            pos["bars_open"] += 1

            # 1. Trailing Stop calculé UNIQUEMENT avec la clôture de la bougie PRÉCÉDENTE (aucun lookahead sur la bougie courante)
            prev_close = pos.get("prev_close")
            if self.config.trailing_stop and prev_close is not None and pos["bars_open"] >= 2:
                trail = self.config.trailing_stop_pct / 100.0
                if pos["direction"] == "BUY":
                    pos["sl"] = max(pos["sl"], float(prev_close) * (1.0 - trail))
                else:
                    pos["sl"] = min(pos["sl"], float(prev_close) * (1.0 + trail))

            # 2. Vérification SL/TP sur la bougie courante avec le SL déjà en vigueur à l'ouverture de cette bougie
            hit_tp = high >= pos["tp"] if pos["direction"] == "BUY" else low <= pos["tp"]
            hit_sl = low <= pos["sl"] if pos["direction"] == "BUY" else high >= pos["sl"]

            pos["last_seen_time"] = timestamp
            pos["last_seen_price"] = close
            pos["prev_close"] = close

            if not hit_tp and not hit_sl:
                continue
            if hit_tp and hit_sl:
                reason = "SL" if self.config.same_bar_exit_policy == "conservative" else "TP"
            else:
                reason = "TP" if hit_tp else "SL"
            exit_price = pos["tp"] if reason == "TP" else pos["sl"]
            self._close_position(pos, timestamp, exit_price, reason)

    def _close_position(self, pos: Dict, timestamp, exit_price: float, reason: str) -> None:
        self._rollover_utc_day(timestamp)
        exit_side = "SELL" if pos["direction"] == "BUY" else "BUY"
        exec_exit = apply_slippage(exit_price, exit_side, self.config.slippage_pct)
        if pos["direction"] == "BUY":
            pnl_gross = (exec_exit - pos["entry_price"]) * pos["qty"]
        else:
            pnl_gross = (pos["entry_price"] - exec_exit) * pos["qty"]
        exit_fee = fee(exec_exit * pos["qty"], self.config.fees_pct)
        pnl_net = pnl_gross - pos["entry_fee"] - exit_fee
        self.equity += pnl_gross - exit_fee
        self._daily_realized_pnl += pnl_net
        if pos in self.open_positions:
            self.open_positions.remove(pos)
        initial_risk = float(pos.get("initial_risk") or (abs(pos["entry_price"] - pos.get("initial_sl", pos["sl"])) * pos["qty"]) or 0.0)
        r_mult = (pnl_net / initial_risk) if initial_risk > 0 else 0.0
        self.closed_trades.append({
            **pos,
            "exit_time": timestamp,
            "exit_price": exec_exit,
            "exit_reason": reason,
            "exit_fee": exit_fee,
            "pnl_gross": pnl_gross,
            "pnl_net": pnl_net,
            "r_multiple": r_mult,
            "pnl_pct_on_margin": (pnl_net / pos["margin"] * 100) if pos["margin"] else 0.0,
            "duration_bars": pos["bars_open"],
            "status": "closed",
            "equity_after": self.equity,
        })

    def _close_remaining_positions(self) -> None:
        for pos in list(self.open_positions):
            self._close_position(
                pos,
                pos.get("last_seen_time", pos["entry_time"]),
                pos.get("last_seen_price", pos["entry_price"]),
                "END_OF_BACKTEST",
            )

    def _unrealized_pnl(self) -> float:
        latent = 0.0
        for pos in self.open_positions:
            mark_price = float(
                self.last_prices.get(pos["symbol"])
                or pos.get("last_seen_price")
                or pos["entry_price"]
            )
            if pos["direction"] == "BUY":
                latent += (mark_price - pos["entry_price"]) * pos["qty"]
            else:
                latent += (pos["entry_price"] - mark_price) * pos["qty"]
        return latent

    def _mark_to_market_equity(self) -> float:
        return self.equity + self._unrealized_pnl()

    def _record_equity(self, timestamp) -> None:
        mtm_equity = self._mark_to_market_equity()
        self.equity_points.append({
            "timestamp": timestamp,
            "equity": mtm_equity,
            "cash": self.equity,
            "unrealized_pnl": mtm_equity - self.equity,
            "open_positions": len(self.open_positions),
        })

    def _equity_curve(self) -> pd.DataFrame:
        if not self.equity_points:
            return pd.DataFrame(columns=["equity", "cash", "unrealized_pnl", "open_positions"])
        df = pd.DataFrame(self.equity_points)
        df.set_index("timestamp", inplace=True)
        return df

    def _results_dir(self) -> Path:
        base = Path(self.config.results_dir)
        return base / self.config.output_subdir if self.config.output_subdir else base

    def _debug_compare(
        self,
        symbol: str,
        timeframe: str,
        timestamp,
        window: pd.DataFrame,
        simulator_result: Dict,
    ) -> None:
        if not self.config.debug_compare:
            return
        from signal_engine import SignalEngine

        live_result = SignalEngine.analyze(window, symbol=symbol, style=self.config.style)
        bot_sig = live_result.get("signal")
        sim_sig = simulator_result.get("signal")
        bot_score = live_result.get("teddy_score")
        sim_score = simulator_result.get("teddy_score")
        self.debug_rows.append({
            "timestamp": timestamp,
            "symbol": symbol,
            "timeframe": timeframe,
            "bot_signal": bot_sig,
            "simulator_signal": sim_sig,
            "bot_score": bot_score,
            "score": sim_score,
            "match": (bot_sig == sim_sig) and (bot_score == sim_score),
            "reason": simulator_result.get("reason"),
            "bot_reason": live_result.get("reason"),
        })
