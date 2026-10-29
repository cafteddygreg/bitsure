import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Play, XCircle, Download, Eye, CheckCircle2, AlertTriangle, FlaskConical, RotateCcw } from 'lucide-react';
import { apiFetch } from '../api';
import { AppLang, tr } from '../i18n';
import { InfoTip, StatusBadge, EmptyState } from './ui';
import { useGlobalStrategyConfig } from '../strategyConfigStore';

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
  onLoadParams?: (params: Record<string, any>, context?: Record<string, any>) => void;
}

const STATUS_TONE: Record<string, 'neutral' | 'positive' | 'negative' | 'warning' | 'info'> = {
  queued: 'warning',
  running: 'info',
  completed: 'positive',
  failed: 'negative',
  cancelled: 'neutral',
};

const STATUS_STYLE: Record<string, string> = {
  queued: 'text-[#D6A84F] border-[#D6A84F]/40 bg-[#D6A84F]/10',
  running: 'text-[#4EA1FF] border-[#4EA1FF]/40 bg-[#4EA1FF]/10',
  completed: 'text-[#20C997] border-[#20C997]/40 bg-[#20C997]/10',
  failed: 'text-[#F04438] border-[#F04438]/40 bg-[#F04438]/10',
  cancelled: 'text-[#8B98A4] border-white/20 bg-white/5',
};

const FLAG_LABELS: Record<string, [string, string]> = {
  validation_loss: ['Perte en validation alors que le training est gagnant', 'Validation loss while training is profitable'],
  validation_drop: ['Rendement de validation très inférieur au training', 'Validation return far below training'],
  oos_collapse: ['Effondrement hors échantillon (OOS négatif)', 'Out-of-sample collapse (negative OOS)'],
  oos_negative: ['Rendement hors échantillon négatif (OOS < 0)', 'Negative out-of-sample return (OOS < 0)'],
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
  return <span className={f > 0 ? 'text-[#20C997]' : f < 0 ? 'text-[#F04438]' : ''}>{`${f > 0 ? '+' : ''}${f.toFixed(nd)}${suffix}`}</span>;
};

// Nombre de valeurs candidates d'un paramètre (même formule que le backend) — null si la saisie est incomplète/invalide.
const countValues = (s: RangeSel | undefined): number | null => {
  if (!s) return null;
  if (s.values) return s.values.length;
  if (s.min === '' || s.max === '' || s.step === '') return null;
  const lo = Number(s.min);
  const hi = Number(s.max);
  const st = Number(s.step);
  if ([lo, hi, st].some((x) => Number.isNaN(x)) || st <= 0 || hi < lo) return null;
  return Math.floor((hi - lo) / st + 1e-9) + 1;
};

const formatDuration = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds <= 0) return '—';
  if (seconds < 90) return `${Math.round(seconds)} s`;
  const minutes = seconds / 60;
  if (minutes < 90) return `${Math.round(minutes)} min`;
  const h = Math.floor(minutes / 60);
  return `${h} h ${String(Math.round(minutes - h * 60)).padStart(2, '0')} min`;
};

const inputCls = 'w-full px-2.5 py-1.5 bg-[#080C0F] border border-white/15 rounded-lg text-xs text-[#E8EEF2]';

export const OptimizationLabPanel: React.FC<Props> = ({
  lang = 'fr', onShowToast, symbol, timeframe, tradingStyle, startDate, endDate, baseParams, onLoadParams,
}) => {
  const en = lang === 'en';
  const [catalog, setCatalog] = useState<OptParam[]>([]);
  const [limits, setLimits] = useState<any>({ max_configs: 20000, warn_configs: 1000, max_params: 12, default_min_trades: 20, default_top_k: 20 });
  const [jobs, setJobs] = useState<OptJob[]>([]);
  const [selected, setSelected] = useState<Record<string, RangeSel>>({});
  const [method, setMethod] = useState<'grid' | 'random'>('grid');
  const [maxConfigs, setMaxConfigs] = useState<string>('200');
  const [minTrades, setMinTrades] = useState<string>('20');
  const [topK, setTopK] = useState<string>('20');
  const [seed, setSeed] = useState<string>('42');
  const [maxCandles, setMaxCandles] = useState<string>('4000');
  // Source de Vérité : configuration validée / sauvegardée dans le Strategy Lab (état global + localStorage).
  const globalCfg = useGlobalStrategyConfig();
  const globalApplies = !!globalCfg && globalCfg.tradingStyle === tradingStyle;
  const [baseSource, setBaseSource] = useState<'global' | 'official' | 'editor'>(() => (globalApplies ? 'global' : 'official'));
  const [plan, setPlan] = useState<any | null>(null);
  const [planError, setPlanError] = useState<string>('');
  const [lastDelta, setLastDelta] = useState<{ text: string; tone: 'add' | 'remove' } | null>(null);
  const planReq = useRef(0);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [activeJob, setActiveJob] = useState<OptJob | null>(null);
  const mounted = useRef(true);
  // Horloge locale (1 s) uniquement pendant qu'un job est actif : alimente durée écoulée et ETA approximatif.
  const [nowSec, setNowSec] = useState<number>(() => Date.now() / 1000);
  const jobIsActive = Boolean(activeJob && (activeJob.status === 'queued' || activeJob.status === 'running'));
  useEffect(() => {
    if (!jobIsActive) return;
    const t = window.setInterval(() => setNowSec(Date.now() / 1000), 1000);
    return () => window.clearInterval(t);
  }, [jobIsActive]);
  // Refs : le parent recrée `onShowToast` à chaque rendu (prix en direct) ; sans refs, le minuteur de suivi
  // serait réinitialisé en permanence et ne se déclencherait jamais.
  const onShowToastRef = useRef(onShowToast);
  onShowToastRef.current = onShowToast;
  const activeJobRef = useRef<OptJob | null>(null);
  activeJobRef.current = activeJob;
  const styleRef = useRef(tradingStyle);
  styleRef.current = tradingStyle;
  const langRef = useRef(lang);
  langRef.current = lang;
  const prevStatus = useRef<Record<string, string>>({});

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

  const notifyTransitions = (list: OptJob[]) => {
    const prev = prevStatus.current;
    const l = langRef.current;
    list.forEach((j) => {
      const before = prev[j.job_id];
      if (before && (before === 'queued' || before === 'running') && before !== j.status) {
        if (j.status === 'completed') onShowToastRef.current('success', `${j.job_id} — ${tr(l, 'optimisation terminée.', 'optimization completed.')}`);
        else if (j.status === 'failed') onShowToastRef.current('error', `${j.job_id} — ${tr(l, 'optimisation échouée', 'optimization failed')}${j.error ? ` : ${j.error}` : ''}`);
        else if (j.status === 'cancelled') onShowToastRef.current('info', `${j.job_id} — ${tr(l, 'optimisation annulée.', 'optimization cancelled.')}`);
      }
      prev[j.job_id] = j.status;
    });
  };

  const loadOverview = useCallback(async (silent = true, light = false) => {
    try {
      const res = await apiFetch(`${API}/overview?style=${encodeURIComponent(styleRef.current)}${light ? '&light=1' : ''}`, { cache: 'no-store' });
      if (!mounted.current) return;
      if (!light) {
        setCatalog(res.parameters || []);
        if (res.limits) setLimits(res.limits);
      }
      const list: OptJob[] = res.jobs || [];
      notifyTransitions(list);
      setJobs(list);
    } catch (err: any) {
      if (!silent) onShowToastRef.current('error', err.message);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshActiveJob = useCallback(async () => {
    const current = activeJobRef.current;
    if (!current) return;
    try {
      const r = await apiFetch(`${API}/job?id=${encodeURIComponent(current.job_id)}`, { cache: 'no-store' });
      if (mounted.current && r.job) setActiveJob(r.job);
    } catch {
      /* silencieux : le prochain cycle réessaiera */
    }
  }, []);

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

  // Suivi automatique (toutes les 3 s) tant qu'une optimisation est en attente ou en cours : le job continue côté serveur
  // même si la page est fermée. Le minuteur ne dépend que d'un booléen stable (pas de réinitialisation à chaque rendu).
  const isActiveStatus = (st?: string) => st === 'queued' || st === 'running';
  const needsPolling = jobs.some((j) => isActiveStatus(j.status)) || isActiveStatus(activeJob?.status);
  useEffect(() => {
    if (!needsPolling) return;
    const tick = () => {
      loadOverview(true, true);
      refreshActiveJob();
    };
    const t = setInterval(tick, 3000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') tick();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(t);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [needsPolling, loadOverview, refreshActiveJob]);

  // Paramètres de référence effectifs (clé → valeur) selon la source choisie ; {} = preset officiel du backend.
  const resolvedBase = useMemo<Record<string, any>>(() => {
    if (baseSource === 'global') return globalApplies && globalCfg ? globalCfg.params : {};
    if (baseSource === 'editor') return baseParams;
    return {};
  }, [baseSource, globalApplies, globalCfg, baseParams]);
  const baseValue = (p: OptParam) => (resolvedBase[p.key] !== undefined ? resolvedBase[p.key] : p.current);

  // À chaque nouvelle config globale (ou changement de style) : on la reprend comme point de départ des tests.
  const globalStamp = globalApplies && globalCfg ? globalCfg.updatedAt : 0;
  useEffect(() => {
    setPlan(null);
    setBaseSource((cur) => (globalStamp ? 'global' : cur === 'global' ? 'official' : cur));
  }, [globalStamp]);

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
      const cur = Number(baseValue(p) ?? 0);
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
    params: resolvedBase,
    parameters: (Object.entries(selected) as [string, RangeSel][]).map(([key, s]) =>
      s.values ? { key, values: s.values } : { key, min: Number(s.min), max: Number(s.max), step: Number(s.step) }
    ),
  });

  const computePlan = () =>
    withBusy('plan', async () => {
      const id = ++planReq.current;
      try {
        const res = await apiFetch(`${API}/plan`, { method: 'POST', body: JSON.stringify(buildBody()) });
        if (id !== planReq.current) return; // réponse périmée : une saisie plus récente est en cours
        setPlanError('');
        setPlan(res.plan);
      } catch (err: any) {
        if (id !== planReq.current) return;
        setPlan(null);
        setPlanError(err.message);
      }
    });

  // Décompte en direct : calcul instantané côté interface + comptage exact côté serveur (après filtrage des
  // combinaisons incohérentes) quelques instants après la dernière modification.
  const selectedParams = catalog.filter((p) => selected[p.key]);
  const counts = selectedParams.map((p) => countValues(selected[p.key]));
  const complete = counts.length > 0 && counts.every((c) => c !== null);
  const gridTotal: number | null = complete ? (counts as number[]).reduce((a, b) => a * b, 1) : null;
  const requested = Number(maxConfigs) || 200;
  const liveTotal: number | null = gridTotal === null ? null : method === 'random' ? Math.min(requested, gridTotal) : gridTotal;
  const overLimit = method === 'grid' && gridTotal !== null && gridTotal > (limits.max_configs || 20000);
  const overWarn = liveTotal !== null && liveTotal > (limits.warn_configs || 1000);
  const planKey = JSON.stringify([selected, method, maxConfigs, maxCandles, minTrades, topK, seed, baseSource, globalStamp, symbol, timeframe, tradingStyle, startDate, endDate]);
  useEffect(() => {
    if (Object.keys(selected).length === 0) {
      planReq.current += 1;
      setPlan(null);
      setPlanError('');
      return;
    }
    const t = setTimeout(() => {
      computePlan();
    }, 600);
    return () => clearTimeout(t);
  }, [planKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!lastDelta) return;
    const t = setTimeout(() => setLastDelta(null), 5000);
    return () => clearTimeout(t);
  }, [lastDelta]);

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
      <td className="py-1 pr-2 text-left text-[#8B98A4]">{name}</td>
      {!m || m.error ? (
        <td colSpan={8} className="py-1 text-[#6E7B88]">N/A</td>
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
    const riskCls = risk === 'high' ? 'text-[#F04438]' : risk === 'medium' ? 'text-[#D6A84F]' : 'text-[#20C997]';
    const riskTxt = risk === 'high' ? tr(lang, 'élevé', 'high') : risk === 'medium' ? tr(lang, 'moyen', 'medium') : tr(lang, 'faible', 'low');
    const flags: string[] = (entry.overfit?.flags || []).filter((f: string) => FLAG_LABELS[f]);
    return (
      <div key={`${title}-${entry.idx}`} className="bg-[#0D1318] border border-white/[0.08] rounded-xl p-3.5 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-semibold text-[#E8EEF2]">{title}</h4>
          <span className={`text-[10px] font-mono-tabular ${riskCls}`}>
            {tr(lang, 'Surapprentissage', 'Overfitting')} : {riskTxt}
          </span>
        </div>
        <div className="text-[11px] font-mono-tabular text-[#E8EEF2] break-words">
          {Object.entries(entry.params_full || entry.params || {}).map(([k, v]) => (
            <span key={k} className="inline-block mr-3">
              {k}=<b className="text-[#20C997]">{String(v)}</b>
            </span>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] font-mono-tabular whitespace-nowrap">
            <thead>
              <tr className="text-[#6E7B88]">
                <th className="text-left font-normal">{tr(lang, 'Période', 'Period')}</th>
                <th className="text-right font-normal px-1.5">{tr(lang, 'Rendement', 'Return')}</th>
                <th className="text-right font-normal px-1.5">Trades</th>
                <th className="text-right font-normal px-1.5">{tr(lang, 'Gain', 'Win')}</th>
                <th className="text-right font-normal px-1.5">PF</th>
                <th className="text-right font-normal px-1.5">{tr(lang, 'Espér. $', 'Exp. $')}</th>
                <th className="text-right font-normal px-1.5">{tr(lang, 'DD max', 'Max DD')}</th>
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
        <div className="text-[10px] text-[#6E7B88] font-mono-tabular">
          {tr(lang, 'Robustesse', 'Robustness')} <InfoTip term="robustness" lang={lang} /> {fmt(entry.robustness, 1)}/100 · {tr(lang, 'cohérence train/val', 'train/val consistency')} {fmt(entry.consistency, 2)} ·{' '}
          {tr(lang, 'stabilité des voisins', 'neighbour stability')} <InfoTip term="neighbors" lang={lang} /> {fmt(entry.neighbors?.stability, 2)}
        </div>
        {flags.length > 0 && (
          <ul className="text-[11px] text-[#D6A84F] space-y-0.5">
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
              // Contexte complet de la course (symbole, timeframe, style, période, config de base) : on recharge
              // EXACTEMENT ce qui a été testé, pas seulement les paramètres balayés.
              onLoadParams(entry.params_full || entry.params || {}, {
                symbol: summary?.symbol,
                timeframe: summary?.timeframe,
                trading_style: summary?.trading_style,
                base_params_full: summary?.base_params_full,
                start_date: summary?.request_period?.start_date,
                end_date: summary?.request_period?.end_date,
                max_candles: summary?.request_period?.max_candles,
              });
              onShowToast('success', tr(lang, "Paramètres chargés dans l'éditeur du Lab (aucun impact sur le trading live).", 'Parameters loaded in the Lab editor (no live trading impact).'));
            }}
            className="px-2.5 py-1 rounded-lg bg-[#172129] hover:bg-[#202A32] border border-white/10 text-[11px] text-[#E8EEF2] inline-flex items-center gap-1.5"
          >
            <RotateCcw className="w-3 h-3 text-[#20C997]" />
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

  // ---- Comparaison côte à côte : configuration actuelle (référence) vs meilleures configurations ----
  const renderCompare = () => {
    const base = summary?.baseline;
    if (!base) return null;
    const cols: { key: string; title: string; entry: any }[] = [
      { key: 'ref', title: tr(lang, 'Actuelle (référence)', 'Current (reference)'), entry: base },
    ];
    const seen = new Map<number, number>();
    catEntries.forEach(([key, fr, enTxt]) => {
      const idx = summary?.categories?.[key];
      const entry = (summary?.finalists || []).find((f: any) => f.idx === idx);
      if (!entry) return;
      const short = tr(lang, fr.replace('Meilleure configuration globale', 'Globale').replace('Meilleure performance brute', 'Brute').replace('Meilleur compromis', 'Compromis').replace('Meilleure robustesse', 'Robuste'), enTxt.replace('Best overall configuration', 'Overall').replace('Best raw performance', 'Raw').replace('Best trade-off', 'Trade-off').replace('Best robustness', 'Robust'));
      const at = seen.get(entry.idx);
      if (at !== undefined) {
        cols[at].title += ` / ${short}`;
      } else {
        seen.set(entry.idx, cols.length);
        cols.push({ key, title: short, entry });
      }
    });
    if (cols.length < 2) return null;

    type Row = { label: string; get: (e: any) => number | null; render: (e: any) => React.ReactNode; better: 'high' | 'low' | null };
    const num = (v: any): number | null => (v === null || v === undefined || v === '' || Number.isNaN(Number(v)) ? null : Number(v));
    const stageRows = (stage: 'training' | 'validation' | 'oos', name: string): Row[] => [
      { label: `${name} · Return`, get: (e) => num(e?.[stage]?.total_return_pct), render: (e) => signed(e?.[stage]?.total_return_pct, 2, '%'), better: 'high' },
      { label: `${name} · PF`, get: (e) => num(e?.[stage]?.profit_factor), render: (e) => fmt(e?.[stage]?.profit_factor), better: 'high' },
      { label: `${name} · Max DD`, get: (e) => (num(e?.[stage]?.max_drawdown_pct) === null ? null : Math.abs(num(e?.[stage]?.max_drawdown_pct) as number)), render: (e) => (num(e?.[stage]?.max_drawdown_pct) === null ? '—' : `-${fmt(Math.abs(Number(e[stage].max_drawdown_pct)), 2, '%')}`), better: 'low' },
      { label: `${name} · Sharpe`, get: (e) => num(e?.[stage]?.sharpe_ratio), render: (e) => fmt(e?.[stage]?.sharpe_ratio), better: 'high' },
    ];
    const rows: Row[] = [
      ...stageRows('training', 'Training'),
      ...stageRows('validation', 'Validation'),
      ...stageRows('oos', 'OOS'),
      { label: tr(lang, 'Robustesse /100', 'Robustness /100'), get: (e) => num(e?.robustness), render: (e) => fmt(e?.robustness, 1), better: 'high' },
      { label: tr(lang, 'Stabilité des voisins', 'Neighbour stability'), get: (e) => num(e?.neighbors?.stability), render: (e) => fmt(e?.neighbors?.stability, 2), better: 'high' },
    ];
    const baseParams = base.params_full || base.params || {};
    const changedKeys = Array.from(new Set(cols.slice(1).flatMap((c) => Object.keys(c.entry.params_full || c.entry.params || {}).filter((k) => String((c.entry.params_full || c.entry.params)[k]) !== String(baseParams[k])))));
    const riskTxt = (e: any) => (e?.overfit?.risk === 'high' ? tr(lang, 'élevé', 'high') : e?.overfit?.risk === 'medium' ? tr(lang, 'moyen', 'medium') : e?.overfit?.risk ? tr(lang, 'faible', 'low') : '—');

    return (
      <div className="space-y-2" data-testid="opt-compare">
        <div className="text-[11px] uppercase font-mono-tabular text-[#6E7B88]">
          {tr(lang, 'Comparaison avec la configuration actuelle', 'Comparison with the current configuration')}
        </div>
        <div className="bg-[#0D1318] border border-white/[0.08] rounded-xl overflow-x-auto">
          <table className="w-full text-[11px] font-mono-tabular whitespace-nowrap">
            <thead>
              <tr className="text-[#6E7B88] border-b border-white/[0.08]">
                <th className="text-left font-normal py-2 pl-3 pr-2 sticky left-0 bg-[#0D1318]">{tr(lang, 'Indicateur', 'Metric')}</th>
                {cols.map((c) => (
                  <th key={c.key} className="text-right font-normal py-2 px-2">{c.title}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const baseVal = r.get(cols[0].entry);
                return (
                  <tr key={r.label} className="border-t border-white/[0.05]">
                    <td className="text-left py-1.5 pl-3 pr-2 text-[#8B98A4] sticky left-0 bg-[#0D1318]">{r.label}</td>
                    {cols.map((c, i) => {
                      const v = r.get(c.entry);
                      let cls = 'text-[#E8EEF2]';
                      let mark = '';
                      if (i > 0 && v !== null && baseVal !== null && r.better && v !== baseVal) {
                        const good = r.better === 'high' ? v > baseVal : v < baseVal;
                        cls = good ? 'text-[#32D583]' : 'text-[#F97066]';
                        mark = good ? ' ▲' : ' ▼';
                      }
                      return (
                        <td key={c.key} className={`text-right py-1.5 px-2 ${cls}`}>{r.render(c.entry)}{mark}</td>
                      );
                    })}
                  </tr>
                );
              })}
              <tr className="border-t border-white/[0.05]">
                <td className="text-left py-1.5 pl-3 pr-2 text-[#8B98A4] sticky left-0 bg-[#0D1318]">{tr(lang, 'Surapprentissage', 'Overfitting')}</td>
                {cols.map((c) => (
                  <td key={c.key} className="text-right py-1.5 px-2 text-[#E8EEF2]">{riskTxt(c.entry)}</td>
                ))}
              </tr>
              {changedKeys.map((k) => (
                <tr key={`p-${k}`} className="border-t border-white/[0.05]">
                  <td className="text-left py-1.5 pl-3 pr-2 text-[#8B98A4] sticky left-0 bg-[#0D1318]">{k}</td>
                  {cols.map((c, i) => {
                    const v = (c.entry.params_full || c.entry.params || {})[k];
                    const changed = i > 0 && String(v) !== String(baseParams[k]);
                    return <td key={c.key} className={`text-right py-1.5 px-2 ${changed ? 'text-[#4EA1FF]' : 'text-[#E8EEF2]'}`}>{v === undefined ? '—' : String(v)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-[#6E7B88]">
          {tr(lang, '▲ / ▼ : mieux / moins bien que la configuration actuelle. Paramètres en bleu : valeur différente de la référence. L’OOS n’a pas servi à choisir ces configurations.', '▲ / ▼: better / worse than the current configuration. Blue parameters: value differs from the reference. OOS was not used to select these configurations.')}
        </p>
      </div>
    );
  };

  // ---- Monte Carlo : rééchantillonnage réel des trades (summary.details[idx].monte_carlo_all) ----
  const renderMonteCarlo = () => {
    const details = summary?.details || {};
    const items: { title: string; mc: any }[] = [];
    const pushed = new Set<number>();
    const add = (title: string, entry: any) => {
      if (!entry || pushed.has(entry.idx)) return;
      pushed.add(entry.idx);
      const mc = details[String(entry.idx)]?.monte_carlo_all;
      if (mc) items.push({ title, mc });
    };
    catEntries.forEach(([key, fr, enTxt]) => {
      const idx = summary?.categories?.[key];
      add(tr(lang, fr, enTxt), (summary?.finalists || []).find((f: any) => f.idx === idx));
    });
    add(tr(lang, 'Configuration actuelle (référence)', 'Current configuration (reference)'), summary?.baseline);
    return (
      <div className="space-y-2" data-testid="opt-montecarlo">
        <div className="text-[11px] uppercase font-mono-tabular text-[#6E7B88] flex items-center gap-1">
          Monte Carlo <InfoTip term="monte_carlo" lang={lang} />
        </div>
        {items.length === 0 ? (
          <div className="text-[11px] text-[#8B98A4] bg-[#0D1318] rounded-lg p-2.5">
            {tr(lang, 'Monte Carlo indisponible : moins de 10 trades sur la période, ou ancien résultat sans ce détail.', 'Monte Carlo unavailable: fewer than 10 trades over the period, or an older result without this detail.')}
          </div>
        ) : (
          <div className="grid gap-2 md:grid-cols-2">
            {items.map(({ title, mc }) => {
              const lo = Number(mc.return_p5), mid = Number(mc.return_p50), hi = Number(mc.return_p95);
              const span = Math.max(1e-9, Math.max(Math.abs(lo), Math.abs(hi), Math.abs(mid)) * 2);
              const pos = (v: number) => `${Math.min(100, Math.max(0, 50 + (v / span) * 100))}%`;
              const left = Math.min(lo, hi), right = Math.max(lo, hi);
              return (
                <div key={title} className="bg-[#0D1318] border border-white/[0.08] rounded-xl p-3 space-y-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <h4 className="text-xs font-semibold text-[#E8EEF2]">{title}</h4>
                    <span className="text-[10px] text-[#6E7B88] font-mono-tabular">{mc.n_sims} {tr(lang, 'tirages', 'draws')} · {mc.n_trades} trades</span>
                  </div>
                  <div className="relative h-3 rounded bg-[#121A21]" role="img" aria-label={tr(lang, `Rendement final : P5 ${fmt(lo, 1)}%, médiane ${fmt(mid, 1)}%, P95 ${fmt(hi, 1)}%`, `Final return: P5 ${fmt(lo, 1)}%, median ${fmt(mid, 1)}%, P95 ${fmt(hi, 1)}%`)}>
                    <div className="absolute top-0 bottom-0 w-px bg-[#5F6B75]" style={{ left: '50%' }} title="0%" />
                    <div className="absolute top-0.5 bottom-0.5 rounded bg-[#4EA1FF]/40" style={{ left: pos(left), width: `${Math.max(1, ((right - left) / span) * 100)}%` }} />
                    <div className="absolute top-0 bottom-0 w-0.5 bg-[#4EA1FF]" style={{ left: pos(mid) }} />
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-[11px] font-mono-tabular">
                    <div><div className="text-[#6E7B88]">{tr(lang, 'Rendement P5', 'Return P5')}</div><div>{signed(mc.return_p5, 2, '%')}</div></div>
                    <div><div className="text-[#6E7B88]">{tr(lang, 'Médiane', 'Median')}</div><div>{signed(mc.return_p50, 2, '%')}</div></div>
                    <div><div className="text-[#6E7B88]">{tr(lang, 'Rendement P95', 'Return P95')}</div><div>{signed(mc.return_p95, 2, '%')}</div></div>
                    <div><div className="text-[#6E7B88]">{tr(lang, 'DD médian', 'Median DD')}</div><div>-{fmt(mc.max_dd_p50, 2, '%')}</div></div>
                    <div><div className="text-[#6E7B88]">{tr(lang, 'DD P95', 'DD P95')}</div><div>-{fmt(mc.max_dd_p95, 2, '%')}</div></div>
                    <div><div className="text-[#6E7B88]">{tr(lang, 'Proba. de perte', 'Loss probability')}</div><div className={Number(mc.prob_loss_pct) > 30 ? 'text-[#D6A84F]' : ''}>{fmt(mc.prob_loss_pct, 1, '%')}</div></div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        <p className="text-[10px] text-[#6E7B88]">
          {tr(lang, 'Rééchantillonnage avec remise des P&L réels des trades (training + validation + OOS). Ne prédit pas l’avenir : mesure la sensibilité au hasard de l’ordre des trades.', 'Bootstrap (with replacement) of real trade P&L (training + validation + OOS). Does not predict the future: it measures sensitivity to trade-order luck.')}
        </p>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* ================= Configuration ================= */}
      <div className="bg-[#0D1318] border border-white/[0.08] rounded-xl p-5 space-y-4">
        <div>
          <h3 className="font-display text-sm font-semibold text-[#E8EEF2] flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-[#20C997]" />
            {tr(lang, 'Laboratoire d\'optimisation', 'Optimization Lab')}
          </h3>
          <p className="text-xs text-[#8B98A4] mt-1">
            {tr(
              lang,
              "Recherche automatique de paramètres robustes sur le moteur de backtest réel de Strategy Lab. L'optimisation tourne sur un worker séparé : elle continue même si vous fermez cette page. Outil de recherche uniquement : aucune configuration live n'est modifiée, aucun résultat n'est une garantie de rentabilité.",
              'Automatic search for robust parameters on the real Strategy Lab backtest engine. It runs on a separate worker and keeps going if you close this page. Research tool only: no live configuration is modified and no result guarantees profitability.'
            )}
          </p>
          <p className="text-[11px] text-[#6E7B88] mt-1 font-mono-tabular">
            {symbol} · {timeframe} · {tradingStyle.toUpperCase()} · {startDate || endDate ? `${startDate || '…'} → ${endDate || '…'}` : tr(lang, 'période automatique', 'automatic period')}
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Méthode', 'Method')}</label>
            <select value={method} onChange={(e) => { setMethod(e.target.value as any); setPlan(null); }} className={inputCls}>
              <option value="grid">{tr(lang, 'Recherche par grille', 'Grid Search')}</option>
              <option value="random">{tr(lang, 'Recherche aléatoire', 'Random Search')}</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-[#8B98A4] mb-1">
              {method === 'random' ? tr(lang, 'Nombre de configurations', 'Number of configurations') : tr(lang, 'Max configurations (garde-fou)', 'Max configurations (guard)')}
            </label>
            <input type="number" min={1} value={maxConfigs} onChange={(e) => { setMaxConfigs(e.target.value); setPlan(null); }} className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Trades minimum (training)', 'Min trades (training)')}</label>
            <input type="number" min={5} value={minTrades} onChange={(e) => setMinTrades(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Finalistes (Top K)', 'Finalists (Top K)')}</label>
            <input type="number" min={3} max={40} value={topK} onChange={(e) => setTopK(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Bougies max', 'Max candles')}</label>
            <input type="number" min={500} max={limits.max_candles || 600000} value={maxCandles} onChange={(e) => setMaxCandles(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Graine (', 'Seed (')}{tr(lang, 'reproductibilité', 'reproducibility')})</label>
            <input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} className={inputCls} />
          </div>
          <div className="col-span-2">
            <label className="block text-[11px] text-[#8B98A4] mb-1">{tr(lang, 'Configuration de base / référence', 'Base / reference configuration')}</label>
            <select value={baseSource} onChange={(e) => { setBaseSource(e.target.value as any); setPlan(null); setSelected({}); }} className={inputCls}>
              {globalApplies && (
                <option value="global">{tr(lang, 'Configuration active du Strategy Lab (validée / sauvegardée)', 'Active Strategy Lab configuration (validated / saved)')}</option>
              )}
              <option value="official">{tr(lang, 'Preset officiel Bitsure du style (configuration actuelle)', 'Official Bitsure preset for the style (current configuration)')}</option>
              <option value="editor">{tr(lang, "Paramètres actuels de l'éditeur du Lab", 'Current Lab editor parameters')}</option>
            </select>
            {baseSource === 'global' && globalCfg && (
              <div className="mt-1 text-[10px] text-[#20C997]">
                {tr(lang, 'Source de vérité : ', 'Source of truth: ')}
                {globalCfg.presetName ? `${tr(lang, 'preset', 'preset')} « ${globalCfg.presetName} »` : tr(lang, 'Raw Config validée', 'validated Raw Config')}
                {' · '}{new Date(globalCfg.updatedAt).toLocaleString()}
              </div>
            )}
            {!globalApplies && (
              <div className="mt-1 text-[10px] text-[#6E7B88]">
                {tr(lang, 'Aucune configuration validée pour ce style : référence = preset officiel. Validez la Raw Config dans le Strategy Lab pour la définir.', 'No validated configuration for this style: reference = official preset. Validate the Raw Config in Strategy Lab to set one.')}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-3">
          <div className="text-[11px] uppercase font-mono-tabular text-[#6E7B88]">
            {tr(lang, 'Paramètres à optimiser', 'Parameters to optimise')} ({Object.keys(selected).length}/{limits.max_params})
          </div>
          {(Object.entries(grouped) as [string, OptParam[]][]).map(([group, list]) => (
            <div key={group} className="space-y-1.5">
              <div className="text-[11px] text-[#8B98A4]">{tr(lang, GROUP_LABELS[group]?.[0] || group, GROUP_LABELS[group]?.[1] || group)}</div>
              <div className="flex flex-wrap gap-1.5">
                {list.map((p) => {
                  const on = !!selected[p.key];
                  return (
                    <button
                      key={p.key}
                      type="button"
                      onClick={() => {
                        const before = liveTotal;
                        const willAdd = !selected[p.key];
                        toggleParam(p);
                        const n = willAdd ? (p.type === 'bool' ? 2 : p.type === 'enum' ? (p.choices || []).length : null) : null;
                        if (!willAdd) setLastDelta({ text: `${label(p)} ${tr(lang, 'retiré', 'removed')}`, tone: 'remove' });
                        else if (n !== null) setLastDelta({ text: `${label(p)} ${tr(lang, 'ajouté', 'added')} : ×${n}${before !== null ? ` → ${(before * n).toLocaleString()} ${tr(lang, 'configurations', 'configurations')}` : ''}`, tone: 'add' });
                        else setLastDelta({ text: `${label(p)} ${tr(lang, 'ajouté', 'added')} — ${tr(lang, 'réglez min / max / step', 'set min / max / step')}`, tone: 'add' });
                      }}
                      className={`px-2.5 py-1 rounded-lg border text-[11px] ${on ? 'bg-[#20C997]/15 border-[#20C997]/50 text-[#20C997]' : 'bg-[#080C0F] border-white/15 text-[#E8EEF2] hover:border-white/30'}`}
                      title={p.key}
                    >
                      {label(p)}
                      {on && countValues(selected[p.key]) !== null && (
                        <span className="ml-1.5 font-mono-tabular opacity-80">×{countValues(selected[p.key])}</span>
                      )}
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
              const cur = baseValue(p);
              return (
                <div key={p.key} className="bg-[#0D1318] border border-white/[0.08] rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs text-[#E8EEF2]">
                      {label(p)} <span className="text-[#6E7B88] font-mono-tabular">({p.key})</span>
                    </div>
                    <div className="text-[10px] text-[#6E7B88] font-mono-tabular text-right">
                      <div className="text-[#20C997] text-[11px]">
                        {countValues(s) === null ? tr(lang, 'saisie incomplète', 'incomplete input') : `${countValues(s)} ${tr(lang, 'valeurs', 'values')} → ×${countValues(s)}`}
                      </div>
                      {tr(lang, 'actuel', 'current')} : {String(cur)} {p.min !== null && p.min !== undefined ? `· [${p.min} – ${p.max}]` : ''}
                    </div>
                  </div>
                  {p.type === 'bool' || p.type === 'enum' ? (
                    <div className="text-[11px] text-[#8B98A4] font-mono-tabular">
                      {tr(lang, 'Valeurs testées', 'Tested values')} : {(s.values || []).map(String).join(', ')}
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-2">
                      {(['min', 'max', 'step'] as const).map((f) => (
                        <div key={f}>
                          <label className="block text-[10px] text-[#6E7B88] mb-0.5 uppercase">{f}</label>
                          <input type="number" step="any" value={s[f]} onChange={(e) => updateRange(p.key, { [f]: e.target.value } as any)} className={inputCls} />
                        </div>
                      ))}
                    </div>
                  )}
                  {p.active_when && String(resolvedBase[p.active_when.param] ?? '') !== '' && baseSource !== 'official' && resolvedBase[p.active_when.param] !== p.active_when.equals && (
                    <div className="text-[11px] text-[#D6A84F]">
                      {tr(lang, `Sans effet tant que ${p.active_when.param} ≠ ${String(p.active_when.equals)}.`, `No effect unless ${p.active_when.param} = ${String(p.active_when.equals)}.`)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {Object.keys(selected).length > 0 && (
          <div className={`sticky bottom-2 z-10 text-xs rounded-lg p-3 space-y-1.5 border ${overLimit || planError ? 'bg-[#2A0F16]/95 border-[#F04438]/40' : overWarn ? 'bg-[#2A200B]/95 border-[#D6A84F]/40' : 'bg-[#0D1318]/95 border-[#20C997]/30'}`}>
            {lastDelta && <div className={lastDelta.tone === 'add' ? 'text-[#20C997]' : 'text-[#8B98A4]'}>{lastDelta.text}</div>}
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-[#8B98A4]">{tr(lang, 'Configurations à tester', 'Configurations to test')} :</span>
              <b className={`text-lg font-mono-tabular ${overLimit || planError ? 'text-[#F04438]' : overWarn ? 'text-[#D6A84F]' : 'text-[#20C997]'}`}>
                {plan && !isBusy('plan') && !planError ? plan.n_configs.toLocaleString() : liveTotal === null ? '—' : `≈ ${liveTotal.toLocaleString()}`}
              </b>
              {isBusy('plan') && <span className="text-[10px] text-[#6E7B88]">{tr(lang, 'comptage exact…', 'exact count…')}</span>}
            </div>
            {complete && (
              <div className="text-[11px] text-[#8B98A4] font-mono-tabular break-words">
                {(counts as number[]).join(' × ')} = {gridTotal!.toLocaleString()} {tr(lang, 'combinaisons', 'combinations')}
                {method === 'random' && gridTotal! > requested ? ` → ${tr(lang, 'tirage aléatoire de', 'random draw of')} ${requested.toLocaleString()}` : ''}
                {plan && !isBusy('plan') && !planError && plan.n_configs !== liveTotal ? ` · ${tr(lang, 'après filtrage des combinaisons incohérentes', 'after removing inconsistent combinations')} : ${plan.n_configs.toLocaleString()}` : ''}
              </div>
            )}
            {liveTotal !== null && !planError && (
              <div className="text-[11px] text-[#8B98A4]">
                {tr(lang, 'Durée estimée', 'Estimated duration')} :{' '}
                {formatDuration(plan && !isBusy('plan') ? plan.estimated_seconds : (liveTotal + 40) * 0.0002 * 0.6 * (Number(maxCandles) || 4000))}{' '}
                <span className="text-[#6E7B88]">({tr(lang, 'indicatif, selon le CPU du worker', 'indicative, depends on worker CPU')})</span>
              </div>
            )}
            {overLimit && (
              <div className="text-[#F04438] flex items-start gap-1.5">
                <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>{tr(lang, `Au-delà de la limite de ${(limits.max_configs || 20000).toLocaleString()} en Grid Search : augmentez les steps, retirez un paramètre ou passez en Random Search.`, `Above the Grid Search limit of ${(limits.max_configs || 20000).toLocaleString()}: increase steps, remove a parameter or switch to Random Search.`)}</span>
              </div>
            )}
            {planError && !overLimit && (
              <div className="text-[#F04438] flex items-start gap-1.5">
                <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>{planError}</span>
              </div>
            )}
            {overWarn && !overLimit && !planError && (
              <div className="text-[#D6A84F] flex items-start gap-1.5">
                <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                <span>{tr(lang, 'Beaucoup de configurations : plus de temps de calcul et un risque de surapprentissage plus élevé (le meilleur score devient plus optimiste).', 'Many configurations: longer run time and a higher overfitting risk (the best score becomes more optimistic).')}</span>
              </div>
            )}
            {!planError && plan && (plan.warnings || []).map((w: string, i: number) => (
              <div key={i} className="text-[#D6A84F] flex items-start gap-1.5">
                <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                <span>{w}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={launch}
            disabled={isBusy('create') || Object.keys(selected).length === 0 || !!planError || overLimit}
            className="px-5 py-2 rounded-lg bg-[#20C997] hover:bg-[#1AA67D] disabled:opacity-50 text-[#080C0F] font-semibold text-xs flex items-center gap-2"
          >
            <Play className={`w-4 h-4 fill-current ${isBusy('create') ? 'animate-pulse' : ''}`} />
            {isBusy('create') ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, "Lancer l'optimisation", 'Start optimization')}
          </button>
        </div>
      </div>

      {/* ================= Historique des jobs ================= */}
      <div className="bg-[#0D1318] border border-white/[0.08] rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-sm font-semibold text-[#E8EEF2]">{tr(lang, 'Optimisations', 'Optimizations')} ({jobs.length})</h3>
          <button type="button" onClick={() => withBusy('refresh', () => loadOverview(false))} disabled={isBusy('refresh')} className="text-[11px] text-[#8B98A4] hover:text-[#E8EEF2] disabled:opacity-50">
            {isBusy('refresh') ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Actualiser', 'Refresh')}
          </button>
        </div>
        {jobs.length === 0 && (
          <EmptyState
            title={tr(lang, 'Aucune optimisation pour le moment.', 'No optimization yet.')}
            description={tr(lang, 'Choisissez des paramètres et leurs plages dans la configuration ci-dessus, puis lancez votre première optimisation.', 'Pick parameters and their ranges in the configuration above, then launch your first optimization.')}
          />
        )}
        <div className="space-y-2">
          {jobs.map((job) => {
            const active = job.status === 'queued' || job.status === 'running';
            return (
              <div key={job.job_id} className={`bg-[#0D1318] border rounded-lg p-3 space-y-2 ${activeJob?.job_id === job.job_id ? 'border-[#20C997]/40' : 'border-white/[0.08]'}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs font-mono-tabular text-[#E8EEF2]">
                    {job.job_id} <span className="text-[#6E7B88]">· {job.symbol} {job.timeframe} · {String(job.method).toUpperCase()} · {job.total_configs} cfg</span>
                  </div>
                  <StatusBadge tone={STATUS_TONE[job.status] || 'neutral'} dot>{statusLabel(job.status)}</StatusBadge>
                </div>
                {active && (
                  <div className="space-y-1">
                    <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                      <div className="h-full bg-[#20C997] transition-all" style={{ width: `${Math.max(2, Math.min(100, job.progress_pct || 0))}%` }} />
                    </div>
                    <div className="text-[10px] text-[#8B98A4] font-mono-tabular">
                      {fmt(job.progress_pct, 0, '%')} · {stageLabel(job.stage)} · {job.done_configs}/{job.total_configs}
                    </div>
                  </div>
                )}
                {job.status === 'failed' && job.error && <div className="text-[11px] text-[#F04438] break-words">{job.error}</div>}
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => openJob(job)} disabled={isBusy(`open-${job.job_id}`)} className="px-2.5 py-1 rounded-lg bg-[#172129] hover:bg-[#202A32] disabled:opacity-50 border border-white/10 text-[11px] text-[#E8EEF2] inline-flex items-center gap-1.5">
                    <Eye className="w-3 h-3" />
                    {isBusy(`open-${job.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Détails', 'Details')}
                  </button>
                  {job.status === 'completed' && (
                    <>
                      <button type="button" onClick={() => viewReport(job)} disabled={isBusy(`view-${job.job_id}`)} className="px-2.5 py-1 rounded-lg bg-[#172129] hover:bg-[#202A32] disabled:opacity-50 border border-white/10 text-[11px] text-[#E8EEF2]">
                        {isBusy(`view-${job.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Rapport', 'Report')}
                      </button>
                      <button type="button" onClick={() => downloadReport(job)} disabled={isBusy(`dl-${job.job_id}`)} className="px-2.5 py-1 rounded-lg bg-[#172129] hover:bg-[#202A32] disabled:opacity-50 border border-white/10 text-[11px] text-[#E8EEF2] inline-flex items-center gap-1.5">
                        <Download className="w-3 h-3 text-[#20C997]" />
                        {isBusy(`dl-${job.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Télécharger', 'Download')}
                      </button>
                    </>
                  )}
                  {active && (
                    <button type="button" onClick={() => cancelJob(job)} disabled={isBusy(`cancel-${job.job_id}`)} className="px-2.5 py-1 rounded-lg bg-[#F04438]/10 hover:bg-[#F04438]/20 disabled:opacity-50 border border-[#F04438]/30 text-[11px] text-[#F04438]">
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
        <div className="bg-[#0D1318] border border-white/[0.08] rounded-xl p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-display text-sm font-semibold text-[#E8EEF2]">
              {activeJob.job_id} — {activeJob.symbol} {activeJob.timeframe}
            </h3>
            <StatusBadge tone={STATUS_TONE[activeJob.status] || 'neutral'} dot>{statusLabel(activeJob.status)}</StatusBadge>
          </div>
          {(activeJob.status === 'queued' || activeJob.status === 'running') && (() => {
            const pct = Math.max(0, Math.min(100, Number(activeJob.progress_pct) || 0));
            const elapsed = activeJob.started_at ? Math.max(0, nowSec - activeJob.started_at) : null;
            // ETA approximatif déduit de la progression réelle ; absent tant que la progression est nulle.
            const eta = elapsed !== null && pct > 0 && pct < 100 ? (elapsed * (100 - pct)) / pct : null;
            return (
              <div className="space-y-2" role="status" aria-live="polite">
                <div className="h-1.5 rounded-full bg-[#172129] overflow-hidden">
                  <div className="h-full bg-[#20C997] transition-all" style={{ width: `${Math.max(2, pct)}%` }} />
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono-tabular">
                  <div><div className="text-[#6E7B88]">{tr(lang, 'Configurations testées', 'Configurations tested')}</div><div className="text-[#E8EEF2] text-sm">{activeJob.done_configs} / {activeJob.total_configs}</div></div>
                  <div><div className="text-[#6E7B88]">{tr(lang, 'Étape', 'Stage')}</div><div className="text-[#E8EEF2] text-sm">{stageLabel(activeJob.stage)} · {fmt(pct, 0, '%')}</div></div>
                  <div><div className="text-[#6E7B88]">{tr(lang, 'Écoulé', 'Elapsed')}</div><div className="text-[#E8EEF2] text-sm">{elapsed !== null ? formatDuration(elapsed) : '—'}</div></div>
                  <div><div className="text-[#6E7B88]">{tr(lang, 'ETA (approx.)', 'ETA (approx.)')}</div><div className="text-[#E8EEF2] text-sm">{eta !== null ? formatDuration(eta) : '—'}</div></div>
                </div>
                <div className="text-[11px] text-[#8B98A4]">
                  {tr(lang, 'Vous pouvez fermer cette page : le worker continue.', 'You can close this page: the worker keeps going.')}
                </div>
              </div>
            );
          })()}
          {activeJob.status === 'failed' && <div className="text-xs text-[#F04438] break-words">{activeJob.error}</div>}
          {activeJob.status === 'cancelled' && <div className="text-xs text-[#8B98A4]">{tr(lang, 'Optimisation annulée.', 'Optimization cancelled.')}</div>}

          {summary && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono-tabular">
                <div className="bg-[#0D1318] rounded-lg p-2.5"><div className="text-[#6E7B88]">{tr(lang, 'Configurations', 'Configurations')}</div><div className="text-[#E8EEF2] text-sm">{summary.n_configs}</div></div>
                <div className="bg-[#0D1318] rounded-lg p-2.5"><div className="text-[#6E7B88]">{tr(lang, 'Exploitables', 'Usable')}</div><div className="text-[#E8EEF2] text-sm">{summary.n_scored}</div></div>
                <div className="bg-[#0D1318] rounded-lg p-2.5"><div className="text-[#6E7B88]">{tr(lang, 'Durée', 'Duration')}</div><div className="text-[#E8EEF2] text-sm">{fmt(summary.duration_seconds, 0, ' s')}</div></div>
                <div className="bg-[#0D1318] rounded-lg p-2.5"><div className="text-[#6E7B88]">{tr(lang, 'Erreurs moteur', 'Engine errors')}</div><div className="text-[#E8EEF2] text-sm">{summary.n_errors}</div></div>
              </div>
              {(summary.warnings || []).map((w: string, i: number) => (
                <div key={i} className="text-[11px] text-[#D6A84F] flex items-start gap-1.5"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /><span>{w}</span></div>
              ))}
              {catEntries.map(([key, fr, enTxt]) => {
                const idx = summary.categories?.[key];
                const entry = (summary.finalists || []).find((f: any) => f.idx === idx);
                return renderEntry(tr(lang, fr, enTxt), entry);
              })}
              {summary.baseline && renderEntry(tr(lang, 'Configuration actuelle de Bitsure (référence)', 'Current Bitsure configuration (reference)'), summary.baseline)}
              {renderCompare()}
              {renderMonteCarlo()}

              {(summary.sensitivity || []).length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] uppercase font-mono-tabular text-[#6E7B88] flex items-center gap-1">{tr(lang, 'Sensibilité des paramètres (score training moyen)', 'Parameter sensitivity (mean training score)')} <InfoTip term="sensitivity" lang={lang} /></div>
                  {(summary.sensitivity || []).map((s: any) => {
                    const rows = (s.values || []).filter((r: any) => r.mean_score !== null && r.mean_score !== undefined);
                    const maxAbs = Math.max(1, ...rows.map((r: any) => Math.abs(r.mean_score)));
                    return (
                      <div key={s.key} className="bg-[#0D1318] rounded-lg p-2.5">
                        <div className="text-[11px] text-[#E8EEF2] mb-1.5">{s.key} <span className="text-[#6E7B88]">· {tr(lang, 'amplitude', 'spread')} {fmt(s.spread, 1)}</span></div>
                        <div className="flex items-end gap-1 h-14">
                          {rows.map((r: any) => (
                            <div key={String(r.value)} className="flex-1 min-w-[6px] flex flex-col justify-end items-center" title={`${r.value}: ${fmt(r.mean_score, 1)}`}>
                              <div className={`w-full rounded-sm ${r.mean_score >= 0 ? 'bg-[#20C997]' : 'bg-[#F04438]'}`} style={{ height: `${Math.max(3, (Math.abs(r.mean_score) / maxAbs) * 100)}%` }} />
                            </div>
                          ))}
                        </div>
                        <div className="flex gap-1 text-[9px] text-[#6E7B88] font-mono-tabular">
                          {rows.map((r: any) => (<div key={String(r.value)} className="flex-1 min-w-[6px] text-center truncate">{String(r.value)}</div>))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="text-[11px] text-[#8B98A4] border-l-2 border-[#D6A84F]/60 pl-2.5">{summary.disclaimer}</p>
              {activeJob.status === 'completed' && (
                <div className="flex gap-2">
                  <button type="button" onClick={() => viewReport(activeJob)} disabled={isBusy(`view-${activeJob.job_id}`)} className="px-3 py-1.5 rounded-lg bg-[#20C997] hover:bg-[#1AA67D] disabled:opacity-50 text-[#080C0F] font-semibold text-xs">
                    {isBusy(`view-${activeJob.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Ouvrir le rapport complet', 'Open full report')}
                  </button>
                  <button type="button" onClick={() => downloadReport(activeJob)} disabled={isBusy(`dl-${activeJob.job_id}`)} className="px-3 py-1.5 rounded-lg bg-[#172129] hover:bg-[#202A32] disabled:opacity-50 border border-white/10 text-xs text-[#E8EEF2]">
                    {isBusy(`dl-${activeJob.job_id}`) ? tr(lang, 'Traitement…', 'Processing…') : tr(lang, 'Télécharger (HTML)', 'Download (HTML)')}
                  </button>
                </div>
              )}
              {activeJob.status === 'completed' && <div className="text-[11px] text-[#20C997] flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3" />{tr(lang, 'Résultats historiques : aucune garantie de rentabilité future.', 'Historical results: no guarantee of future profitability.')}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
