"""Rapport HTML autonome (CSS/SVG inline, aucune dépendance externe) d'une optimisation."""
from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

CATEGORY_LABELS = {
    "best_raw": "Meilleure performance brute",
    "best_compromise": "Meilleur compromis",
    "best_robust": "Meilleure robustesse",
    "best_overall": "Meilleure configuration globale",
}
FLAG_LABELS = {
    "validation_loss": "Perte en validation alors que le training est gagnant",
    "validation_drop": "Rendement de validation très inférieur au training",
    "oos_collapse": "Effondrement hors échantillon (OOS négatif)",
    "oos_negative": "Rendement hors échantillon négatif (OOS < 0)",
    "oos_profit_factor_below_1": "Profit Factor OOS < 1 malgré un bon training",
    "oos_few_trades": "Très peu de trades en OOS (peu fiable)",
    "isolated_peak": "Pic isolé : les configurations voisines sont nettement moins bonnes",
    "few_training_trades": "Peu de trades en training",
    "validation_unavailable": "Validation indisponible",
    "oos_unavailable": "OOS indisponible",
}
RISK_LABELS = {"low": "faible", "medium": "moyen", "high": "élevé"}
COLORS = ["#10B981", "#38BDF8", "#F59E0B", "#A78BFA", "#94A3B8"]

_CSS = """
body{background:#090D16;color:#E2E8F0;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px}
.wrap{max-width:980px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px;color:#10B981}
h3{font-size:14px;margin:14px 0 6px;color:#CBD5E1}.muted{color:#94A3B8}.card{background:#0F1626;border:1px solid #1E293B;border-radius:10px;padding:12px 14px;margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{padding:5px 8px;border-bottom:1px solid #1E293B;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:#94A3B8;font-weight:600}.scroll{overflow-x:auto}
.pos{color:#10B981}.neg{color:#F43F5E}.warn{color:#F59E0B}.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;border:1px solid #334155}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}.kpi b{display:block;font-size:16px}
ul{margin:6px 0 6px 18px;padding:0}svg{max-width:100%;height:auto}.disc{border-left:3px solid #F59E0B;padding-left:10px}
"""


def e(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def num(v: Any, nd: int = 2, suffix: str = "") -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "N/A"
    if f != f:
        return "N/A"
    return f"{f:,.{nd}f}{suffix}"


def pn(v: Any, nd: int = 2, suffix: str = "") -> str:
    """Nombre coloré (positif/négatif)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "N/A"
    cls = "pos" if f > 0 else ("neg" if f < 0 else "")
    return f'<span class="{cls}">{f:+,.{nd}f}{suffix}</span>'


def _params_str(p: Dict[str, Any]) -> str:
    return ", ".join(f"{e(k)} = <b>{e(v)}</b>" for k, v in p.items()) or "—"


def _metrics_row(label: str, m: Optional[Dict[str, Any]], score: Any = None) -> str:
    if not m or m.get("error"):
        return f"<tr><td>{e(label)}</td>" + "<td>N/A</td>" * 9 + "</tr>"
    return (
        f"<tr><td>{e(label)}</td><td>{pn(m.get('total_return_pct'), 2, '%')}</td><td>{num(m.get('total_trades'), 0)}</td>"
        f"<td>{num(m.get('win_rate_pct'), 1, '%')}</td><td>{num(m.get('profit_factor'))}</td>"
        f"<td>{num(m.get('expectancy_usdt'))}</td><td>-{num(abs(float(m.get('max_drawdown_pct') or 0)), 2, '%')}</td>"
        f"<td>{num(m.get('sharpe_ratio'))}</td><td>{num(m.get('sortino_ratio'))}</td><td>{num(score, 1)}</td></tr>"
    )


_TH = ("<tr><th>Période</th><th>Return</th><th>Trades</th><th>Win Rate</th><th>Profit Factor</th><th>Expectancy ($)</th>"
       "<th>Max DD</th><th>Sharpe</th><th>Sortino</th><th>Score</th></tr>")


def _entry_block(title: str, entry: Dict[str, Any], details: Dict[str, Any], baseline: Optional[Dict[str, Any]]) -> str:
    ov = entry.get("params_full") or entry.get("params") or {}
    flags = entry.get("overfit", {})
    flag_items = "".join(f"<li>{e(FLAG_LABELS.get(f, f))}</li>" for f in flags.get("flags", [])
                         if f not in ("validation_unavailable", "oos_unavailable"))
    mc = (details.get(str(entry["idx"])) or {}).get("monte_carlo_all")
    mc_html = ""
    if mc:
        mc_html = (f"<p class='muted'>Monte Carlo ({mc['n_sims']} rééchantillonnages de {mc['n_trades']} trades réels) : "
                   f"rendement médian {num(mc['return_p50'], 1, '%')} (5ᵉ pct {num(mc['return_p5'], 1, '%')}, 95ᵉ pct {num(mc['return_p95'], 1, '%')}), "
                   f"drawdown 95ᵉ pct {num(mc['max_dd_p95'], 1, '%')}, probabilité de perte {num(mc['prob_loss_pct'], 1, '%')}.</p>")
    nb = entry.get("neighbors", {})
    return (
        f"<div class='card'><h3>{e(title)} <span class='pill'>surapprentissage : {e(RISK_LABELS.get(flags.get('risk'), '?'))}</span></h3>"
        f"<div>{_params_str(ov)}</div><div class='scroll'><table>{_TH}"
        + _metrics_row("Training", entry.get("training"), entry.get("training_score"))
        + _metrics_row("Validation", entry.get("validation"), entry.get("validation_score"))
        + _metrics_row("Out-of-Sample", entry.get("oos"), entry.get("oos_score"))
        + f"</table></div><p class='muted'>Robustesse {num(entry.get('robustness'), 1)} / 100 · cohérence train/val {num(entry.get('consistency'), 2)} · "
        f"stabilité des voisins {num(nb.get('stability'), 2)} (voisins : {nb.get('n', 0)})</p>"
        + (f"<ul class='warn'>{flag_items}</ul>" if flag_items else "") + mc_html + "</div>"
    )


def _equity_svg(series: List[Dict[str, Any]], width: int = 720, height: int = 240) -> str:
    series = [s for s in series if s.get("equity") and len(s["equity"]) > 1]
    if not series:
        return "<p class='muted'>Courbe d'equity indisponible.</p>"
    lo = min(min(s["equity"]) for s in series)
    hi = max(max(s["equity"]) for s in series)
    pad = 28
    span = (hi - lo) or 1.0
    out = [f"<svg viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Courbes d equity OOS'>",
           f"<rect width='{width}' height='{height}' fill='#0F1626' rx='8'/>"]
    for frac in (0, 0.5, 1):
        y = pad + (height - 2 * pad) * (1 - frac)
        out.append(f"<line x1='{pad}' x2='{width - pad}' y1='{y:.1f}' y2='{y:.1f}' stroke='#1E293B'/>")
        out.append(f"<text x='4' y='{y + 4:.1f}' fill='#64748B' font-size='10'>{lo + span * frac:,.0f}</text>")
    for i, s in enumerate(series):
        eq = s["equity"]
        pts = " ".join(
            f"{pad + (width - 2 * pad) * j / (len(eq) - 1):.1f},{pad + (height - 2 * pad) * (1 - (v - lo) / span):.1f}"
            for j, v in enumerate(eq)
        )
        out.append(f"<polyline fill='none' stroke='{COLORS[i % len(COLORS)]}' stroke-width='2' points='{pts}'/>")
        out.append(f"<text x='{pad + 8 + i * 190}' y='16' fill='{COLORS[i % len(COLORS)]}' font-size='11'>{e(s['label'])}</text>")
    out.append("</svg>")
    return "".join(out)


def _sens_svg(item: Dict[str, Any], width: int = 460, height: int = 120) -> str:
    rows = [r for r in item["values"] if r.get("mean_score") is not None]
    if not rows:
        return ""
    vals = [r["mean_score"] for r in rows]
    lo, hi = min(0.0, min(vals)), max(0.0, max(vals))
    span = (hi - lo) or 1.0
    bw = (width - 20) / len(rows)
    base_y = 14 + (height - 34) * (hi / span)
    out = [f"<svg viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg'><rect width='{width}' height='{height}' fill='#0F1626' rx='6'/>"]
    for i, r in enumerate(rows):
        h = (height - 34) * abs(r["mean_score"]) / span
        y = base_y - h if r["mean_score"] >= 0 else base_y
        col = "#10B981" if r["mean_score"] >= 0 else "#F43F5E"
        out.append(f"<rect x='{10 + i * bw + 1:.1f}' y='{y:.1f}' width='{max(1.0, bw - 2):.1f}' height='{max(1.0, h):.1f}' fill='{col}'/>")
        if len(rows) <= 14 or i % max(1, len(rows) // 10) == 0:
            out.append(f"<text x='{10 + i * bw + bw / 2:.1f}' y='{height - 4}' fill='#94A3B8' font-size='9' text-anchor='middle'>{e(r['value'])}</text>")
    out.append("</svg>")
    return "".join(out)


def build_report_html(s: Dict[str, Any]) -> str:
    cats = s.get("categories", {})
    fin = {f["idx"]: f for f in s.get("finalists", [])}
    base = s.get("baseline")
    details = s.get("details", {})
    per = s.get("period", {})
    parts: List[str] = [f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                        f"<title>Optimization Lab — {e(s.get('job_id'))}</title><style>{_CSS}</style></head><body><div class='wrap'>"]
    parts.append(f"<h1>Optimization Lab — {e(s.get('job_id'))}</h1>"
                 f"<div class='muted'>{e(s.get('symbol'))} · {e(s.get('market_type', '').upper())} · {e(s.get('timeframe'))} · style {e(s.get('trading_style'))} · "
                 f"moteur {e(s.get('engine_version'))} / stratégie {e(s.get('strategy_version'))}</div>")
    parts.append(f"<div class='card disc'>{e(s.get('disclaimer'))}</div>")

    # Résumé
    best = fin.get(cats.get("best_overall"))
    parts.append("<h2>Résumé</h2><div class='grid'>"
                 f"<div class='card kpi'><span class='muted'>Configurations testées</span><b>{s.get('n_configs')}</b></div>"
                 f"<div class='card kpi'><span class='muted'>Exploitables (≥ {s.get('min_trades')} trades)</span><b>{s.get('n_scored')}</b></div>"
                 f"<div class='card kpi'><span class='muted'>Méthode</span><b>{e(str(s.get('method')).upper())}</b></div>"
                 f"<div class='card kpi'><span class='muted'>Durée</span><b>{num(s.get('duration_seconds'), 0)} s</b></div></div>")
    if best:
        parts.append(f"<p>Configuration globale la plus équilibrée (training + validation + robustesse) : {_params_str(best.get('params_full') or best['params'])}. "
                     f"Risque de surapprentissage estimé : <b>{e(RISK_LABELS.get(best['overfit']['risk']))}</b>.</p>")
    else:
        parts.append("<p class='warn'>Aucune configuration exploitable n'a été trouvée avec les contraintes actuelles.</p>")

    # Configuration de l'optimisation
    parts.append("<h2>Configuration de l'optimisation</h2><div class='card'>")
    wins = per.get("windows", {})
    parts.append(f"<p>Source de données : {e(s.get('data_source'))} · {per.get('total_candles')} bougies chargées dont {per.get('warmup_candles')} de warm-up · "
                 f"{per.get('simulated_candles')} simulées.</p><ul>"
                 + "".join(f"<li>{lab} : {w.get('candles')} bougies ({e(str(w.get('start'))[:16])} → {e(str(w.get('end'))[:16])})</li>"
                           for lab, w in (("Training (60 %)", wins.get("training", {})), ("Validation (20 %)", wins.get("validation", {})), ("Out-of-Sample (20 %)", wins.get("oos", {}))))
                 + "</ul><div class='scroll'><table><tr><th>Paramètre</th><th>Valeurs testées</th><th>Valeur actuelle</th></tr>")
    for p in s.get("parameters", []):
        vals = p["values"]
        shown = ", ".join(map(str, vals[:14])) + (f" … (+{len(vals) - 14})" if len(vals) > 14 else "")
        parts.append(f"<tr><td>{e(p['key'])}</td><td style='white-space:normal'>{e(shown)}</td><td>{e((s.get('base_params') or {}).get(p['key']))}</td></tr>")
    parts.append("</table></div>")
    parts.append(f"<p class='muted'>{e(s.get('selection_protocol'))}</p></div>")

    # Catégories
    parts.append("<h2>Meilleures configurations</h2>")
    shown_idx = set()
    for key in ("best_overall", "best_raw", "best_compromise", "best_robust"):
        idx = cats.get(key)
        if idx is None or idx not in fin:
            continue
        label = CATEGORY_LABELS[key]
        if idx in shown_idx:
            same = [CATEGORY_LABELS[k] for k in cats if cats[k] == idx and k != key]
            parts.append(f"<div class='card'><h3>{e(label)}</h3><p class='muted'>Identique à la configuration « {e(', '.join(same[:1]) or '—')} » ci-dessus.</p></div>")
            continue
        shown_idx.add(idx)
        parts.append(_entry_block(label, fin[idx], details, base))
    if base:
        parts.append(_entry_block("Configuration actuelle de Bitsure (référence)", base, details, None))

    # Equity OOS
    series = []
    for key in ("best_overall", "best_raw", "best_robust"):
        idx = cats.get(key)
        if idx is not None and not any(sr.get("idx") == idx for sr in series):
            eq = (details.get(str(idx), {}).get("splits", {}).get("oos", {}) or {}).get("equity")
            series.append({"idx": idx, "label": CATEGORY_LABELS[key], "equity": eq})
    bq = (details.get("-1", {}).get("splits", {}).get("oos", {}) or {}).get("equity")
    series.append({"idx": -1, "label": "Configuration actuelle", "equity": bq})
    parts.append("<h2>Courbes d'equity — période Out-of-Sample</h2>" + _equity_svg(series))

    # Top
    parts.append("<h2>Top configurations (finalistes)</h2><div class='scroll'><table><tr><th>#</th><th>Paramètres</th><th>Train</th><th>Val</th><th>OOS</th>"
                 "<th>Score train</th><th>Robustesse</th><th>Risque</th></tr>")
    ranked = sorted(s.get("finalists", []), key=lambda f: -(f.get("compromise") or -1e9))[:20]
    for rank, f in enumerate(ranked, 1):
        def r_(m):
            return pn((m or {}).get("total_return_pct"), 1, "%") if m and not m.get("error") else "N/A"
        parts.append(f"<tr><td>{rank}</td><td style='white-space:normal;text-align:left'>{_params_str(f['params'])}</td><td>{r_(f.get('training'))}</td>"
                     f"<td>{r_(f.get('validation'))}</td><td>{r_(f.get('oos'))}</td><td>{num(f.get('training_score'), 1)}</td>"
                     f"<td>{num(f.get('robustness'), 1)}</td><td>{e(RISK_LABELS.get(f['overfit']['risk']))}</td></tr>")
    parts.append("</table></div>")

    # Sensibilité
    parts.append("<h2>Sensibilité des paramètres (score training moyen par valeur)</h2>")
    for item in s.get("sensitivity", []):
        imp = item.get("importance")
        parts.append(f"<h3>{e(item['key'])} <span class='muted'>— amplitude {num(item.get('spread'), 1)}"
                     f"{' · importance relative ' + num(imp, 2) if imp is not None else ''}</span></h3>{_sens_svg(item)}")

    # Overfitting & conclusions
    parts.append("<h2>Surapprentissage et robustesse</h2><div class='card'><ul>")
    for f in s.get("finalists", [])[:0]:
        pass
    high = [f for f in s.get("finalists", []) if f["overfit"]["risk"] == "high"]
    parts.append(f"<li>{len(high)} finaliste(s) sur {len(s.get('finalists', []))} présentent un risque de surapprentissage élevé (écart training/validation/OOS ou pic isolé).</li>")
    parts.append(f"<li>{s.get('n_configs')} configurations ont été comparées : le meilleur score observé est mécaniquement optimiste (biais de sélection).</li>")
    parts.append(f"<li>Walk-Forward : {e(s.get('walk_forward', {}).get('reason'))}</li></ul></div>")
    if s.get("warnings"):
        parts.append("<h2>Avertissements</h2><div class='card'><ul>" + "".join(f"<li class='warn'>{e(w)}</li>" for w in s["warnings"]) + "</ul></div>")
    parts.append("<h2>Conclusions</h2><div class='card'><p>Privilégiez une configuration dont les voisins directs donnent des résultats proches, dont les performances "
                 "training / validation / OOS restent cohérentes et dont le nombre de trades est suffisant, plutôt que le meilleur rendement isolé. "
                 "Ces résultats décrivent le comportement historique de la stratégie sur la période étudiée ; ils ne prédisent pas le futur et "
                 "ne modifient en rien la configuration live de Bitsure.</p></div></div></body></html>")
    return "".join(parts)
