"""Notifications Telegram de l'Optimization Lab (Bot API avec le TELEGRAM_TOKEN existant).

Le worker est un processus séparé du bot : il n'utilise pas l'Application du bot mais l'API HTTP Telegram
avec le même token (envois sortants uniquement, sans polling → aucun conflit avec le bot principal).
Ne lève jamais d'exception : une notification qui échoue ne doit pas faire échouer un job.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger("optimization.notify")

_API = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 20


def _token() -> str:
    try:
        from config import TELEGRAM_TOKEN
        return TELEGRAM_TOKEN or ""
    except Exception:
        return ""


def send_message(chat_id: int, text: str) -> bool:
    token = _token()
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            _API.format(token=token, method="sendMessage"),
            json={"chat_id": int(chat_id), "text": text[:4000], "disable_web_page_preview": True},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning("Telegram sendMessage HTTP %s", r.status_code)
        return r.status_code == 200
    except Exception as exc:  # réseau, DNS, etc.
        logger.warning("Telegram sendMessage échec: %s", type(exc).__name__)
        return False


def send_document(chat_id: int, content: bytes, filename: str, caption: Optional[str] = None) -> bool:
    token = _token()
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            _API.format(token=token, method="sendDocument"),
            data={"chat_id": int(chat_id), "caption": (caption or "")[:1000]},
            files={"document": (filename, content, "text/html")},
            timeout=60,
        )
        if r.status_code != 200:
            logger.warning("Telegram sendDocument HTTP %s", r.status_code)
        return r.status_code == 200
    except Exception as exc:
        logger.warning("Telegram sendDocument échec: %s", type(exc).__name__)
        return False


class TelegramJobNotifier:
    """Messages de cycle de vie d'un job (début, progression espacée, erreur, annulation, fin + rapport)."""

    def __init__(self, sender=None, doc_sender=None):
        self._send = sender or send_message
        self._send_doc = doc_sender or send_document

    def started(self, chat_id: int, job_id: str, req: dict, n_configs: int, resumed: bool = False) -> None:
        head = "Optimization Worker resumed" if resumed else "Optimization Worker started"
        self._send(chat_id, f"🧪 {head}\n{job_id} · {req.get('symbol')} {req.get('timeframe')} · "
                            f"{n_configs} configurations ({str(req.get('method', 'grid')).upper()})")

    def progress(self, chat_id: int, job_id: str, stage: str, pct: float, done_configs: int) -> None:
        self._send(chat_id, f"⏳ {job_id} — {pct:.0f} % (étape : {stage}, {done_configs} configurations évaluées)")

    def failed(self, chat_id: int, job_id: str, stage: str, error: str) -> None:
        self._send(chat_id, f"❌ {job_id} — échec à l'étape « {stage} » : {error[:300]}\nLe job est arrêté (relancez-le depuis Strategy Lab).")

    def cancelled(self, chat_id: int, job_id: str) -> None:
        self._send(chat_id, f"⏹ {job_id} — optimisation annulée.")

    def finished(self, chat_id: int, job_id: str, summary: dict, report_html: str) -> None:
        cats = summary.get("categories", {})
        fin = {f["idx"]: f for f in summary.get("finalists", [])}

        def line(label: str, key: str) -> str:
            f = fin.get(cats.get(key))
            if not f:
                return f"{label} : N/A"
            t, o = f.get("training") or {}, f.get("oos") or {}
            return (f"{label} : {f.get('params')} — train {t.get('total_return_pct', 'N/A')} % · "
                    f"OOS {o.get('total_return_pct', 'N/A') if o and not o.get('error') else 'N/A'} %")

        best = fin.get(cats.get("best_overall"))
        oos_txt = ""
        if best and best.get("oos") and not best["oos"].get("error"):
            oos_txt = (f"\nOOS (meilleure globale) : {best['oos'].get('total_return_pct')} % sur {best['oos'].get('total_trades')} trades, "
                       f"PF {best['oos'].get('profit_factor')}")
        self._send(chat_id, (
            f"✅ {job_id} terminé\n{summary.get('symbol')} · {summary.get('timeframe')} · {summary.get('n_configs')} configurations · "
            f"{summary.get('duration_seconds')} s\n"
            f"{line('Meilleure performance', 'best_raw')}\n{line('Meilleure robustesse', 'best_robust')}\n"
            f"{line('Meilleure globale', 'best_overall')}{oos_txt}\nRésultats historiques, non prédictifs. Rapport disponible dans Strategy Lab."
        ))
        self._send_doc(chat_id, report_html.encode("utf-8"), f"{job_id}.html", f"Rapport {job_id}")
