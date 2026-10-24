import React from 'react';
import { AppLang, tr } from '../i18n';

/**
 * Get Started / Learn section (public).
 * The score example mirrors signal_engine.py (_compute_score, check_tf_alignment, _clamp_score):
 * 7 grouped rows = 100 points, then a multi-timeframe modifier (+15 / +5 / 0 / -15), final score clamped to 0-100.
 * Numbers in the example are illustrative, not live market data.
 */

interface LearnSectionProps {
  lang: AppLang;
  onStartDemo: () => void;
  onCreateAccount: () => void;
}

const TOOL_MAP: { fr: [string, string]; en: [string, string] }[] = [
  {
    fr: ['Je veux comprendre un signal', 'Market Intelligence : score, SL/TP et explication, actif par actif.'],
    en: ['I want to understand a signal', 'Market Intelligence: score, SL/TP and explanation, asset by asset.'],
  },
  {
    fr: ["Je veux m'entraîner sans risque", 'Paper Trading : portefeuille virtuel de 10 000 USDT, frais et glissement simulés.'],
    en: ['I want to practice with no risk', 'Paper Trading: virtual 10,000 USDT portfolio with simulated fees and slippage.'],
  },
  {
    fr: ['Je veux être prévenu', 'Alertes & Watchlist : une alerte quand un prix franchit votre seuil.'],
    en: ['I want to be notified', 'Alerts & Watchlist: an alert when a price crosses your level.'],
  },
  {
    fr: ["Je veux tester une idée sur le passé", 'Strategy Lab : backtest d’une stratégie sur des données historiques.'],
    en: ['I want to test an idea on past data', 'Strategy Lab: backtest a strategy on historical data.'],
  },
  {
    fr: ['Je veux affiner les réglages', 'Optimization Lab (avancé) : compare des configurations et détecte le surapprentissage.'],
    en: ['I want to fine-tune settings', 'Optimization Lab (advanced): compares configurations and flags overfitting.'],
  },
  {
    fr: ['Je veux automatiser sur Binance', 'Auto-Trade & Safety (plans Pro/VIP) : ordres réels avec garde-fous. À aborder en dernier.'],
    en: ['I want to automate on Binance', 'Auto-Trade & Safety (Pro/VIP plans): real orders with safeguards. Come to it last.'],
  },
];

const GLOSSARY: { term: string; fr: string; en: string }[] = [
  { term: 'ATR', fr: 'Amplitude moyenne des bougies : mesure la volatilité et fixe la distance du stop-loss.', en: 'Average candle range: measures volatility and sets the stop-loss distance.' },
  { term: 'SMA', fr: 'Moyenne mobile simple : le prix moyen des N dernières bougies (SMA 20 et SMA 50 ici).', en: 'Simple moving average: the average price of the last N candles (SMA 20 and SMA 50 here).' },
  { term: 'RSI', fr: 'Indice de 0 à 100 qui montre si le prix a monté ou baissé trop vite.', en: 'A 0–100 index showing whether price rose or fell too fast.' },
  { term: 'MACD', fr: 'Compare deux moyennes mobiles pour voir si l’élan haussier ou baissier se renforce.', en: 'Compares two moving averages to see whether bullish or bearish momentum is building.' },
  { term: 'ADX', fr: 'Force de la tendance (pas sa direction) : un ADX bas veut dire marché sans direction.', en: 'Trend strength (not direction): a low ADX means a market going nowhere.' },
  { term: 'HTF', fr: 'Higher timeframe : une échelle de temps plus longue (1h, 4h, 1j) pour confirmer la tendance.', en: 'Higher timeframe: a longer time span (1h, 4h, 1d) used to confirm the trend.' },
  { term: 'S/R', fr: 'Support / résistance : zones de prix où le marché a déjà rebondi ou buté.', en: 'Support / resistance: price zones where the market has bounced or stalled before.' },
  { term: 'R:R', fr: 'Gain visé divisé par le risque pris : 2,0 veut dire gagner 2 pour 1 risqué.', en: 'Target gain divided by risk taken: 2.0 means aiming to win 2 for every 1 risked.' },
  { term: 'DCA', fr: 'Dollar-cost averaging : acheter en plusieurs fois pour lisser son prix d’entrée.', en: 'Dollar-cost averaging: buying in several steps to smooth your entry price.' },
  { term: 'Slippage', fr: 'Écart entre le prix attendu et le prix réellement obtenu (0,02 % simulé en paper).', en: 'Gap between the expected price and the price actually filled (0.02% simulated in paper).' },
  { term: 'Confluence', fr: 'Plusieurs indicateurs qui disent la même chose en même temps.', en: 'Several indicators saying the same thing at the same time.' },
];

// Illustrative example, BUY signal, "day" style. Each row: [label fr, label en, points earned, max, why fr, why en]
const EXAMPLE_ROWS: [string, string, number, number, string, string][] = [
  ['Tendance + retour vers la SMA 20', 'Trend + pullback to SMA 20', 23, 25, 'Tendance alignée (15/15) + prix à 0,3 % de la SMA 20 (8/10)', 'Aligned trend (15/15) + price 0.3% from SMA 20 (8/10)'],
  ['Momentum MACD', 'MACD momentum', 20, 20, 'Ligne MACD et histogramme du bon côté', 'MACD line and histogram on the right side'],
  ['Force ADX', 'ADX strength', 10, 15, 'ADX 27 (5) + écart DI de 12 (5)', 'ADX 27 (5) + DI gap of 12 (5)'],
  ['RSI', 'RSI', 10, 10, 'RSI à 58 : zone saine', 'RSI at 58: healthy zone'],
  ['Gain/risque (R:R)', 'Reward/risk (R:R)', 7, 10, 'R:R de 2,3', 'R:R of 2.3'],
  ['Support / résistance', 'Support / resistance', 15, 15, 'Support à 0,8 % sous le prix', 'Support 0.8% below price'],
  ['Volume', 'Volume', 3, 5, 'Volume 1,3× sa moyenne', 'Volume 1.3× its average'],
];
const MTF_BONUS = 15;
const MIN_SCORE_DAY = 65;

export const LearnSection: React.FC<LearnSectionProps> = ({ lang, onStartDemo, onCreateAccount }) => {
  const base = EXAMPLE_ROWS.reduce((n, r) => n + r[2], 0);
  const maxBase = EXAMPLE_ROWS.reduce((n, r) => n + r[3], 0);
  const raw = base + MTF_BONUS;
  const finalScore = Math.max(0, Math.min(100, raw));

  return (
    <section id="learn" className="py-16 border-b border-white/[0.06]">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 space-y-12">
        <header className="space-y-2">
          <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#E8EEF2]">
            {tr(lang, 'Pour commencer', 'Get started')}
          </h2>
          <p className="text-sm text-[#8B98A4] max-w-[64ch]">
            {tr(
              lang,
              "Pas besoin de connaître la finance. Voici quel outil utiliser selon votre objectif, le vocabulaire en une ligne, et comment le score est calculé.",
              'No finance background needed. Here is which tool to use for each goal, the vocabulary in one line, and how the score is calculated.'
            )}
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <button type="button" onClick={onStartDemo} className="px-4 py-2.5 bg-[#20C997] text-[#080C0F] text-xs font-semibold rounded-lg">
              {tr(lang, 'Essayer la démo', 'Try the demo')}
            </button>
            <button type="button" onClick={onCreateAccount} className="px-4 py-2.5 border border-white/15 text-xs text-[#E8EEF2] rounded-lg">
              {tr(lang, 'Créer un compte', 'Create an account')}
            </button>
          </div>
        </header>

        {/* 1. Goal-based tool map */}
        <div className="space-y-3">
          <h3 className="font-display text-lg font-bold">{tr(lang, 'Quel outil pour quel objectif ?', 'Which tool for which goal?')}</h3>
          <ul className="grid sm:grid-cols-2 gap-2.5">
            {TOOL_MAP.map((t, i) => (
              <li key={i} className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-3.5">
                <div className="text-sm font-semibold text-[#E8EEF2]">{lang === 'en' ? t.en[0] : t.fr[0]}</div>
                <div className="text-xs text-[#8B98A4] mt-0.5">{lang === 'en' ? t.en[1] : t.fr[1]}</div>
              </li>
            ))}
          </ul>
        </div>

        {/* 2. Glossary */}
        <div className="space-y-3">
          <h3 className="font-display text-lg font-bold">{tr(lang, 'Vocabulaire en une ligne', 'Vocabulary in one line')}</h3>
          <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2.5">
            {GLOSSARY.map((g) => (
              <div key={g.term} className="flex gap-3 text-xs">
                <dt className="w-20 shrink-0 font-mono-tabular font-semibold text-[#20C997]">{g.term}</dt>
                <dd className="text-[#8B98A4]">{lang === 'en' ? g.en : g.fr}</dd>
              </div>
            ))}
          </dl>
        </div>

        {/* 3. Worked score example */}
        <div className="space-y-4">
          <h3 className="font-display text-lg font-bold">{tr(lang, 'Un score, étape par étape', 'A score, step by step')}</h3>

          <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-4 text-xs space-y-1.5">
            <div className="font-semibold text-[#E8EEF2]">
              {tr(lang, 'Étape 1 : 5 conditions (un signal n’existe que si au moins 4 sur 5 sont vraies)', 'Step 1: 5 conditions (a signal exists only if at least 4 of 5 are true)')}
            </div>
            <div className="text-[#8B98A4]">
              {tr(
                lang,
                '① tendance SMA ② RSI dans sa fenêtre ③ MACD dans le bon sens ④ ADX au-dessus du minimum ⑤ volatilité ATR pas excessive.',
                '① SMA trend ② RSI inside its window ③ MACD pointing the right way ④ ADX above the minimum ⑤ ATR volatility not excessive.'
              )}
            </div>
          </div>

          <div className="bg-[#0D1318] border border-white/[0.07] rounded-lg p-4 space-y-3">
            <div className="text-xs font-semibold text-[#E8EEF2]">
              {tr(lang, `Étape 2 : 7 lignes groupées, ${maxBase} points au maximum`, `Step 2: 7 grouped rows, ${maxBase} points maximum`)}
            </div>
            <ul className="space-y-2.5">
              {EXAMPLE_ROWS.map((r) => (
                <li key={r[0]} className="text-xs">
                  <div className="flex justify-between gap-3">
                    <span className="text-[#E8EEF2]">{lang === 'en' ? r[1] : r[0]}</span>
                    <span className="font-mono-tabular text-[#8B98A4]">{r[2]} / {r[3]}</span>
                  </div>
                  <div className="h-1.5 rounded bg-[#080C0F] mt-1" aria-hidden="true">
                    <div className="h-full rounded bg-[#20C997]" style={{ width: `${(r[2] / r[3]) * 100}%` }} />
                  </div>
                  <div className="text-[11px] text-[#6E7B88] mt-0.5">{lang === 'en' ? r[5] : r[4]}</div>
                </li>
              ))}
            </ul>
            <div className="flex justify-between border-t border-white/10 pt-2 text-xs font-semibold">
              <span>{tr(lang, 'Sous-total', 'Subtotal')}</span>
              <span className="font-mono-tabular">{base} / {maxBase}</span>
            </div>

            <div className="text-xs font-semibold text-[#E8EEF2] pt-2">
              {tr(lang, 'Étape 3 : bonus ou malus multi-timeframes, ajouté après le sous-total', 'Step 3: multi-timeframe bonus or penalty, added after the subtotal')}
            </div>
            <ul className="text-[11px] text-[#8B98A4] space-y-0.5">
              <li>{tr(lang, '+15 : 1h, 4h et 1j vont tous dans le sens du signal', '+15: 1h, 4h and 1d all agree with the signal')}</li>
              <li>{tr(lang, '+5 : 2 échelles sur 3 vont dans le sens du signal', '+5: 2 of 3 timeframes agree with the signal')}</li>
              <li>{tr(lang, '0 : pas d’avis net', '0: no clear view')}</li>
              <li>{tr(lang, '−15 : les échelles se contredisent', '−15: the timeframes contradict each other')}</li>
            </ul>
            <div className="flex justify-between text-xs">
              <span>{tr(lang, 'Dans cet exemple : bonus +15', 'In this example: +15 bonus')}</span>
              <span className="font-mono-tabular text-[#20C997]">{base} + {MTF_BONUS} = {raw}</span>
            </div>

            <div className="rounded-lg border border-[#D6A84F]/40 bg-[#D6A84F]/10 p-3 text-xs space-y-1">
              <div className="font-semibold text-[#E2BC6A]">
                {tr(lang, `Plafond : le score final est limité à 100 (affiché : ${finalScore})`, `Cap: the final score is limited to 100 (shown: ${finalScore})`)}
              </div>
              <div className="text-[#8B98A4]">
                {tr(
                  lang,
                  `${raw} dépasse 100, donc le score affiché est ${finalScore}. Il est aussi limité à 0 en bas.`,
                  `${raw} is above 100, so the score shown is ${finalScore}. It is also floored at 0.`
                )}
              </div>
            </div>
            <div className="text-xs text-[#8B98A4]">
              {tr(
                lang,
                `Étape 4 : le signal n’est retenu que si le score atteint le minimum du style (${MIN_SCORE_DAY} en day trading) et si l’ADX et le R:R minimums sont respectés.`,
                `Step 4: the signal is kept only if the score reaches the style minimum (${MIN_SCORE_DAY} for day trading) and the minimum ADX and R:R are met.`
              )}
            </div>
          </div>
          <p className="text-[11px] text-[#6E7B88]">
            {tr(
              lang,
              'Exemple pédagogique avec des chiffres fictifs, pas un signal en direct. Pas un conseil financier.',
              'Teaching example with made-up numbers, not a live signal. Not financial advice.'
            )}
          </p>
        </div>
      </div>
    </section>
  );
};
