import React, { useState } from 'react';
import { CheckCircle2, Circle, X } from 'lucide-react';
import { AppLang, tr } from '../i18n';

const STEP_KEY = 'bitsure_beginner_steps';
type Steps = { asset: boolean; signal: boolean; practice: boolean };

function loadSteps(): Steps {
  try {
    const raw = JSON.parse(localStorage.getItem(STEP_KEY) || '{}');
    return { asset: !!raw.asset, signal: !!raw.signal, practice: !!raw.practice };
  } catch {
    return { asset: false, signal: false, practice: false };
  }
}

interface BeginnerPathProps {
  lang: AppLang;
  selectedSymbol: string;
  signal?: string | null;
  score?: number | null;
  loading: boolean;
  onPickAsset: (symbol: string) => void;
  onAnalyze: () => void;
  onOpenPaper: () => void;
  onShowAdvanced: () => void;
  onDismiss: () => void;
}

const ASSETS = [
  { id: 'BTCUSDT', label: 'Bitcoin' },
  { id: 'ETHUSDT', label: 'Ethereum' },
  { id: 'SOLUSDT', label: 'Solana' },
];

export const BeginnerPath: React.FC<BeginnerPathProps> = ({
  lang,
  selectedSymbol,
  signal,
  score,
  loading,
  onPickAsset,
  onAnalyze,
  onOpenPaper,
  onShowAdvanced,
  onDismiss,
}) => {
  const [steps, setSteps] = useState<Steps>(loadSteps);
  const mark = (k: keyof Steps) =>
    setSteps((prev) => {
      const next = { ...prev, [k]: true };
      try {
        localStorage.setItem(STEP_KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  const signalDone = steps.signal || (!!signal && steps.asset);
  const Icon = (done: boolean) =>
    done ? <CheckCircle2 className="w-4 h-4 text-[#20C997] shrink-0" /> : <Circle className="w-4 h-4 text-[#6E7B88] shrink-0" />;
  const plain =
    signal === 'BUY'
      ? tr(lang, 'les indicateurs penchent pour un achat', 'indicators lean towards buying')
      : signal === 'SELL'
        ? tr(lang, 'les indicateurs penchent pour une vente', 'indicators lean towards selling')
        : tr(lang, "pas de signal clair, le plus sage est d'attendre", 'no clear signal, waiting is the wiser move');

  return (
    <section className="bg-[#0D1318] border border-[#20C997]/30 rounded-xl p-4 space-y-3" aria-label={tr(lang, 'Parcours débutant', 'Beginner path')}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-sm font-bold text-[#E8EEF2]">{tr(lang, 'Parcours débutant : 3 étapes', 'Beginner path: 3 steps')}</h2>
          <p className="text-[11px] text-[#8B98A4]">
            {tr(lang, 'Tout se fait en simulation. Les outils avancés viennent ensuite.', 'Everything runs in simulation. Advanced tools come after.')}
          </p>
        </div>
        <button type="button" onClick={onDismiss} title={tr(lang, 'Masquer le guide (affiche les outils avancés)', 'Hide the guide (shows advanced tools)')} className="text-[#6E7B88] hover:text-[#E8EEF2]">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex gap-2.5 text-xs">
        {Icon(steps.asset)}
        <div className="space-y-1.5">
          <div className="font-semibold text-[#E8EEF2]">{tr(lang, '1. Choisissez un actif', '1. Choose an asset')}</div>
          <div className="flex flex-wrap gap-1.5">
            {ASSETS.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => {
                  onPickAsset(a.id);
                  mark('asset');
                }}
                className={`px-3 py-1.5 rounded-lg border text-[11px] ${
                  selectedSymbol === a.id && steps.asset ? 'border-[#20C997]/60 bg-[#20C997]/15 text-[#20C997]' : 'border-white/10 text-[#8B98A4]'
                }`}
              >
                {a.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex gap-2.5 text-xs">
        {Icon(signalDone)}
        <div className="space-y-1.5">
          <div className="font-semibold text-[#E8EEF2]">{tr(lang, '2. Comprenez un signal', '2. Understand one signal')}</div>
          <p className="text-[#8B98A4]">
            {signal
              ? tr(lang, `Signal ${signal}, score ${score ?? 0}/100 : ${plain}.`, `Signal ${signal}, score ${score ?? 0}/100: ${plain}.`)
              : tr(lang, 'Lancez une analyse : le score va de 0 à 100 (plus il est haut, plus les indicateurs sont d’accord).', 'Run an analysis: the score runs 0–100 (higher means the indicators agree more).')}
          </p>
          <button
            type="button"
            disabled={loading || !steps.asset}
            onClick={() => {
              onAnalyze();
              mark('signal');
            }}
            className="px-3 py-1.5 rounded-lg bg-[#20C997] text-[#080C0F] font-semibold text-[11px] disabled:opacity-40"
          >
            {tr(lang, "Analyser l'actif", 'Analyze the asset')}
          </button>
        </div>
      </div>

      <div className="flex gap-2.5 text-xs">
        {Icon(steps.practice)}
        <div className="space-y-1.5">
          <div className="font-semibold text-[#E8EEF2]">{tr(lang, '3. Entraînez-vous en sécurité', '3. Practice safely')}</div>
          <p className="text-[#8B98A4]">{tr(lang, 'Portefeuille virtuel de 10 000 USDT : aucun argent réel.', 'Virtual 10,000 USDT portfolio: no real money.')}</p>
          <button
            type="button"
            onClick={() => {
              onOpenPaper();
              mark('practice');
            }}
            className="px-3 py-1.5 rounded-lg border border-white/15 text-[#E8EEF2] text-[11px]"
          >
            {tr(lang, 'Ouvrir le Paper Trading', 'Open Paper Trading')}
          </button>
        </div>
      </div>

      <div className="border-t border-white/[0.07] pt-3 text-[11px] text-[#8B98A4] flex flex-wrap items-center justify-between gap-2">
        <span>
          {tr(
            lang,
            'Ensuite : Strategy Lab pour tester sur le passé, puis Auto-Trade Binance (plans Pro/VIP).',
            'Next: Strategy Lab to test on past data, then Binance Auto-Trade (Pro/VIP plans).'
          )}
        </span>
        <button type="button" onClick={onShowAdvanced} className="text-[#20C997] underline underline-offset-4">
          {tr(lang, 'Afficher les outils avancés', 'Show advanced tools')}
        </button>
      </div>
    </section>
  );
};
