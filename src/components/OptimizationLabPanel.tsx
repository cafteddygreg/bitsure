import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Play, XCircle, Download, Eye, CheckCircle2, AlertTriangle, FlaskConical, RotateCcw } from 'lucide-react';
import { apiFetch } from '../api';
import { AppLang, tr } from '../i18n';

const API = '/api/admin/strategy-lab/optimization';

interface OptParam {
  key: string;
  type: 'int' | 'float' | 'bool' | 'enum';
  min?: number | null;
  max?: number | null;
  choices?: string[] | null;
  label_fr: string;
  label_en: string;
  model?: string;
  current?: any;
  suggested_step?: number | null;
  active_when?: { param: string; equals: any };
}

interface RangeSel {
  min: string;
  max: string;
  step: string;
  values?: any[];
}

interface OptJob {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  stage?: string;
  created_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  symbol: string;
  timeframe: string;
  method: string;
  total_configs: number;
  done_configs: number;
  progress_pct: number;
  error?: string | null;
  summary?: any;
  plan?: any;
}

interface Props {
  lang?: AppLang | string;
  onShowToast: (type: 'success' | 'error' | 'info', text: string) => void;
  symbol: string;
  timeframe: string;
  tradingStyle: string;
  startDate: string;
  endDate: string;
  baseParams: Record<string, any>;
  onLoadParams?: (params: Record<string, any>) => void;
}

const STATUS_STYLE: Record<string, string> = {
  queued: 'text-[#F59E0B] border-[#F59E0B]/40 bg-[#F59E0B]/10',
  running: 'text-[#38BDF8] border-[#38BDF8]/40 bg-[#38BDF8]/10',
  completed: 'text-[#10B981] border-[#10B981]/40 bg-[#10B981]/10',
  failed: 'text-[#F43F5E] border-[#F43F5E]/40 bg-[#F43F5E]/10',
  cancelled: 'text-[#94A3B8] border-white/20 bg-white/5',
};

const FLAG_LABELS: Record<string, [string, string]> = {
  validation_loss: ['Perte en validation alors que le training est gagnant', 'Validation loss while training is profitable'],
  validation_drop: ['Rendement de validation très inférieur au training', 'Validation return far below training'],
  oos_collapse: ['Effondrement hors échantillon (OOS négatif)', 'Out-of-sample collapse (negative OOS)'],
  oos_profit_factor_below_1: ['Profit Factor OOS < 1 malgré un bon training', 'OOS Profit Factor < 1 despite good training'],
  oos_few_trades: ['Très peu de trades en OOS (peu fiable)', 'Very few OOS trades (unreliable)'],
  isolated_peak: ['Pic isolé : voisins nettement moins bons', 'Isolated peak: neighbours are much worse'],
  few_training_trades: ['Peu de trades en training', 'Few training trades'],
};

const fmt = (v: any, nd = 2, suffix = ''): string => {
  const f = Number(v);
  return v === null || v === undefined || Number.isNaN(f) ? 'N/A' : `${f.toFixed(nd)}${suffix}`;
};

const signed = (v: any, nd = 2, suffix = ''): React.ReactNode => {
  const f = Number(v);
  if (v === null || v === undefined || Number.isNaN(f)) return 'N/A';
  return <span className={f > 0 ? 'text-[#10B981]' : f < 0 ? 'text-[#F43F5E]' : ''}>{`${f > 0 ? '+' : ''}${f.toFixed(nd)}${suffix}`}</span>;
};

const inputCls = 'w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]';

export const OptimizationLabPanel: React.FC<Props> = ({
  lang = 'fr', onShowToast, symbol, timeframe, tradingStyle, startDate, endDate, baseParams, onLoadParams,
}) => {
  const en = lang === 'en';
  const [catalog, setCatalog] = useState<OptParam[]>([]);
  const [limits, setLimits] = useState<any>({ max_configs: 5000, warn_configs: 400, max_params: 8, default_min_trades: 20, default_top_k: 20 });
  const [jobs, setJobs] = useState<OptJob[]>([]);
  const [selected, setSelected] = useState<Record<string, RangeSel>>({});
  const [method, setMethod] = useState<'grid' | 'random'>('grid');
  const [maxConfigs, setMaxConfigs] = useState<string>('200');
  const [minTrades, setMinTrades] = useState<string>('20');
  const [topK, setTopK] = useState<string>('20');
  const [seed, setSeed] = useState<string>('42');
  const [maxCandles, setMaxCandles] = useState<string>('4000');
  const [baseSource, setBaseSource] = useState<'official' | 'editor'>('official');
  const [plan, setPlan] = useState<any | null>(null);
  const [planError, setPlanError] = useState<string>('');
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [activeJob, setActiveJob] = useState<OptJob | null>(null);
  const mounted = useRef(true);

  const label = (p: OptParam) => (en ? p.label_en : p.label_fr);
  const isBusy = (k: string) => !!busy[k];
  const withBusy = useCallback(async (key: string, fn: () => Promise<void>) => {
    setBusy((b) => (b[key] ? b : { ...b, [key]: true }));
    try {
      await fn();
    } finally {
      if (mounted.current) setBusy((b) => ({ ...b, [key]: false }));
    }
  }, []);

  const loadOverview = useCallback(async (silent = true) => {
    try {
      const res = await apiFetch(`${API}/overview?style=${encodeURIComponent(tradingStyle)}`);
      if (!mounted.current) return;
      setCatalog(res.parameters || []);
      setJobs(res.jobs || []);
      if (res.limits) setLimits(res.limits);
    } catch (err: any) {
      if (!silent) onShowToast('error', err.message);
    }
  }, [tradingStyle, onShowToast]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    setSelected({});
    setPlan(null);
    loadOverview(false);
  }, [tradingStyle]); // eslint-disable-line react-hooks/exhaustive-deps

  // Suivi automatique tant qu'une optimisation est en attente ou en cours (le job continue côté serveur même si la page est fermée)
  const hasActive = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!hasActive && !(activeJob && (activeJob.status === 'queued' || activeJob.status === 'running'))) return;
    const t = setInterval(async () => {
      await loadOverview(true);
      if (activeJob) {
        try {
          const r = await apiFetch(`${API}/job?id=${encodeURIComponent(activeJob.job_id)}`);
          if (mounted.current && r.job) setActiveJob(r.job);
        } catch {
          /* silencieux : le prochain cycle réessaiera */
        }
      }
    }, 5000);
    return () => clearInterval(t);
  }, [hasActive, activeJob?.job_id, activeJob?.status, loadOverview]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleParam = (p: OptParam) => {
    setPlan(null);
    setSelected((prev) => {
      if (prev[p.key]) {
        const { [p.key]: _drop, ...rest } = prev;
        return rest;
      }
      if (Object.keys(prev).length >= (limits.max_params || 8)) {
        onShowToast('info', tr(lang, `Maximum ${limits.max_params || 8} paramètres simultanés.`, `Maximum ${limits.max_params || 8} parameters at once.`));
        return prev;
      }
      if (p.type === 'bool') return { ...prev, [p.key]: { min: '', max: '', step: '', values: [true, false] } };
      if (p.type === 'enum') return { ...prev, [p.key]: { min: '', max: '', step: '', values: [...(p.choices || [])] } };
      const step = p.suggested_step || 1;
      const cur = Number(baseSource === 'editor' && baseParams[p.key] !== undefined ? baseParams[p.key] : p.current ?? 0);
      let lo = Math.max(Number(p.min ?? cur - 3 * step), cur - 3 * step);
      let hi = Math.min(Number(p.max ?? cur + 3 * step), cur + 3 * step);
      if (p.type === 'int') {
        lo = Math.round(lo);
        hi = Math.round(hi);
      }
      return { ...prev, [p.key]: { min: String(Number(lo.toFixed(6))), max: String(Number(hi.toFixed(6))), step: String(step) } };
    });
  };

  const updateRange = (key: string, patch: Partial<RangeSel>) => {
    setPlan(null);
    setSelected((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  };

  const buildBody = () => ({
    symbol,
    timeframe,
    trading_style: tradingStyle,
    market_type: 'futures',
    start_date: startDate || '',
    end_date: endDate || '',
    max_candles: Number(maxCandles) || 4000,
    method,
    max_configs: maxConfigs ? Number(maxConfigs) : null,
    seed: Number(seed) || 42,
    min_trades: Number(minTrades) || 20,
    top_k: Number(topK) || 20,
    params: baseSource === 'editor' ? baseParams : {},
    parameters: (Object.entries(selected) as [string, RangeSel][]).map(([key, s]) =>
      s.values ? { key, values: s.values } : { key, min: Number(s.min), max: Number(s.max), step: Number(s.step) }
    ),
  });

  const computePlan = () =>
    withBusy('plan', async () => {
      setPlanError('');
      try {
        const res = await apiFetch(`${API}/plan`, { method: 'POST', body: JSON.stringify(buildBody()) });
        setPlan(res.plan);
      } catch (err: any) {
        setPlan(null);
        setPlanError(err.message);
      }
    });

  const launch = () =>
    withBusy('create', async () => {
      try {
        const planRes = await apiFetch(`${API}/plan`, { method: 'POST', body: JSON.stringify(buildBody()) });
        setPlan(planRes.plan);
        const n = planRes.plan?.n_configs || 0;
        if (n > (limits.warn_configs || 400)) {
          const ok = window.confirm(
            tr(
              lang,
              `${n} configurations vont être testées : l'optimisation peut durer longtemps (elle tourne en arrière-plan). Continuer ?`,
              `${n} configurations will be tested: this may take a long time (runs in the background). Continue?`
            )
          );
          if (!ok) return;
        }
        const res = await apiFetch(`${API}/create`, { method: 'POST', body: JSON.stringify(buildBody()) });
        if (res.ok) {
          onShowToast('success', `${res.job_id} — ${tr(lang, "mise en file d'attente, elle continue même si vous fermez la page.", 'queued, it keeps running even if you close this page.')}`);
          await loadOverview(true);
        }
      } catch (err: any) {
        onShowToast('error', err.message);
      }
    });

  const openJob = (job: OptJob) =>
    withBusy(`open-${job.job_id}`, async () => {
      try {
        const res = await apiFetch(`${API}/job?id=${encodeURIComponent(job.job_id)}`);
        setActiveJob(res.job);
      } catch (err: any) {
        onShowToast('error', err.message);
      }
    });

  const cancelJob = (job: OptJob) =>
    withBusy(`cancel-${job.job_id}`, async () => {
      try {
        const res = await apiFetch(`${API}/cancel`, { method: 'POST', body: JSON.stringify({ id: job.job_id }) });
        if (res.ok) onShowToast('info', res.message || tr(lang, 'Annulation demandée.', 'Cancellation requested.'));
        await loadOverview(true);
      } catch (err: any) {
        onShowToast('error', err.message);
      }
    });

  const fetchReport = async (jobId: string): Promise<{ html: string; filename: string }> => {
    const res = await apiFetch(`${API}/report?id=${encodeURIComponent(jobId)}`);
    return { html: res.html, filename: res.filename || `${jobId}.html` };
  };

  const downloadReport = (job: OptJob) =>
    withBusy(`dl-${job.job_id}`, async () => {
      try {
        const { html, filename } = await fetchReport(job.job_id);
        const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        onShowToast('success', tr(lang, 'Rapport téléchargé.', 'Report downloaded.'));
      } catch (err: any) {
        onShowToast('error', err.message);
      }
    });

  const viewReport = (job: OptJob) =>
    withBusy(`view-${job.job_id}`, async () => {
      try {
        const { html } = await fetchReport(job.job_id);
        const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
        const w = window.open(url, '_blank');
        if (!w) onShowToast('info', tr(lang, "Ouverture bloquée par le navigateur : utilisez « Télécharger ».", 'Popup blocked: use “Download” instead.'));
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      } catch (err: any) {
        onShowToast('error', err.message);
      }
    });

  const grouped = useMemo(() => {
    const out: Record<string, OptParam[]> = {};
    catalog.forEach((p) => {
      const g = p.model || 'other';
      (out[g] = out[g] || []).push(p);
    });
    return out;
  }, [catalog]);

  const GROUP_LABELS: Record<string, [string, string]> = {
    confluence: ['Confluence & filtres', 'Confluence & filters'],
    indicators: ['Indicateurs', 'Indicators'],
    exits: ['Sorties (SL / TP / trailing)', 'Exits (SL / TP / trailing)'],
    other: ['Autres', 'Other'],
  };

  const stageLabel = (s?: string) => {
    const m: Record<string, [string, string]> = {
      queued: ['En attente du worker', 'Waiting for worker'],
      loading_data: ['Chargement des données', 'Loading data'],
      search: ['Recherche (training)', 'Search (training)'],
      validation: ['Validation', 'Validation'],
      oos: ['Out-of-Sample', 'Out-of-Sample'],
      analysis: ['Analyse de robustesse', 'Robustness analysis'],
      finalizing: ['Finalisation', 'Finalizing'],
      completed: ['Terminée', 'Completed'],
    };
    const t = m[s || 'queued'];
    return t ? tr(lang, t[0], t[1]) : s || '';
  };

  const statusLabel = (s: string) => {
    const m: Record<string, [string, string]> = {
      queued: ['En attente', 'Queued'],
      running: ['En cours', 'Running'],
      completed: ['Terminée', 'Completed'],
      failed: ['Échouée', 'Failed'],
      cancelled: ['Annulée', 'Cancelled'],
    };
    return tr(lang, m[s]?.[0] || s, m[s]?.[1] || s);
  };

  const metricRow = (name: string, m: any, score?: any) => (
    <tr key={name} className="border-t border-white/[0.06]">
      <td className="py-1 pr-2 text-left text-[#94A3B8]">{name}</td>
      {!m || m.error ? (
        <td colSpan={8} className="py-1 text-[#64748B]">N/A</td>
      ) : (
        <>
          <td className="py-1 px-1.5 text-right">{signed(m.total_return_pct, 2, '%')}</td>
          <td className="py-1 px-1.5 text-right">{fmt(m.total_trades, 0)}</td>
          <td className="py-1 px-1.5 text-right">{fmt(m.win_rate_pct, 1, '%')}</td>
          <td className="py-1 px-1.5 text-right">{fmt(m.profit_factor)}</td>
          <td className="py-1 px-1.5 text-right">{fmt(m.expectancy_usdt)}</td>
          <td className="py-1 px-1.5 text-right">-{fmt(Math.abs(Number(m.max_drawdown_pct || 0)), 2, '%')}</td>
          <td className="py-1 px-1.5 text-right">{fmt(m.sharpe_ratio)}</td>
          <td className="py-1 pl-1.5 text-right">{fmt(score, 1)}</td>
        </>
      )}
    </tr>
  );

  const renderEntry = (title: string, entry: any) => {
    if (!entry) return null;
    const risk = entry.overfit?.risk as string;
    const riskCls = risk === 'high' ? 'text-[#F43F5E]' : risk === 'medium' ? 'text-[#F59E0B]' : 'text-[#10B981]';
    const riskTxt = risk === 'high' ? tr(lang, 'élevé', 'high') : risk === 'medium' ? tr(lang, 'moyen', 'medium') : tr(lang, 'faible', 'low');
    const flags: string[] = (entry.overfit?.flags || []).filter((f: string) => FLAG_LABELS[f]);
    return (
      <div key={`${title}-${entry.idx}`} className="bg-[#0B1220] border border-white/[0.08] rounded-xl p-3.5 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-semibold text-[#F1F5F9]">{title}</h4>
          <span className={`text-[10px] font-mono-tabular ${riskCls}`}>
            {tr(lang, 'Surapprentissage', 'Overfitting')} : {riskTxt}
          </span>
        </div>
        <div className="text-[11px] font-mono-tabular text-[#CBD5E1] break-words">
          {Object.entries(entry.params_full || entry.params || {}).map(([k, v]) => (
            <span key={k} className="inline-block mr-3">
              {k}=<b className="text-[#10B981]">{String(v)}</b>
            </span>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] font-mono-tabular whitespace-nowrap">
            <thead>
              <tr className="text-[#64748B]">
                <th className="text-left font-normal">{tr(lang, 'Période', 'Period')}</th>
                <th className="text-right font-normal px-1.5">Return</th>
                <th className="text-right font-normal px-1.5">Trades</th>
                <th className="text-right font-normal px-1.5">Win</th>
                <th className="text-right font-normal px-1.5">PF</th>
                <th className="text-right font-normal px-1.5">Exp. $</th>
                <th className="text-right font-normal px-1.5">Max DD</th>
                <th className="text-right font-normal px-1.5">Sharpe</th>
                <th className="text-right font-normal pl-1.5">Score</th>
              </tr>
            </thead>
            <tbody>
              {metricRow('Training', entry.training, entry.training_score)}
              {metricRow('Validation', entry.validation, entry.validation_score)}
              {metricRow('Out-of-Sample', entry.oos, entry.oos_score)}
            </tbody>
          </table>
        </div>
        <div className="text-[10px] text-[#64748B] font-mono-tabular">
          {tr(lang, 'Robustesse', 'Robustness')} {fmt(entry.robustness, 1)}/100 · {tr(lang, 'cohérence train/val', 'train/val consistency')} {fmt(entry.consistency, 2)} ·{' '}
          {tr(lang, 'stabilité des voisins', 'neighbour stability')} {fmt(entry.neighbors?.stability, 2)}
        </div>
        {flags.length > 0 && (
          <ul className="text-[11px] text-[#F59E0B] space-y-0.5">
            {flags.map((f) => (
              <li key={f} className="flex items-start gap-1.5">
                <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                <span>{tr(lang, FLAG_LABELS[f][0], FLAG_LABELS[f][1])}</span>
              </li>
            ))}
          </ul>
        )}
        {onLoadParams && entry.idx !== -1 && (
          <button
            type="button"
            onClick={() => {
              onLoadParams(entry.params || {});
              onShowToast('success', tr(lang, "Paramètres chargés dans l'éditeur du Lab (aucun impact sur le trading live).", 'Parameters loaded in the Lab editor (no live trading impact).'));
            }}
            className="px-2.5 py-1 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-[11px] text-[#F1F5F9] inline-flex items-center gap-1.5"
          >
            <RotateCcw className="w-3 h-3 text-[#10B981]" />
            {tr(lang, "Charger dans l'éditeur du Lab", 'Load into Lab editor')}
          </button>
        )}
      </div>
    );
  };

  const summary = activeJob?.summary;
  const catEntries: [string, string, string][] = [
    ['best_overall', 'Meilleure configuration globale', 'Best overall configuration'],
    ['best_raw', 'Meilleure performance brute', 'Best raw performance'],
    ['best_compromise', 'Meilleur compromis', 'Best trade-off'],
    ['best_robust', 'Meilleure robustesse', 'Best robustness'],
  ];

  return (
    <div className="space-y-6">
      {/* ================= Configuration ================= */}
      <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-4">
        <div>
          <h3 className="font-display text-sm font-semibold text-[#F1F5F9] flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-[#10B981]" />
            Optimization Lab
          </h3>
          <p className="text-xs text-[#94A3B8] mt-1">
            {tr(
              lang,
              "Recherche automatique de paramètres robustes sur le moteur de backtest réel de Strategy Lab. L'optimisation tourne sur un worker séparé : elle continue même si vous fermez cette page. Outil de recherche uniquement : aucune configuration live n'est modifiée, aucun résultat n'est une garantie de rentabilité.",
              'Automatic search for robust parameters on the real Strategy Lab backtest engine. It runs on a separate worker and keeps going if you close this page. Research tool only: no live configuration is modified and no result guarantees profitability.'
            )}
          </p>
          <p className="text-[11px] text-[#64748B] mt-1 font-mono-tabular">
            {symbol} · {timeframe} · {tradingStyle.toUpperCase()} · {startDate || endDate ? `${startDate || '…'} → ${endDate || '…'}` : tr(lang, 'période automatique', 'automatic period')}
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Méthode', 'Method')}</label>
            <select value={method} onChange={(e) => { setMethod(e.target.value as any); setPlan(null); }} className={inputCls}>
              <option value="grid">Grid Search</option>
              <option value="random">Random Search</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-[#94A3B8] mb-1">
              {method === 'random' ? tr(lang, 'Nombre de configurations', 'Number of configurations') : tr(lang, 'Max configurations (garde-fou)', 'Max configurations (guard)')}
            </label>
            <input type="number" min={1} value={maxConfigs} onChange={(e) => { setMaxConfigs(e.target.value); setPlan(null); }} className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Trades minimum (training)', 'Min trades (training)')}</label>
            <input type="number" min={5} value={minTrades} onChange={(e) => setMinTrades(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Finalistes (Top K)', 'Finalists (Top K)')}</label>
            <input type="number" min={3} max={40} value={topK} onChange={(e) => setTopK(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Bougies max', 'Max candles')}</label>
            <input type="number" min={500} max={12000} value={maxCandles} onChange={(e) => setMaxCandles(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-[#94A3B8] mb-1">Seed ({tr(lang, 'reproductibilité', 'reproducibility')})</label>
            <input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} className={inputCls} />
          </div>
          <div className="col-span-2">
            <label className="block text-[11px] text-[#94A3B8] mb-1">{tr(lang, 'Configuration de base / référence', 'Base / reference configuration')}</label>
            <select value={baseSource} onChange={(e) => { setBaseSource(e.target.value as any); setPlan(null); setSelected({}); }} className={inputCls}>
              <option value="official">{tr(lang, 'Preset officiel Bitsure du style (configuration actuelle)', 'Official Bitsure preset for the style (current configuration)')}</option>
              <option value="editor">{tr(lang, "Paramètres actuels de l'éditeur du Lab", 'Current Lab editor parameters')}</option>
            </select>
          </div>
        </div>

        <div className="space-y-3">
          <div className="text-[11px] uppercase font-mono-tabular text-[#64748B]">
            {tr(lang, 'Paramètres à optimiser', 'Parameters to optimise')} ({Object.keys(selected).length}/{limits.max_params})
          </div>
          {(Object.entries(grouped) as [string, OptParam[]][]).map(([group, list]) => (
            <div key={group} className="space-y-1.5">
              <div className="text-[11px] text-[#94A3B8]">{tr(lang, GROUP_LABELS[group]?.[0] || group, GROUP_LABELS[group]?.[1] || group)}</div>
              <div className="flex flex-wrap gap-1.5">
                {list.map((p) => {
                  const on = !!selected[p.key];
                  return (
                    <button
                      key={p.key}
                      type="button"
                      onClick={() => toggleParam(p)}
                      className={`px-2.5 py-1 rounded-lg border text-[11px] ${on ? 'bg-[#10B981]/15 border-[#10B981]/50 text-[#10B981]' : 'bg-[#090D16] border-white/15 text-[#CBD5E1] hover:border-white/30'}`}
                      title={p.key}
                    >
                      {label(p)}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {Object.keys(selected).length > 0 && (
          <div className="space-y-2">
            {catalog.filter((p) => selected[p.key]).map((p) => {
              const s = selected[p.key];
              const cur = baseSource === 'editor' && baseParams[p.key] !== undefined ? baseParams[p.key] : p.current;
              return (
                <div key={p.key} className="bg-[#0B1220] border border-white/[0.08] rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs text-[#F1F5F9]">
                      {label(p)} <span className="text-[#64748B] font-mono-tabular">({p.key})</span>
                    </div>
                    <div className="text-[10px] text-[#64748B] font-mono-tabular">
                      {tr(lang, 'actuel', 'current')} : {String(cur)} {p.min !== null && p.min !== undefined ? `· [${p.min} – ${p.max}]` : ''}
                    </div>
                  </div>
                  {p.type === 'bool' || p.type === 'enum' ? (
                    <div className="text-[11px] text-[#94A3B8] font-mono-tabular">
                      {tr(lang, 'Valeurs testées', 'Tested values')} : {(s.values || []).map(String).join(', ')}
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-2">
                      {(['min', 'max', 'step'] as const).map((f) => (
                        <div key={f}>
                          <label className="block text-[10px] text-[#64748B] mb-0.5 uppercase">{f}</label>
                          <input type="number" step="any" value={s[f]} onChange={(e) => updateRange(p.key, { [f]: e.target.value } as any)} className={inputCls} />
                        </div>
                      ))}
                    </div>
                  )}
                  {p.active_when && String(baseParams[p.active_when.param] ?? '') !== '' && baseSource === 'editor' && baseParams[p.active_when.param] !== p.active_when.equals && (
                    <div className="text-[11px] text-[#F59E0B]">
                      {tr(lang, `Sans effet tant que ${p.active_when.param} ≠ ${String(p.active_when.equals)}.`, `No effect unless ${p.active_when.param} = ${String(p.active_when.equals)}.`)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {planError && (
          <div className="text-xs text-[#F43F5E] bg-[#F43F5E]/10 border border-[#F43F5E]/30 rounded-lg p-2.5 flex items-start gap-2">
            <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>{planError}</span>
          </div>
        )}
        {plan && (
          <div className="text-xs bg-[#0B1220] border border-white/[0.08] rounded-lg p-3 space-y-1.5">
            <div className="text-[#F1F5F9]">
              <b className="text-[#10B981]">{plan.n_configs}</b> {tr(lang, 'configurations à tester', 'configurations to test')}
              {plan.total_grid !== plan.n_configs ? ` (${tr(lang, 'espace total', 'total space')} : ${plan.total_grid})` : ''} · ~{plan.estimated_backtests} {tr(lang, 'backtests', 'backtests')}
            </div>
            {(plan.warnings || []).map((w: string, i: number) => (
              <div key={i} className="text-[#F59E0B] flex items-start gap-1.5">
                <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                <span>{w}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={computePlan}
            disabled={isBusy('plan') || Object.keys(selected).length === 0}
            className="px-3.5 py-2 rounded-lg bg-[#1E293B] hover:bg-[#334155] disabled:opacity-40 border border-white/10 text-xs font-medium text-[#F1F5F9]"
          >
            {isBusy('plan') ? tr(lang, 'Calcul…', 'Computing…') : tr(lang, 'Calculer le nombre de configurations', 'Count configurations')}
          </button>
          <button
            type="button"
            onClick={launch}
            disabled={isBusy('create') || Object.keys(selected).length === 0}
            className="px-5 py-2 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-[#090D16] font-semibold text-xs flex items-center gap-2"
          >
            <Play className={`w-4 h-4 fill-current ${isBusy('create') ? 'animate-pulse' : ''}`} />
            {isBusy('create') ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, "Lancer l'optimisation", 'Start optimization')}
          </button>
        </div>
      </div>

      {/* ================= Historique des jobs ================= */}
      <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-sm font-semibold text-[#F1F5F9]">{tr(lang, 'Optimisations', 'Optimizations')} ({jobs.length})</h3>
          <button type="button" onClick={() => withBusy('refresh', () => loadOverview(false))} disabled={isBusy('refresh')} className="text-[11px] text-[#94A3B8] hover:text-[#F1F5F9] disabled:opacity-50">
            {isBusy('refresh') ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Actualiser', 'Refresh')}
          </button>
        </div>
        {jobs.length === 0 && <div className="text-xs text-[#64748B]">{tr(lang, 'Aucune optimisation pour le moment.', 'No optimization yet.')}</div>}
        <div className="space-y-2">
          {jobs.map((job) => {
            const active = job.status === 'queued' || job.status === 'running';
            return (
              <div key={job.job_id} className={`bg-[#0B1220] border rounded-lg p-3 space-y-2 ${activeJob?.job_id === job.job_id ? 'border-[#10B981]/40' : 'border-white/[0.08]'}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs font-mono-tabular text-[#F1F5F9]">
                    {job.job_id} <span className="text-[#64748B]">· {job.symbol} {job.timeframe} · {String(job.method).toUpperCase()} · {job.total_configs} cfg</span>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${STATUS_STYLE[job.status] || ''}`}>{statusLabel(job.status)}</span>
                </div>
                {active && (
                  <div className="space-y-1">
                    <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                      <div className="h-full bg-[#10B981] transition-all" style={{ width: `${Math.max(2, Math.min(100, job.progress_pct || 0))}%` }} />
                    </div>
                    <div className="text-[10px] text-[#94A3B8] font-mono-tabular">
                      {fmt(job.progress_pct, 0, '%')} · {stageLabel(job.stage)} · {job.done_configs}/{job.total_configs}
                    </div>
                  </div>
                )}
                {job.status === 'failed' && job.error && <div className="text-[11px] text-[#F43F5E] break-words">{job.error}</div>}
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => openJob(job)} disabled={isBusy(`open-${job.job_id}`)} className="px-2.5 py-1 rounded-lg bg-[#1E293B] hover:bg-[#334155] disabled:opacity-50 border border-white/10 text-[11px] text-[#F1F5F9] inline-flex items-center gap-1.5">
                    <Eye className="w-3 h-3" />
                    {isBusy(`open-${job.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Détails', 'Details')}
                  </button>
                  {job.status === 'completed' && (
                    <>
                      <button type="button" onClick={() => viewReport(job)} disabled={isBusy(`view-${job.job_id}`)} className="px-2.5 py-1 rounded-lg bg-[#1E293B] hover:bg-[#334155] disabled:opacity-50 border border-white/10 text-[11px] text-[#F1F5F9]">
                        {isBusy(`view-${job.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Rapport', 'Report')}
                      </button>
                      <button type="button" onClick={() => downloadReport(job)} disabled={isBusy(`dl-${job.job_id}`)} className="px-2.5 py-1 rounded-lg bg-[#1E293B] hover:bg-[#334155] disabled:opacity-50 border border-white/10 text-[11px] text-[#F1F5F9] inline-flex items-center gap-1.5">
                        <Download className="w-3 h-3 text-[#10B981]" />
                        {isBusy(`dl-${job.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Télécharger', 'Download')}
                      </button>
                    </>
                  )}
                  {active && (
                    <button type="button" onClick={() => cancelJob(job)} disabled={isBusy(`cancel-${job.job_id}`)} className="px-2.5 py-1 rounded-lg bg-[#F43F5E]/10 hover:bg-[#F43F5E]/20 disabled:opacity-50 border border-[#F43F5E]/30 text-[11px] text-[#F43F5E]">
                      {isBusy(`cancel-${job.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Annuler', 'Cancel')}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ================= Détails / résultats ================= */}
      {activeJob && (
        <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-display text-sm font-semibold text-[#F1F5F9]">
              {activeJob.job_id} — {activeJob.symbol} {activeJob.timeframe}
            </h3>
            <span className={`text-[10px] px-2 py-0.5 rounded-full border ${STATUS_STYLE[activeJob.status] || ''}`}>{statusLabel(activeJob.status)}</span>
          </div>
          {(activeJob.status === 'queued' || activeJob.status === 'running') && (
            <div className="text-xs text-[#94A3B8]">
              {stageLabel(activeJob.stage)} — {fmt(activeJob.progress_pct, 0, '%')} ({activeJob.done_configs}/{activeJob.total_configs} {tr(lang, 'configurations', 'configurations')}).{' '}
              {tr(lang, 'Vous pouvez fermer cette page : le worker continue.', 'You can close this page: the worker keeps going.')}
            </div>
          )}
          {activeJob.status === 'failed' && <div className="text-xs text-[#F43F5E] break-words">{activeJob.error}</div>}
          {activeJob.status === 'cancelled' && <div className="text-xs text-[#94A3B8]">{tr(lang, 'Optimisation annulée.', 'Optimization cancelled.')}</div>}

          {summary && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono-tabular">
                <div className="bg-[#0B1220] rounded-lg p-2.5"><div className="text-[#64748B]">{tr(lang, 'Configurations', 'Configurations')}</div><div className="text-[#F1F5F9] text-sm">{summary.n_configs}</div></div>
                <div className="bg-[#0B1220] rounded-lg p-2.5"><div className="text-[#64748B]">{tr(lang, 'Exploitables', 'Usable')}</div><div className="text-[#F1F5F9] text-sm">{summary.n_scored}</div></div>
                <div className="bg-[#0B1220] rounded-lg p-2.5"><div className="text-[#64748B]">{tr(lang, 'Durée', 'Duration')}</div><div className="text-[#F1F5F9] text-sm">{fmt(summary.duration_seconds, 0, ' s')}</div></div>
                <div className="bg-[#0B1220] rounded-lg p-2.5"><div className="text-[#64748B]">{tr(lang, 'Erreurs moteur', 'Engine errors')}</div><div className="text-[#F1F5F9] text-sm">{summary.n_errors}</div></div>
              </div>
              {(summary.warnings || []).map((w: string, i: number) => (
                <div key={i} className="text-[11px] text-[#F59E0B] flex items-start gap-1.5"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /><span>{w}</span></div>
              ))}
              {catEntries.map(([key, fr, enTxt]) => {
                const idx = summary.categories?.[key];
                const entry = (summary.finalists || []).find((f: any) => f.idx === idx);
                return renderEntry(tr(lang, fr, enTxt), entry);
              })}
              {summary.baseline && renderEntry(tr(lang, 'Configuration actuelle de Bitsure (référence)', 'Current Bitsure configuration (reference)'), summary.baseline)}

              {(summary.sensitivity || []).length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] uppercase font-mono-tabular text-[#64748B]">{tr(lang, 'Sensibilité des paramètres (score training moyen)', 'Parameter sensitivity (mean training score)')}</div>
                  {(summary.sensitivity || []).map((s: any) => {
                    const rows = (s.values || []).filter((r: any) => r.mean_score !== null && r.mean_score !== undefined);
                    const maxAbs = Math.max(1, ...rows.map((r: any) => Math.abs(r.mean_score)));
                    return (
                      <div key={s.key} className="bg-[#0B1220] rounded-lg p-2.5">
                        <div className="text-[11px] text-[#CBD5E1] mb-1.5">{s.key} <span className="text-[#64748B]">· {tr(lang, 'amplitude', 'spread')} {fmt(s.spread, 1)}</span></div>
                        <div className="flex items-end gap-1 h-14">
                          {rows.map((r: any) => (
                            <div key={String(r.value)} className="flex-1 min-w-[6px] flex flex-col justify-end items-center" title={`${r.value}: ${fmt(r.mean_score, 1)}`}>
                              <div className={`w-full rounded-sm ${r.mean_score >= 0 ? 'bg-[#10B981]' : 'bg-[#F43F5E]'}`} style={{ height: `${Math.max(3, (Math.abs(r.mean_score) / maxAbs) * 100)}%` }} />
                            </div>
                          ))}
                        </div>
                        <div className="flex gap-1 text-[9px] text-[#64748B] font-mono-tabular">
                          {rows.map((r: any) => (<div key={String(r.value)} className="flex-1 min-w-[6px] text-center truncate">{String(r.value)}</div>))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="text-[11px] text-[#94A3B8] border-l-2 border-[#F59E0B]/60 pl-2.5">{summary.disclaimer}</p>
              {activeJob.status === 'completed' && (
                <div className="flex gap-2">
                  <button type="button" onClick={() => viewReport(activeJob)} disabled={isBusy(`view-${activeJob.job_id}`)} className="px-3 py-1.5 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-[#090D16] font-semibold text-xs">
                    {isBusy(`view-${activeJob.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Ouvrir le rapport complet', 'Open full report')}
                  </button>
                  <button type="button" onClick={() => downloadReport(activeJob)} disabled={isBusy(`dl-${activeJob.job_id}`)} className="px-3 py-1.5 rounded-lg bg-[#1E293B] hover:bg-[#334155] disabled:opacity-50 border border-white/10 text-xs text-[#F1F5F9]">
                    {isBusy(`dl-${activeJob.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Télécharger (HTML)', 'Download (HTML)')}
                  </button>
                </div>
              )}
              {activeJob.status === 'completed' && <div className="text-[11px] text-[#10B981] flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3" />{tr(lang, 'Résultats historiques : aucune garantie de rentabilité future.', 'Historical results: no guarantee of future profitability.')}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
