"""
Audit decision_log.py — Système explicable de journalisation des décisions de signal (Phase 4).

Fournit une structure standardisée `SignalDecisionRecord` qui trace chaque candidat signal
depuis les indicateurs bruts jusqu'à la décision finale (EXECUTE / REJECT / WAIT), avec :
- symbol, direction, timestamp, timeframe, strategy/style, strategy_version
- raw_conditions (détail de chaque condition technique)
- conditions_passed_count, min_cond_required
- score_initial, score_modifiers, score_final, score_threshold
- indicators (RSI, MACD, MACD_signal, MACD_hist, ADX, +DI, -DI, ATR, ATR%, SMA20, SMA50, BB, Volume, SR)
- mtf_alignment (1h, 4h, 1d)
- sl, tp, sl_pct, rr_ratio
- filters_passed, filters_failed
- rejection_stage, rejection_reason
- execution_checks (daily_loss, max_positions, cooldown, circuit_breaker, exposure)
- final_decision ("BUY", "SELL", "WAIT", "REJECT")

Peut exporter vers JSONL (`logs/signal_decisions.jsonl`) et CSV (`logs/signal_decisions.csv`)
et fournir des statistiques agrégées par motif de rejet.
"""

import csv
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STRATEGY_VERSION = "v4.1-walkforward-validated"


@dataclass
class SignalDecisionRecord:
    symbol: str
    direction: str  # "BUY", "SELL", "WAIT"
    timestamp: str
    timeframe: str
    style: str
    strategy_version: str = STRATEGY_VERSION

    # Conditions brutes
    raw_conditions: Dict[str, bool] = field(default_factory=dict)
    conditions_passed_count: int = 0
    min_cond_required: int = 4

    # Score & Modificateurs
    score_initial: float = 0.0
    score_components: Dict[str, float] = field(default_factory=dict)
    score_modifiers: Dict[str, float] = field(default_factory=dict)
    score_final: int = 0
    score_threshold: int = 75

    # Indicateurs clés
    rsi: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    adx: float = 0.0
    adx_prev: float = 0.0
    adx_rising: bool = False
    plus_di: float = 0.0
    minus_di: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    price: float = 0.0
    sma20: float = 0.0
    sma50: float = 0.0
    trend: str = "NEUTRE"
    support: Optional[float] = None
    resistance: Optional[float] = None
    distance_to_sr_pct: Optional[float] = None
    volume_ratio: float = 1.0
    pullback_pct: float = 0.0
    extension_atr: float = 0.0

    # Multi-timeframe
    mtf_alignment: Dict[str, str] = field(default_factory=dict)

    # Risk / Reward & SL / TP
    sl: Optional[float] = None
    tp: Optional[float] = None
    sl_distance_pct: float = 0.0
    rr_ratio: float = 0.0

    # Filtres & Décision
    filters_passed: List[str] = field(default_factory=list)
    filters_failed: List[str] = field(default_factory=list)
    rejection_stage: Optional[str] = None  # "CONDITIONS", "SIGNAL_FILTER", "SCORE_FILTER", "EXECUTION_SAFETY", "RISK_SIZING"
    rejection_reason: Optional[str] = None
    final_decision: str = "WAIT"  # "BUY", "SELL", "WAIT", "REJECT"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_flat_row(self) -> Dict[str, Any]:
        """Retourne une ligne aplatie pour export CSV."""
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "style": self.style,
            "strategy_version": self.strategy_version,
            "direction": self.direction,
            "final_decision": self.final_decision,
            "rejection_stage": self.rejection_stage or "NONE",
            "rejection_reason": self.rejection_reason or "NONE",
            "conditions_passed": f"{self.conditions_passed_count}/{self.min_cond_required}",
            "score_initial": round(self.score_initial, 1),
            "score_final": self.score_final,
            "score_threshold": self.score_threshold,
            "price": round(self.price, 6),
            "rsi": round(self.rsi, 2),
            "macd_hist": round(self.macd_hist, 6),
            "adx": round(self.adx, 2),
            "adx_rising": self.adx_rising,
            "plus_di": round(self.plus_di, 2),
            "minus_di": round(self.minus_di, 2),
            "atr_pct": round(self.atr_pct, 4),
            "trend": self.trend,
            "mtf_1h": self.mtf_alignment.get("1h", "N/A"),
            "mtf_4h": self.mtf_alignment.get("4h", "N/A"),
            "mtf_1d": self.mtf_alignment.get("1d", "N/A"),
            "sl": round(self.sl, 6) if self.sl else "",
            "tp": round(self.tp, 6) if self.tp else "",
            "sl_distance_pct": round(self.sl_distance_pct, 4),
            "rr_ratio": round(self.rr_ratio, 2),
            "filters_passed": "|".join(self.filters_passed),
            "filters_failed": "|".join(self.filters_failed),
        }


class SignalDecisionJournal:
    """Gestionnaire de journal de décisions explicables (mémoire + JSONL/CSV)."""

    def __init__(self, jsonl_path: str = "logs/signal_decisions.jsonl", max_memory: int = 1000):
        self.jsonl_path = jsonl_path
        self.max_memory = max_memory
        self.records: List[SignalDecisionRecord] = []

    def record(self, decision: SignalDecisionRecord, persist: bool = True) -> None:
        self.records.append(decision)
        if len(self.records) > self.max_memory:
            self.records = self.records[-self.max_memory :]
        if persist and self.jsonl_path:
            try:
                os.makedirs(os.path.dirname(self.jsonl_path), exist_ok=True)
                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")
            except Exception:
                pass

    def export_csv(self, csv_path: str) -> None:
        if not self.records:
            return
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        rows = [r.to_flat_row() for r in self.records]
        fieldnames = list(rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def summarize_rejections(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self.records:
            key = f"{r.final_decision}:{r.rejection_stage or 'OK'}:{r.rejection_reason or 'ACCEPTED'}"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


# Instance partagée par défaut
decision_journal = SignalDecisionJournal()
