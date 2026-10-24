import React, { useState } from 'react';
import { ArrowLeft, FlaskConical, Loader2, Lock, UserPlus } from 'lucide-react';
import { AppLang, tr } from '../i18n';

const DEMO_SESSION_KEY = 'bitsure_demo_session';
const DEMO_USED_KEY = 'bitsure_demo_used';
const DEMO_LIMIT = 3;

const ASSETS = [
  { id: 'BTCUSDT', label: 'Bitcoin (BTC)' },
  { id: 'ETHUSDT', label: 'Ethereum (ETH)' },
  { id: 'XAUUSDT', label: 'Gold (XAU)' },
];
const TIMEFRAMES = ['15m', '1h', '4h', '1d'];

interface DemoAnalysis {
  symbol: string;
  timeframe: string;
  signal: string;
  teddy_score: number;
  confidence: string;
  reason: string;
  rejection_reason: string;
  current_price: number;
  sl?: number | null;
  tp?: number | null;
  rr_ratio?: number | null;
  indicators: Record<string, number | null>;
}

function getDemoSessionId(): string {
  try {
    let id = sessionStorage.getItem(DEMO_SESSION_KEY);
    if (!id) {
      id = `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
      sessionStorage.setItem(DEMO_SESSION_KEY, id);
    }
    return id;
  } catch {
    return `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
  }
}

function getUsed(): number {
  try {
    return Math.min(DEMO_LIMIT, Number(sessionStorage.getItem(DEMO_USED_KEY)) || 0);
  } catch {
    return 0;
  }
}

interface DemoModeProps {
  lang: AppLang;
  onBack: () => void;
  onCreateAccount: () => void;
  onLogin: () => void;
}

const fmt = (v?: number | null, d = 2) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString('en-US', { maximumFractionDigits: d }) : '—';

export const DemoMode: React.FC<DemoModeProps> = ({ lang, onBack, onCreateAccount, onLogin }) => {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [used, setUsed] = useState<number>(getUsed);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DemoAnalysis | null>(null);
  const limitReached = used >= DEMO_LIMIT;

  const runAnalysis = async () => {
    if (limitReached || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/demo/analyze?symbol=${symbol}&timeframe=${timeframe}&lang=${lang}`,
        { headers: { 'X-Demo-Session': getDemoSessionId() } }
      );
      const data = await res.json().catch(() => ({}));
      if (res.status === 429) {
        setUsed(DEMO_LIMIT);
        try {
          sessionStorage.setItem(DEMO_USED_KEY, String(DEMO_LIMIT));
        } catch {
          /* ignore */
        }
        return;
      }
      if (!res.ok || !data.ok) {
        throw new Error(data.error || tr(lang, 'Analyse indisponible pour le moment.', 'Analysis unavailable right now.'));
      }
      setResult(data.analysis);
      const next = Math.min(DEMO_LIMIT, Number(data.quota?.used) || used + 1);
      setUsed(next);
      try {
        sessionStorage.setItem(DEMO_USED_KEY, String(next));
      } catch {
        /* ignore */
      }
    } catch (e: any) {
      setError(e?.message || tr(lang, 'Erreur réseau.', 'Network error.'));
    } finally {
      setLoading(false);
    }
  };

  const signalColor =
    result?.signal === 'BUY' ? 'text-[#32D583]' : result?.signal === 'SELL' ? 'text-[#F04438]' : 'text-[#D6A84F]';
  const signalPlain = (s?: string) =>
    s === 'BUY'
      ? tr(lang, 'Conditions favorables à un achat', 'Conditions favour buying')
      : s === 'SELL'
        ? tr(lang, 'Conditions favorables à une vente', 'Conditions favour selling')
        : tr(lang, 'Pas de signal clair : attendre', 'No clear signal: wait');

  return (
    <div className="min-h-screen bg-[#080C0F] text-[#E8EEF2] flex flex-col">
      <header className="border-b border-white/[0.07] px-4 sm:px-6 h-14 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-xs text-[#8B98A4] hover:text-[#E8EEF2]"
        >
          <ArrowLeft className="w-4 h-4" />
          {tr(lang, 'Retour', 'Back')}
        </button>
        <span
          className="inline-flex items-center gap-1.5 text-[11px] font-mono-tabular font-semibold uppercase tracking-wider text-[#D6A84F] border border-[#D6A84F]/40 bg-[#D6A84F]/10 px-2.5 py-1 rounded"
          role="status"
        >
          <FlaskConical className="w-3.5 h-3.5" />
          {tr(lang, 'Mode démo', 'Demo mode')}
        </span>
        <button type="button" onClick={onLogin} className="text-xs text-[#8B98A4] hover:text-[#E8EEF2]">
          {tr(lang, 'Connexion', 'Log in')}
        </button>
      </header>

      <main className="flex-1 w-full max-w-xl mx-auto px-4 py-6 space-y-5">
        <div className="space-y-1">
          <h1 className="font-display text-xl font-bold">
            {tr(lang, 'Essayez une analyse, sans compte', 'Try an analysis, no account needed')}
          </h1>
          <p className="text-xs text-[#8B98A4] leading-relaxed">
            {tr(
              lang,
              "100 % simulé : aucun argent réel, aucune clé API, aucune connexion à un exchange. Rien n'est enregistré.",
              'Fully simulated: no real money, no API keys, no exchange connection. Nothing is saved.'
            )}
          </p>
        </div>

        <section className="bg-[#0D1318] border border-white/[0.09] rounded-xl p-4 space-y-4">
          <label className="block space-y-1.5">
            <span className="text-[11px] uppercase tracking-wider text-[#6E7B88]">
              {tr(lang, '1. Choisissez un actif', '1. Choose an asset')}
            </span>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-[#080C0F] border border-white/10 rounded-lg px-3 py-2.5 text-sm"
            >
              {ASSETS.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
          <div className="space-y-1.5">
            <span className="text-[11px] uppercase tracking-wider text-[#6E7B88]">
              {tr(lang, '2. Durée de chaque bougie', '2. Candle length')}
            </span>
            <div className="grid grid-cols-4 gap-2">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                  className={`py-2 rounded-lg text-xs font-mono-tabular border ${
                    timeframe === tf
                      ? 'bg-[#20C997]/15 border-[#20C997]/50 text-[#20C997]'
                      : 'bg-[#080C0F] border-white/10 text-[#8B98A4]'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={runAnalysis}
            disabled={loading || limitReached}
            className="w-full py-3 bg-[#20C997] hover:bg-[#1AA67D] disabled:opacity-40 text-[#080C0F] font-semibold text-sm rounded-lg flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {tr(lang, "Lancer l'analyse", 'Run analysis')}
          </button>
          <p className="text-[11px] text-[#6E7B88] text-center font-mono-tabular">
            {tr(lang, `Analyses de démo : ${used}/${DEMO_LIMIT}`, `Demo analyses: ${used}/${DEMO_LIMIT}`)}
          </p>
          {error && <p className="text-xs text-[#F04438]">{error}</p>}
        </section>

        {result && (
          <section className="bg-[#0D1318] border border-white/[0.09] rounded-xl p-4 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className={`font-display text-2xl font-bold ${signalColor}`}>{result.signal}</div>
                <div className="text-xs text-[#8B98A4]">{signalPlain(result.signal)}</div>
              </div>
              <div className="text-right">
                <div className="font-mono-tabular text-2xl font-bold">
                  {fmt(result.teddy_score, 0)}
                  <span className="text-sm text-[#6E7B88]">/100</span>
                </div>
                <div className="text-[11px] text-[#6E7B88]">
                  {tr(lang, 'Score de confiance', 'Confidence score')}
                </div>
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-[#080C0F] rounded-lg p-2.5 border border-white/[0.06]">
                <dt className="text-[#6E7B88]">{tr(lang, 'Prix', 'Price')}</dt>
                <dd className="font-mono-tabular">{fmt(result.current_price)}</dd>
              </div>
              <div className="bg-[#080C0F] rounded-lg p-2.5 border border-white/[0.06]">
                <dt className="text-[#6E7B88]">{tr(lang, 'Gain/risque (R:R)', 'Reward/risk (R:R)')}</dt>
                <dd className="font-mono-tabular">{fmt(result.rr_ratio)}</dd>
              </div>
              <div className="bg-[#080C0F] rounded-lg p-2.5 border border-white/[0.06]">
                <dt className="text-[#6E7B88]">{tr(lang, 'Stop-loss (SL)', 'Stop-loss (SL)')}</dt>
                <dd className="font-mono-tabular">{fmt(result.sl)}</dd>
              </div>
              <div className="bg-[#080C0F] rounded-lg p-2.5 border border-white/[0.06]">
                <dt className="text-[#6E7B88]">{tr(lang, 'Objectif (TP)', 'Target (TP)')}</dt>
                <dd className="font-mono-tabular">{fmt(result.tp)}</dd>
              </div>
            </dl>
            {(result.reason || result.rejection_reason) && (
              <p className="text-xs text-[#8B98A4] leading-relaxed">
                {result.reason || result.rejection_reason}
              </p>
            )}
            <p className="text-[11px] text-[#6E7B88]">
              {tr(
                lang,
                'Simulation éducative : ce n’est pas un conseil financier.',
                'Educational simulation: this is not financial advice.'
              )}
            </p>
          </section>
        )}

        {limitReached && (
          <section className="bg-[#20C997]/10 border border-[#20C997]/40 rounded-xl p-4 space-y-3" role="status">
            <div className="flex items-center gap-2 font-semibold text-sm text-[#20C997]">
              <Lock className="w-4 h-4" />
              {tr(lang, 'Vous avez utilisé vos analyses de démo.', 'You have used your demo analyses.')}
            </div>
            <p className="text-xs text-[#E8EEF2]">
              {tr(lang, 'Créez un compte pour continuer.', 'Create an account to keep going.')}
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onCreateAccount}
                className="px-4 py-2.5 bg-[#20C997] text-[#080C0F] text-xs font-semibold rounded-lg flex items-center gap-1.5"
              >
                <UserPlus className="w-4 h-4" />
                {tr(lang, 'Créer un compte', 'Create an account')}
              </button>
              <button
                type="button"
                onClick={onLogin}
                className="px-4 py-2.5 border border-white/15 text-xs text-[#E8EEF2] rounded-lg"
              >
                {tr(lang, 'J’ai déjà un compte', 'I already have an account')}
              </button>
            </div>
          </section>
        )}
      </main>
    </div>
  );
};
