import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  FlaskConical,
  Play,
  RotateCcw,
  Save,
  Copy,
  Download,
  TrendingUp,
  ShieldCheck,
  Sliders,
  GitCompare,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Bookmark,
  Trash2,
  Eye,
  Filter,
  Layers,
  Activity,
} from 'lucide-react';
import { apiFetch } from '../api';
import { AppLang, tr } from '../i18n';
import {
  StrategyLabParams,
  StrategyLabPreset,
  StrategyLabRun,
  StrategyLabTrade,
  StrategyLabModelMeta,
  StrategyLabParamSpec,
  StrategyLabParamDiff,
  StrategyLabSchema,
} from '../types';

const DEFAULT_LAB_MODELS: StrategyLabModelMeta[] = [
  {
    id: 'confluence',
    name: 'Signal & Confluence Model',
    name_fr: 'Modèle Signal & Confluence (Teddy Score)',
    description:
      "Gouverne le seuil Teddy Score, les directions autorisées (Long/Short), les filtres d'alignement EMA/MACD/Tendance et les seuils de régime (ADX, ATR%, Volume, Cooldown).",
    is_strategy_model: true,
  },
  {
    id: 'indicators',
    name: 'Technical Indicators Model',
    name_fr: 'Modèle Indicateurs Techniques (EMA / RSI / ADX / ATR / Volume)',
    description:
      "Définit les périodes de calcul des moyennes mobiles exponentielles, du RSI (et ses bornes survente/surachat), de l'ADX, de l'ATR et de la moyenne mobile de volume.",
    is_strategy_model: true,
  },
  {
    id: 'exits',
    name: 'Exit & Protection Model',
    name_fr: 'Modèle Sorties & Protection (SL / TP / Break-Even / Trailing)',
    description:
      'Contrôle le calcul du Stop Loss, du Take Profit, du ratio R:R minimum, de la prise de profit partielle (TP1), du Break-Even, du Trailing Stop ATR et de la durée maximale en position.',
    is_strategy_model: true,
  },
  {
    id: 'capital',
    name: 'Capital, Sizing & Execution Simulation Model',
    name_fr: 'Modèle Capital, Sizing & Frais de Simulation',
    description:
      'Configure le capital initial simulé, le mode de dimensionnement des positions, le levier, les frais Taker, le slippage et les coupe-circuits journaliers.',
    is_strategy_model: false,
  },
];

const DEFAULT_LAB_PARAM_SPECS: Record<keyof StrategyLabParams, StrategyLabParamSpec> = {
  min_teddy_score: { model: 'confluence', type: 'int', min: 20, max: 95, unit: '/100', label_fr: "Score Teddy Minimum d'Entrée", label_en: 'Minimum Entry Teddy Score' },
  allow_long: { model: 'confluence', type: 'bool', unit: '', label_fr: 'Autoriser les positions LONG (BUY)', label_en: 'Allow LONG (BUY) positions' },
  allow_short: { model: 'confluence', type: 'bool', unit: '', label_fr: 'Autoriser les positions SHORT (SELL)', label_en: 'Allow SHORT (SELL) positions' },
  require_ema_alignment: { model: 'confluence', type: 'bool', unit: '', label_fr: 'Exiger alignement EMA rapide / lente', label_en: 'Require Fast / Slow EMA alignment' },
  require_macd_confirmation: { model: 'confluence', type: 'bool', unit: '', label_fr: 'Exiger confirmation impulsion MACD', label_en: 'Require MACD momentum confirmation' },
  require_trend_filter_ema200: { model: 'confluence', type: 'bool', unit: '', label_fr: 'Filtre directionnel strict EMA tendance', label_en: 'Strict directional Trend EMA filter' },
  block_against_strong_trend: { model: 'confluence', type: 'bool', unit: '', label_fr: 'Protection anti contre-tendance forte (ADX >= 30)', label_en: 'Strong counter-trend protection (ADX >= 30)' },
  adx_min: { model: 'confluence', type: 'float', min: 5, max: 60, unit: 'pts', label_fr: 'Seuil ADX Minimum (Force de tendance)', label_en: 'Minimum ADX Threshold (Trend strength)' },
  min_atr_pct: { model: 'confluence', type: 'float', min: 0, max: 5, unit: '%', label_fr: 'Volatilité ATR Minimum (%)', label_en: 'Minimum ATR Volatility (%)' },
  min_volume_ratio: { model: 'confluence', type: 'float', min: 0, max: 5, unit: 'x', label_fr: 'Ratio Volume Minimum (vs MA)', label_en: 'Minimum Volume Ratio (vs MA)' },
  cooldown_candles: { model: 'confluence', type: 'int', min: 0, max: 100, unit: 'candles', label_fr: 'Cooldown après clôture (bougies)', label_en: 'Post-trade Cooldown (candles)' },

  ema_fast: { model: 'indicators', type: 'int', min: 3, max: 100, unit: 'bars', label_fr: 'Période EMA Rapide', label_en: 'Fast EMA Period' },
  ema_slow: { model: 'indicators', type: 'int', min: 5, max: 250, unit: 'bars', label_fr: 'Période EMA Lente', label_en: 'Slow EMA Period' },
  ema_trend: { model: 'indicators', type: 'int', min: 20, max: 500, unit: 'bars', label_fr: 'Période EMA Tendance', label_en: 'Trend EMA Period' },
  rsi_period: { model: 'indicators', type: 'int', min: 4, max: 50, unit: 'bars', label_fr: 'Période RSI', label_en: 'RSI Period' },
  rsi_oversold: { model: 'indicators', type: 'float', min: 10, max: 49, unit: 'pts', label_fr: 'Seuil RSI Survente', label_en: 'RSI Oversold Threshold' },
  rsi_overbought: { model: 'indicators', type: 'float', min: 51, max: 90, unit: 'pts', label_fr: 'Seuil RSI Surachat', label_en: 'RSI Overbought Threshold' },
  adx_period: { model: 'indicators', type: 'int', min: 5, max: 50, unit: 'bars', label_fr: 'Période ADX', label_en: 'ADX Period' },
  atr_period: { model: 'indicators', type: 'int', min: 5, max: 50, unit: 'bars', label_fr: 'Période ATR', label_en: 'ATR Period' },
  volume_ma_period: { model: 'indicators', type: 'int', min: 5, max: 100, unit: 'bars', label_fr: 'Période Moyenne Mobile Volume', label_en: 'Volume Moving Average Period' },

  sl_mode: { model: 'exits', type: 'enum', choices: ['atr', 'fixed_pct'], unit: '', label_fr: 'Mode de calcul Stop Loss', label_en: 'Stop Loss Calculation Mode' },
  sl_atr_mult: { model: 'exits', type: 'float', min: 0.3, max: 10, unit: 'xATR', label_fr: 'Multiplicateur Stop Loss (ATR)', label_en: 'Stop Loss ATR Multiplier' },
  sl_fixed_pct: { model: 'exits', type: 'float', min: 0.1, max: 25, unit: '%', label_fr: 'Distance Stop Loss Fixe (%)', label_en: 'Fixed Stop Loss Distance (%)' },
  tp_mode: { model: 'exits', type: 'enum', choices: ['rr', 'atr', 'fixed_pct'], unit: '', label_fr: 'Mode de calcul Take Profit', label_en: 'Take Profit Calculation Mode' },
  min_rr_ratio: { model: 'exits', type: 'float', min: 0.5, max: 10, unit: 'R', label_fr: 'Ratio Risque/Rendement (R:R) Minimum', label_en: 'Minimum Risk/Reward (R:R) Ratio' },
  tp_atr_mult: { model: 'exits', type: 'float', min: 0.5, max: 20, unit: 'xATR', label_fr: 'Multiplicateur Take Profit (ATR)', label_en: 'Take Profit ATR Multiplier' },
  tp_fixed_pct: { model: 'exits', type: 'float', min: 0.2, max: 50, unit: '%', label_fr: 'Distance Take Profit Fixe (%)', label_en: 'Fixed Take Profit Distance (%)' },
  partial_tp_enabled: { model: 'exits', type: 'bool', unit: '', label_fr: 'Activer Take Profit Partiel (TP1)', label_en: 'Enable Partial Take Profit (TP1)' },
  partial_tp_rr: { model: 'exits', type: 'float', min: 0.3, max: 10, unit: 'R', label_fr: 'Seuil de déclenchement TP Partiel (en R)', label_en: 'Partial TP Trigger (in R)' },
  partial_tp_close_pct: { model: 'exits', type: 'float', min: 10, max: 90, unit: '%', label_fr: 'Pourcentage clôturé au TP Partiel (%)', label_en: 'Position Closed at Partial TP (%)' },
  breakeven_enabled: { model: 'exits', type: 'bool', unit: '', label_fr: 'Activer mise à Break-Even automatique', label_en: 'Enable Automatic Break-Even' },
  breakeven_trigger_rr: { model: 'exits', type: 'float', min: 0.3, max: 10, unit: 'R', label_fr: "Seuil d'activation Break-Even (en R)", label_en: 'Break-Even Activation Threshold (in R)' },
  trailing_stop_enabled: { model: 'exits', type: 'bool', unit: '', label_fr: 'Activer Trailing Stop Dynamique (ATR)', label_en: 'Enable Dynamic ATR Trailing Stop' },
  trailing_activation_rr: { model: 'exits', type: 'float', min: 0.4, max: 10, unit: 'R', label_fr: "Seuil d'activation Trailing Stop (en R)", label_en: 'Trailing Stop Activation Threshold (in R)' },
  trailing_distance_atr: { model: 'exits', type: 'float', min: 0.3, max: 10, unit: 'xATR', label_fr: 'Distance de suivi Trailing Stop (x ATR)', label_en: 'Trailing Stop Distance (x ATR)' },
  exit_on_opposite_signal: { model: 'exits', type: 'bool', unit: '', label_fr: 'Clôturer sur signal opposé validé', label_en: 'Exit on Validated Opposite Signal' },
  max_bars_in_trade: { model: 'exits', type: 'int', min: 4, max: 1000, unit: 'candles', label_fr: "Durée maximale d'une position (bougies)", label_en: 'Maximum Bars Held in Trade' },

  initial_capital: { model: 'capital', type: 'float', min: 100, max: 10000000, unit: 'USDT', label_fr: 'Capital Initial Simulé (USDT)', label_en: 'Simulated Initial Capital (USDT)' },
  position_sizing_mode: { model: 'capital', type: 'enum', choices: ['risk_pct', 'capital_pct', 'fixed_usdt'], unit: '', label_fr: 'Mode de Dimensionnement (Position Sizing)', label_en: 'Position Sizing Mode' },
  risk_per_trade_pct: { model: 'capital', type: 'float', min: 0.1, max: 25, unit: '%', label_fr: 'Risque par Trade (% du capital)', label_en: 'Risk per Trade (% of capital)' },
  fixed_position_usdt: { model: 'capital', type: 'float', min: 10, max: 1000000, unit: 'USDT', label_fr: 'Mise Fixe par Position (USDT)', label_en: 'Fixed Position Size (USDT)' },
  capital_allocation_pct: { model: 'capital', type: 'float', min: 1, max: 100, unit: '%', label_fr: 'Allocation Capital par Position (%)', label_en: 'Capital Allocation per Position (%)' },
  leverage: { model: 'capital', type: 'float', min: 1, max: 50, unit: 'x', label_fr: 'Levier Simulé (x)', label_en: 'Simulated Leverage (x)' },
  fee_bps: { model: 'capital', type: 'float', min: 0, max: 100, unit: 'bps', label_fr: 'Frais Taker Simulés (bps)', label_en: 'Simulated Taker Fee (bps)' },
  slippage_bps: { model: 'capital', type: 'float', min: 0, max: 100, unit: 'bps', label_fr: 'Slippage Estimé par Ordre (bps)', label_en: 'Estimated Slippage per Order (bps)' },
  max_open_positions: { model: 'capital', type: 'int', min: 1, max: 1, unit: 'pos', label_fr: 'Positions Simultanées Max', label_en: 'Max Simultaneous Open Positions' },
  max_trades_per_day: { model: 'capital', type: 'int', min: 1, max: 100, unit: 'trades/d', label_fr: 'Nombre Maximum de Trades par Jour', label_en: 'Max Trades per Day' },
  max_consecutive_losses: { model: 'capital', type: 'int', min: 1, max: 50, unit: 'losses', label_fr: 'Coupe-circuit Pertes Consécutives Max', label_en: 'Max Consecutive Losses Circuit Breaker' },
};

function formatRawConfigText(
  params: StrategyLabParams,
  selectedModels: string[],
  modelsCatalog: StrategyLabModelMeta[] = DEFAULT_LAB_MODELS,
  paramSpecs: Record<keyof StrategyLabParams, StrategyLabParamSpec> = DEFAULT_LAB_PARAM_SPECS
): string {
  const lines: string[] = [];
  for (const m of modelsCatalog) {
    if (!selectedModels.includes(m.id)) continue;
    const keys = (Object.keys(paramSpecs) as (keyof StrategyLabParams)[]).filter(
      (k) => paramSpecs[k]?.model === m.id
    );
    if (!keys.length) continue;
    if (lines.length > 0) lines.push('');
    lines.push(`# [${m.name}]`);
    for (const k of keys) {
      const val = params[k];
      const valStr = typeof val === 'boolean' ? (val ? 'true' : 'false') : String(val);
      lines.push(`${k}=${valStr}`);
    }
  }
  return lines.join('\n');
}

const EquityAndDrawdownChart: React.FC<{
  data: NonNullable<StrategyLabRun['equity_curve']>;
  initialCapital: number;
  lang?: AppLang;
}> = ({ data, initialCapital, lang = 'fr' }) => {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (!data || data.length < 2) {
    return (
      <div className="h-64 flex items-center justify-center text-xs text-[#64748B]">
        {tr(lang, "Données d'équité insuffisantes.", 'Insufficient equity data.')}
      </div>
    );
  }

  const width = 920;
  const eqHeight = 220;
  const ddHeight = 85;
  const padL = 12;
  const padR = 64;
  const padT = 14;
  const padB = 18;
  const plotW = width - padL - padR;
  const eqPlotH = eqHeight - padT - padB;
  const ddPlotH = ddHeight - 10 - 16;

  const equities = data.map((d) => d.equity);
  const minEq = Math.min(initialCapital * 0.98, ...equities);
  const maxEq = Math.max(initialCapital * 1.02, ...equities);
  const eqRange = Math.max(1, maxEq - minEq);

  const dds = data.map((d) => d.drawdown_pct);
  const minDd = Math.min(-1, ...dds);

  const getX = (i: number) => padL + (i / Math.max(1, data.length - 1)) * plotW;
  const getEqY = (val: number) => padT + eqPlotH - ((val - minEq) / eqRange) * eqPlotH;
  const getDdY = (val: number) => 10 + (Math.abs(val) / Math.max(0.5, Math.abs(minDd))) * ddPlotH;

  const eqPoints = data.map((d, i) => `${getX(i).toFixed(1)},${getEqY(d.equity).toFixed(1)}`).join(' ');
  const eqArea = `${getX(0).toFixed(1)},${(padT + eqPlotH).toFixed(1)} ${eqPoints} ${getX(data.length - 1).toFixed(1)},${(padT + eqPlotH).toFixed(1)}`;

  const ddPoints = data.map((d, i) => `${getX(i).toFixed(1)},${getDdY(d.drawdown_pct).toFixed(1)}`).join(' ');
  const ddArea = `${getX(0).toFixed(1)},10 ${ddPoints} ${getX(data.length - 1).toFixed(1)},10`;

  const initY = getEqY(initialCapital);
  const activePoint = hoverIdx !== null && data[hoverIdx] ? data[hoverIdx] : data[data.length - 1];

  return (
    <div className="space-y-2 select-none">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono-tabular px-2 py-1.5 rounded bg-[#090D16] border border-white/[0.06]">
        <span className="text-[#94A3B8]">
          Date : <strong className="text-[#F1F5F9]">{String(activePoint.timestamp).slice(0, 16).replace('T', ' ')}</strong>
        </span>
        <span className="text-[#94A3B8]">
          {tr(lang, 'Équité :', 'Equity:')} <strong className="text-[#10B981]">{activePoint.equity.toLocaleString()} USDT</strong>
        </span>
        <span className="text-[#94A3B8]">
          Drawdown : <strong className="text-[#F43F5E]">{activePoint.drawdown_pct.toFixed(2)}%</strong>
        </span>
        <span className="text-[#94A3B8]">
          {tr(lang, 'Prix Actif :', 'Asset Price:')} <strong className="text-[#F1F5F9]">{activePoint.price.toLocaleString()} USDT</strong>
        </span>
      </div>

      {/* Equity SVG */}
      <svg
        viewBox={`0 0 ${width} ${eqHeight}`}
        className="w-full h-56 bg-[#090D16]/70 rounded-lg border border-white/[0.05] overflow-visible"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const relX = ((e.clientX - rect.left) / rect.width) * width;
          const idx = Math.round(((relX - padL) / plotW) * (data.length - 1));
          if (idx >= 0 && idx < data.length) setHoverIdx(idx);
        }}
        onMouseLeave={() => setHoverIdx(null)}
      >
        <defs>
          <linearGradient id="svgLabEq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = padT + t * eqPlotH;
          const val = maxEq - t * eqRange;
          return (
            <g key={t}>
              <line x1={padL} y1={y} x2={width - padR} y2={y} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
              <text x={width - padR + 6} y={y + 3} fill="#64748B" fontSize="10" fontFamily="JetBrains Mono, monospace">
                {Math.round(val).toLocaleString()}$
              </text>
            </g>
          );
        })}

        <line
          x1={padL}
          y1={initY}
          x2={width - padR}
          y2={initY}
          stroke="rgba(148,163,184,0.45)"
          strokeDasharray="4 4"
        />
        <polygon points={eqArea} fill="url(#svgLabEq)" />
        <polyline fill="none" stroke="#10B981" strokeWidth="2" points={eqPoints} />

        {hoverIdx !== null && data[hoverIdx] && (
          <g>
            <line
              x1={getX(hoverIdx)}
              y1={padT}
              x2={getX(hoverIdx)}
              y2={padT + eqPlotH}
              stroke="rgba(255,255,255,0.25)"
              strokeDasharray="2 2"
            />
            <circle
              cx={getX(hoverIdx)}
              cy={getEqY(data[hoverIdx].equity)}
              r={4}
              fill="#10B981"
              stroke="#090D16"
              strokeWidth={2}
            />
          </g>
        )}
      </svg>

      {/* Underwater Drawdown SVG */}
      <svg
        viewBox={`0 0 ${width} ${ddHeight}`}
        className="w-full h-24 bg-[#090D16]/70 rounded-lg border border-white/[0.05]"
      >
        <polygon points={ddArea} fill="rgba(244,63,94,0.22)" />
        <polyline fill="none" stroke="#F43F5E" strokeWidth="1.5" points={ddPoints} />
        <text x={width - padR + 6} y={16} fill="#64748B" fontSize="9" fontFamily="JetBrains Mono, monospace">
          0.0%
        </text>
        <text
          x={width - padR + 6}
          y={10 + ddPlotH}
          fill="#F43F5E"
          fontSize="9"
          fontFamily="JetBrains Mono, monospace"
        >
          {minDd.toFixed(1)}%
        </text>
      </svg>
    </div>
  );
};

const LabCandlesSignalsChart: React.FC<{
  candles: NonNullable<StrategyLabRun['candles']>;
  trades: StrategyLabTrade[];
  params: StrategyLabParams;
  selectedTrade: StrategyLabTrade | null;
  onSelectTrade: (trade: StrategyLabTrade | null) => void;
  onInspectInJournal?: (trade: StrategyLabTrade) => void;
  lang?: AppLang;
}> = ({
  candles,
  trades,
  params,
  selectedTrade,
  onSelectTrade,
  onInspectInJournal,
  lang = 'fr',
}) => {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [clickedMarkerCandleIdx, setClickedMarkerCandleIdx] = useState<number | null>(null);

  if (!candles || candles.length < 2) {
    return (
      <div className="h-80 flex items-center justify-center text-xs text-[#64748B]">
        {lang === 'en' ? 'No candles available.' : 'Aucune bougie disponible.'}
      </div>
    );
  }

  const width = 920;
  const height = 380;
  const padL = 12;
  const padR = 68;
  const padT = 18;
  const padB = 24;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const prices: number[] = [];
  candles.forEach((c) => {
    prices.push(c.high, c.low, c.ema_fast, c.ema_slow);
  });
  if (selectedTrade) {
    if (selectedTrade.sl_initial) prices.push(selectedTrade.sl_initial);
    if (selectedTrade.tp_initial) prices.push(selectedTrade.tp_initial);
  }
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const pRange = Math.max(0.0001, maxP - minP);

  const getX = (i: number) => padL + (i / Math.max(1, candles.length - 1)) * plotW;
  const getY = (val: number) => padT + plotH - ((val - minP) / pRange) * plotH;

  const closeLine = candles.map((c, i) => `${getX(i).toFixed(1)},${getY(c.close).toFixed(1)}`).join(' ');
  const emaFastLine = candles.map((c, i) => `${getX(i).toFixed(1)},${getY(c.ema_fast).toFixed(1)}`).join(' ');
  const emaSlowLine = candles.map((c, i) => `${getX(i).toFixed(1)},${getY(c.ema_slow).toFixed(1)}`).join(' ');
  const emaTrendLine = candles.map((c, i) => `${getX(i).toFixed(1)},${getY(c.ema_trend).toFixed(1)}`).join(' ');

  // Resolve trade for a marker candle
  const resolveTradeForCandle = (candleIdx: number): StrategyLabTrade | null => {
    const c = candles[candleIdx];
    if (!c || !c.marker) return null;
    if (c.marker.trade_id) {
      const byId = trades.find((t) => t.id === c.marker?.trade_id);
      if (byId) return byId;
    }
    const byIndex = trades.find(
      (t) => t.entry_index === c.index || t.exit_index === c.index
    );
    if (byIndex) return byIndex;
    const byTime = trades.find(
      (t) => t.entry_time === c.timestamp || t.exit_time === c.timestamp
    );
    return byTime || null;
  };

  // Find chart indices for selectedTrade entry and exit so we can draw a trade trajectory line
  const selectedEntryChartIdx = selectedTrade
    ? candles.findIndex(
        (c) =>
          (c.marker?.type === 'ENTRY' && c.marker?.trade_id === selectedTrade.id) ||
          c.index === selectedTrade.entry_index ||
          c.timestamp === selectedTrade.entry_time
      )
    : -1;

  const selectedExitChartIdx = selectedTrade
    ? candles.findIndex(
        (c) =>
          (c.marker?.type === 'EXIT' && c.marker?.trade_id === selectedTrade.id) ||
          c.index === selectedTrade.exit_index ||
          c.timestamp === selectedTrade.exit_time
      )
    : -1;

  const markerIndices = candles
    .map((c, idx) => (c.marker ? idx : -1))
    .filter((idx) => idx >= 0);

  const handleMarkerClick = (candleIdx: number, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setClickedMarkerCandleIdx(candleIdx);
    const matched = resolveTradeForCandle(candleIdx);
    if (matched) {
      onSelectTrade(matched);
    }
  };

  const activeC =
    hoverIdx !== null && candles[hoverIdx]
      ? candles[hoverIdx]
      : clickedMarkerCandleIdx !== null && candles[clickedMarkerCandleIdx]
      ? candles[clickedMarkerCandleIdx]
      : candles[candles.length - 1];

  const clickedCandle =
    clickedMarkerCandleIdx !== null && candles[clickedMarkerCandleIdx]
      ? candles[clickedMarkerCandleIdx]
      : null;

  return (
    <div className="space-y-3 select-none">
      {/* Top live cursor readout bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono-tabular px-3 py-2 rounded-lg bg-[#090D16] border border-white/[0.06]">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[#94A3B8]">
            {String(activeC.timestamp).slice(0, 16).replace('T', ' ')}
          </span>
          <span>
            Close : <strong className="text-[#F1F5F9]">{activeC.close}</strong>
          </span>
          <span className="text-[#10B981]">
            EMA({params.ema_fast}) : {activeC.ema_fast}
          </span>
          <span className="text-[#3B82F6]">
            EMA({params.ema_slow}) : {activeC.ema_slow}
          </span>
          <span className="text-[#94A3B8]">
            RSI : <strong className="text-[#F1F5F9]">{activeC.rsi}</strong> | ADX :{' '}
            <strong className="text-[#F1F5F9]">{activeC.adx}</strong>
          </span>
        </div>

        <div className="flex items-center gap-2">
          {activeC.marker ? (
            <span
              className={`px-2 py-0.5 rounded font-bold ${
                activeC.marker.side === 'BUY'
                  ? 'bg-[#10B981]/20 text-[#10B981]'
                  : 'bg-[#F43F5E]/20 text-[#FB7185]'
              }`}
            >
              {activeC.marker.type} {activeC.marker.side} @ {activeC.marker.price}
            </span>
          ) : (
            <span className="text-[11px] text-[#64748B]">
              {lang === 'en'
                ? `Click any marker (${markerIndices.length}) on the timeline to inspect trade`
                : `Cliquez sur un marqueur (${markerIndices.length}) du graphique pour inspecter le trade`}
            </span>
          )}
        </div>
      </div>

      {/* Main SVG Price & Signals Timeline */}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-88 bg-[#090D16]/85 rounded-xl border border-white/[0.07] cursor-crosshair"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const relX = ((e.clientX - rect.left) / rect.width) * width;
          const idx = Math.round(((relX - padL) / plotW) * (candles.length - 1));
          if (idx >= 0 && idx < candles.length) setHoverIdx(idx);
        }}
        onMouseLeave={() => setHoverIdx(null)}
        onClick={(e) => {
          // Clicking anywhere near a marker on the price timeline selects that marker
          const rect = e.currentTarget.getBoundingClientRect();
          const relX = ((e.clientX - rect.left) / rect.width) * width;
          const clickedIdx = Math.round(((relX - padL) / plotW) * (candles.length - 1));
          if (markerIndices.length === 0) return;
          let nearestIdx = -1;
          let minDist = Infinity;
          for (const mIdx of markerIndices) {
            const dist = Math.abs(mIdx - clickedIdx);
            if (dist < minDist) {
              minDist = dist;
              nearestIdx = mIdx;
            }
          }
          const maxSnapDistance = Math.max(4, Math.round(candles.length * 0.03));
          if (nearestIdx >= 0 && minDist <= maxSnapDistance) {
            handleMarkerClick(nearestIdx);
          }
        }}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = padT + t * plotH;
          const val = maxP - t * pRange;
          return (
            <g key={t}>
              <line x1={padL} y1={y} x2={width - padR} y2={y} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
              <text x={width - padR + 6} y={y + 3} fill="#64748B" fontSize="10" fontFamily="JetBrains Mono, monospace">
                {val.toFixed(val > 100 ? 0 : 2)}
              </text>
            </g>
          );
        })}

        {/* Selected Trade SL / TP / Entry horizontal reference lines & connecting path */}
        {selectedTrade && (
          <g>
            {selectedTrade.tp_initial > 0 && (
              <g>
                <line
                  x1={padL}
                  y1={getY(selectedTrade.tp_initial)}
                  x2={width - padR}
                  y2={getY(selectedTrade.tp_initial)}
                  stroke="rgba(16,185,129,0.45)"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
                <text
                  x={padL + 6}
                  y={Math.max(padT + 10, getY(selectedTrade.tp_initial) - 4)}
                  fill="#10B981"
                  fontSize="9"
                  fontFamily="JetBrains Mono, monospace"
                >
                  TP #{selectedTrade.id}: {selectedTrade.tp_initial}
                </text>
              </g>
            )}
            {selectedTrade.sl_initial > 0 && (
              <g>
                <line
                  x1={padL}
                  y1={getY(selectedTrade.sl_initial)}
                  x2={width - padR}
                  y2={getY(selectedTrade.sl_initial)}
                  stroke="rgba(244,63,94,0.45)"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
                <text
                  x={padL + 6}
                  y={Math.min(padT + plotH - 4, getY(selectedTrade.sl_initial) + 11)}
                  fill="#FB7185"
                  fontSize="9"
                  fontFamily="JetBrains Mono, monospace"
                >
                  SL #{selectedTrade.id}: {selectedTrade.sl_initial}
                </text>
              </g>
            )}
            {selectedEntryChartIdx >= 0 && selectedExitChartIdx >= 0 && (
              <line
                x1={getX(selectedEntryChartIdx)}
                y1={getY(candles[selectedEntryChartIdx].close)}
                x2={getX(selectedExitChartIdx)}
                y2={getY(candles[selectedExitChartIdx].close)}
                stroke={selectedTrade.pnl_usdt >= 0 ? '#10B981' : '#F43F5E'}
                strokeWidth="2.2"
                strokeDasharray="3 3"
              />
            )}
          </g>
        )}

        <polyline fill="none" stroke="#F59E0B" strokeWidth="1.2" strokeDasharray="4 4" points={emaTrendLine} />
        <polyline fill="none" stroke="#3B82F6" strokeWidth="1.3" points={emaSlowLine} />
        <polyline fill="none" stroke="#10B981" strokeWidth="1.3" points={emaFastLine} />
        <polyline fill="none" stroke="#F1F5F9" strokeWidth="1.6" points={closeLine} />

        {/* Interactive Entry & Exit Signal Markers */}
        {candles.map((c, i) => {
          if (!c.marker) return null;
          const cx = getX(i);
          const cy = getY(c.close);
          const isBuy = c.marker.side === 'BUY';
          const isEntry = c.marker.type === 'ENTRY';
          const color = isBuy ? '#10B981' : '#F43F5E';
          const matchedTrade = resolveTradeForCandle(i);
          const isSelected =
            clickedMarkerCandleIdx === i ||
            (selectedTrade !== null && matchedTrade?.id === selectedTrade.id);

          return (
            <g
              key={i}
              className="cursor-pointer"
              onClick={(e) => handleMarkerClick(i, e)}
            >
              {/* Larger invisible hit target for easy clicking */}
              <circle cx={cx} cy={cy} r={12} fill="transparent" />
              {isSelected && (
                <circle
                  cx={cx}
                  cy={cy}
                  r={10}
                  fill="none"
                  stroke={color}
                  strokeWidth={1.8}
                  strokeOpacity={0.75}
                />
              )}
              <circle
                cx={cx}
                cy={cy}
                r={isSelected ? 7 : isEntry ? 5.5 : 4.5}
                fill={isEntry ? color : '#090D16'}
                stroke={isSelected ? '#F8FAFC' : color}
                strokeWidth={isSelected ? 2.4 : 2}
              />
              {isSelected && (
                <text
                  x={Math.min(width - padR - 55, Math.max(padL + 4, cx - 22))}
                  y={Math.max(padT + 12, cy - 12)}
                  fill="#F8FAFC"
                  fontSize="9.5"
                  fontWeight="bold"
                  fontFamily="JetBrains Mono, monospace"
                >
                  {isEntry ? '▲ IN' : '◆ OUT'} #{matchedTrade?.id || c.marker.trade_id || ''}
                </text>
              )}
            </g>
          );
        })}

        {hoverIdx !== null && candles[hoverIdx] && (
          <line
            x1={getX(hoverIdx)}
            y1={padT}
            x2={getX(hoverIdx)}
            y2={padT + plotH}
            stroke="rgba(255,255,255,0.25)"
            strokeDasharray="2 2"
          />
        )}
      </svg>

      {/* Quick timeline marker pills so user can also step through markers directly */}
      {markerIndices.length > 0 && (
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 pt-0.5 text-[11px] font-mono-tabular">
          <span className="text-[#64748B] shrink-0 mr-1">
            {lang === 'en' ? 'Markers:' : 'Marqueurs :'}
          </span>
          {markerIndices.slice(0, 24).map((mIdx) => {
            const mc = candles[mIdx];
            const m = mc.marker!;
            const tMatch = resolveTradeForCandle(mIdx);
            const active =
              clickedMarkerCandleIdx === mIdx ||
              (selectedTrade !== null && tMatch?.id === selectedTrade.id);
            return (
              <button
                key={mIdx}
                type="button"
                onClick={() => handleMarkerClick(mIdx)}
                className={`px-2 py-1 rounded border shrink-0 transition-colors flex items-center gap-1 ${
                  active
                    ? 'bg-[#10B981]/20 border-[#10B981] text-[#F1F5F9]'
                    : 'bg-[#090D16] border-white/10 text-[#94A3B8] hover:text-[#F1F5F9] hover:border-white/25'
                }`}
              >
                <span className={m.side === 'BUY' ? 'text-[#10B981]' : 'text-[#FB7185]'}>
                  {m.type === 'ENTRY' ? '▲' : '◆'} {m.type}
                </span>
                <span>#{tMatch?.id || m.trade_id || ''}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Interactive Clicked Marker / Selected Trade Inspector Panel */}
      {(selectedTrade || clickedCandle?.marker) && (
        <div className="bg-[#0B101B] border border-[#10B981]/40 rounded-xl p-4 space-y-3 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {selectedTrade ? (
                <>
                  <span
                    className={`px-2.5 py-0.5 rounded text-xs font-mono-tabular font-bold ${
                      selectedTrade.side === 'BUY'
                        ? 'bg-[#10B981]/20 text-[#10B981]'
                        : 'bg-[#F43F5E]/20 text-[#FB7185]'
                    }`}
                  >
                    TRADE #{selectedTrade.id} • {selectedTrade.side}
                  </span>
                  {clickedCandle?.marker && (
                    <span className="px-2 py-0.5 rounded bg-white/[0.06] text-[11px] font-mono-tabular text-[#E2E8F0]">
                      {clickedCandle.marker.type === 'ENTRY'
                        ? tr(lang, "Marqueur d'Entrée sélectionné", 'Entry Marker selected')
                        : tr(lang, 'Marqueur de Sortie sélectionné', 'Exit Marker selected')}
                    </span>
                  )}
                  <span className="text-xs font-mono-tabular text-[#94A3B8]">
                    Teddy Score : <strong className="text-[#F1F5F9]">{selectedTrade.teddy_score}/100</strong>
                  </span>
                  <span className="text-xs font-mono-tabular text-[#94A3B8]">
                    • {tr(lang, ' Motif de sortie :', ' Exit reason:')}{' '}
                    <strong className="text-[#F1F5F9]">{selectedTrade.exit_reason}</strong>
                  </span>
                </>
              ) : (
                clickedCandle?.marker && (
                  <span className="px-2.5 py-0.5 rounded text-xs font-mono-tabular font-bold bg-[#10B981]/20 text-[#10B981]">
                    {clickedCandle.marker.type} • {clickedCandle.marker.side} @ {clickedCandle.marker.price}
                  </span>
                )
              )}
            </div>

            <div className="flex items-center gap-2">
              {selectedTrade && onInspectInJournal && (
                <button
                  type="button"
                  onClick={() => onInspectInJournal(selectedTrade)}
                  className="px-2.5 py-1 rounded bg-[#1E293B] hover:bg-[#334155] text-[11px] text-[#60A5FA] font-medium transition-colors"
                >
                  {tr(lang, 'Ouvrir dans le Journal →', 'Open in Trade Journal →')}
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setClickedMarkerCandleIdx(null);
                  onSelectTrade(null);
                }}
                className="text-xs text-[#94A3B8] hover:text-[#F1F5F9] px-2 py-1"
              >
                {tr(lang, 'Fermer ✕', 'Close ✕')}
              </button>
            </div>
          </div>

          {selectedTrade ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 text-xs font-mono-tabular">
                <div className="p-2.5 rounded-lg bg-[#111827] border border-white/[0.05]">
                  <div className="text-[10px] text-[#64748B]">{tr(lang, 'Entrée (Date & Prix)', 'Entry (Time & Price)')}</div>
                  <div className="text-[#F1F5F9] font-semibold mt-0.5">{selectedTrade.entry_price} USDT</div>
                  <div className="text-[10px] text-[#94A3B8]">
                    {String(selectedTrade.entry_time).slice(0, 16).replace('T', ' ')}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#111827] border border-white/[0.05]">
                  <div className="text-[10px] text-[#64748B]">{tr(lang, 'Sortie (Date & Prix)', 'Exit (Time & Price)')}</div>
                  <div className="text-[#F1F5F9] font-semibold mt-0.5">{selectedTrade.exit_price} USDT</div>
                  <div className="text-[10px] text-[#94A3B8]">
                    {String(selectedTrade.exit_time).slice(0, 16).replace('T', ' ')}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#111827] border border-white/[0.05]">
                  <div className="text-[10px] text-[#64748B]">{tr(lang, 'Stop Loss / Take Profit', 'Stop Loss / Take Profit')}</div>
                  <div className="mt-0.5">
                    <span className="text-[#FB7185]">{selectedTrade.sl_initial}</span> /{' '}
                    <span className="text-[#10B981]">{selectedTrade.tp_initial}</span>
                  </div>
                  <div className="text-[10px] text-[#94A3B8]">
                    {tr(lang, 'Durée :', 'Held:')} {selectedTrade.bars_held} {tr(lang, 'bougies', 'candles')}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#111827] border border-white/[0.05]">
                  <div className="text-[10px] text-[#64748B]">{tr(lang, 'Taille & Marge', 'Size & Margin')}</div>
                  <div className="text-[#F1F5F9] mt-0.5">
                    {selectedTrade.qty} ({selectedTrade.notional_usdt}$)
                  </div>
                  <div className="text-[10px] text-[#94A3B8]">
                    {tr(lang, 'Frais :', 'Fees:')} {selectedTrade.fees_usdt} USDT
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#111827] border border-white/[0.05]">
                  <div className="text-[10px] text-[#64748B]">Excursion MFE / MAE</div>
                  <div className="mt-0.5">
                    <span className="text-[#10B981]">+{selectedTrade.mfe_pct}%</span> /{' '}
                    <span className="text-[#F43F5E]">{selectedTrade.mae_pct}%</span>
                  </div>
                  <div className="text-[10px] text-[#94A3B8]">
                    {selectedTrade.partial_taken
                      ? tr(lang, 'TP partiel encaissé', 'Partial TP taken')
                      : tr(lang, 'Sortie complète', 'Full exit')}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#111827] border border-white/[0.05]">
                  <div className="text-[10px] text-[#64748B]">{tr(lang, 'PnL Net & Multiple R', 'Net PnL & R Multiple')}</div>
                  <div
                    className={`font-bold mt-0.5 ${
                      selectedTrade.pnl_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                    }`}
                  >
                    {selectedTrade.pnl_usdt >= 0 ? '+' : ''}
                    {selectedTrade.pnl_usdt} USDT ({selectedTrade.pnl_pct >= 0 ? '+' : ''}
                    {selectedTrade.pnl_pct}%)
                  </div>
                  <div
                    className={`text-[10px] font-bold ${
                      selectedTrade.r_multiple >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                    }`}
                  >
                    {selectedTrade.r_multiple >= 0 ? '+' : ''}
                    {selectedTrade.r_multiple}R
                  </div>
                </div>
              </div>

              <div className="text-xs text-[#94A3B8] flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-white/[0.06]">
                <div>
                  <strong className="text-[#F1F5F9]">
                    {tr(lang, "Confluence & Règles d'entrée :", 'Entry Confluence & Rules:')}
                  </strong>{' '}
                  {selectedTrade.entry_reasons?.join(' • ') || tr(lang, 'Signal validé', 'Validated signal')}
                </div>
              </div>
            </>
          ) : (
            clickedCandle?.marker && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs font-mono-tabular">
                <div className="p-2.5 rounded bg-[#111827]">
                  <div className="text-[10px] text-[#64748B]">{tr(lang, 'Prix Exécution', 'Execution Price')}</div>
                  <div className="text-[#F1F5F9] font-semibold">{clickedCandle.marker.price} USDT</div>
                </div>
                {clickedCandle.marker.sl && (
                  <div className="p-2.5 rounded bg-[#111827]">
                    <div className="text-[10px] text-[#64748B]">SL / TP</div>
                    <div className="text-[#F1F5F9]">
                      {clickedCandle.marker.sl} / {clickedCandle.marker.tp}
                    </div>
                  </div>
                )}
                {clickedCandle.marker.pnl_usdt !== undefined && (
                  <div className="p-2.5 rounded bg-[#111827]">
                    <div className="text-[10px] text-[#64748B]">PnL Net</div>
                    <div className={clickedCandle.marker.pnl_usdt >= 0 ? 'text-[#10B981] font-bold' : 'text-[#F43F5E] font-bold'}>
                      {clickedCandle.marker.pnl_usdt >= 0 ? '+' : ''}
                      {clickedCandle.marker.pnl_usdt} USDT
                    </div>
                  </div>
                )}
                <div className="p-2.5 rounded bg-[#111827]">
                  <div className="text-[10px] text-[#64748B]">{tr(lang, 'Détail', 'Detail')}</div>
                  <div className="text-[#F1F5F9]">
                    {clickedCandle.marker.exit_reason || clickedCandle.marker.reason || 'Signal'}
                  </div>
                </div>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
};

const DEFAULT_PARAMS: StrategyLabParams = {
  initial_capital: 10000,
  position_sizing_mode: 'risk_pct',
  risk_per_trade_pct: 1.0,
  fixed_position_usdt: 1000,
  capital_allocation_pct: 10,
  leverage: 2,
  fee_bps: 4.0,
  slippage_bps: 2.0,
  allow_long: true,
  allow_short: true,
  max_open_positions: 1,
  cooldown_candles: 2,
  max_trades_per_day: 8,
  max_consecutive_losses: 4,
  ema_fast: 20,
  ema_slow: 50,
  ema_trend: 200,
  rsi_period: 14,
  rsi_oversold: 32,
  rsi_overbought: 68,
  adx_period: 14,
  adx_min: 20,
  atr_period: 14,
  min_atr_pct: 0.12,
  volume_ma_period: 20,
  min_volume_ratio: 0.65,
  min_teddy_score: 58,
  require_ema_alignment: true,
  require_macd_confirmation: true,
  require_trend_filter_ema200: false,
  block_against_strong_trend: true,
  sl_mode: 'atr',
  sl_atr_mult: 1.5,
  sl_fixed_pct: 1.2,
  tp_mode: 'rr',
  min_rr_ratio: 1.8,
  tp_atr_mult: 2.8,
  tp_fixed_pct: 2.4,
  partial_tp_enabled: true,
  partial_tp_rr: 1.2,
  partial_tp_close_pct: 50,
  breakeven_enabled: true,
  breakeven_trigger_rr: 1.0,
  trailing_stop_enabled: true,
  trailing_activation_rr: 1.3,
  trailing_distance_atr: 1.1,
  exit_on_opposite_signal: true,
  max_bars_in_trade: 48,
};

const REJECTION_LABELS: Record<string, string> = {
  score_too_low: 'Teddy Score inférieur au seuil',
  low_volatility_atr: 'Volatilité ATR insuffisante',
  weak_adx_regime: 'Régime ADX trop faible (Range)',
  low_volume: 'Volume relatif insuffisant',
  ema_misaligned: 'EMAs rapide/lente non alignées',
  macd_divergence: 'Momentum MACD contraire',
  against_ema200_trend: 'Contre-tendance EMA longue',
  counter_strong_trend: 'Contre tendance forte (ADX >= 30)',
  insufficient_rr: 'Ratio Risque/Rendement insuffisant',
  cooldown_or_limits: 'Cooldown ou limite journalière',
  direction_disabled: 'Direction Long/Short désactivée',
};

const REJECTION_LABELS_EN: Record<string, string> = {
  score_too_low: 'Teddy Score below threshold',
  low_volatility_atr: 'Insufficient ATR volatility',
  weak_adx_regime: 'Weak ADX regime (Range)',
  low_volume: 'Insufficient relative volume',
  ema_misaligned: 'Fast/Slow EMAs misaligned',
  macd_divergence: 'Contrary MACD momentum',
  against_ema200_trend: 'Counter long-term EMA trend',
  counter_strong_trend: 'Counter strong trend (ADX >= 30)',
  insufficient_rr: 'Insufficient Risk/Reward ratio',
  cooldown_or_limits: 'Cooldown or daily trade limit',
  direction_disabled: 'Long/Short direction disabled',
};

interface StrategyLabViewProps {
  onShowToast: (type: 'success' | 'error' | 'info', text: string) => void;
  lang?: AppLang;
}

export const StrategyLabView: React.FC<StrategyLabViewProps> = ({ onShowToast, lang = 'fr' }) => {
  // Available markets, presets & saved runs
  const [symbols, setSymbols] = useState<string[]>([
    'BTCUSDT',
    'ETHUSDT',
    'XAUUSD',
    'SOLUSDT',
    'BNBUSDT',
    'XRPUSDT',
    'DOGEUSDT',
    'ADAUSDT',
    'AVAXUSDT',
    'LINKUSDT',
  ]);
  const [timeframes, setTimeframes] = useState<string[]>(['1m', '5m', '15m', '1h', '4h', '1d']);
  const [presets, setPresets] = useState<StrategyLabPreset[]>([]);
  const [savedRuns, setSavedRuns] = useState<StrategyLabRun[]>([]);

  // Active Experiment Configuration
  const [symbol, setSymbol] = useState<string>('BTCUSDT');
  const [timeframe, setTimeframe] = useState<string>('15m');
  const [tradingStyle, setTradingStyle] = useState<string>('day');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [maxCandles, setMaxCandles] = useState<number>(800);
  const [params, setParams] = useState<StrategyLabParams>(DEFAULT_PARAMS);
  const [baselineParams, setBaselineParams] = useState<StrategyLabParams>(DEFAULT_PARAMS);

  // Active Backtest Run & Comparison State
  const [activeRun, setActiveRun] = useState<StrategyLabRun | null>(null);
  const [compareRun, setCompareRun] = useState<StrategyLabRun | null>(null);
  const [runningBacktest, setRunningBacktest] = useState<boolean>(false);
  const [runningCompare, setRunningCompare] = useState<boolean>(false);

  // Sub-views inside Strategy Lab
  const [labSection, setLabSection] = useState<
    'overview' | 'chart' | 'trades' | 'diagnostics' | 'compare' | 'sweep' | 'history'
  >('overview');
  const [paramCategory, setParamCategory] = useState<
    'capital' | 'indicators' | 'confluence' | 'exits'
  >('confluence');

  // Trade Inspector & Filtering
  const [tradeSideFilter, setTradeSideFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');
  const [tradeOutcomeFilter, setTradeOutcomeFilter] = useState<'ALL' | 'WIN' | 'LOSS'>('ALL');
  const [tradeReasonFilter, setTradeReasonFilter] = useState<string>('ALL');
  const [selectedTrade, setSelectedTrade] = useState<StrategyLabTrade | null>(null);

  // Save Preset / Run Modal State
  const [presetNameInput, setPresetNameInput] = useState<string>('');
  const [presetDescInput, setPresetDescInput] = useState<string>('');
  const [presetTagsInput, setPresetTagsInput] = useState<string>('officiel,recherche');
  const [showSavePresetModal, setShowSavePresetModal] = useState<boolean>(false);

  // Parameter Sweep (Sensitivity Grid) State
  const [sweepParamName, setSweepParamName] = useState<string>('min_teddy_score');
  const [sweepValuesInput, setSweepValuesInput] = useState<string>('48, 54, 58, 62, 68, 74');
  const [runningSweep, setRunningSweep] = useState<boolean>(false);
  const [sweepResult, setSweepResult] = useState<any | null>(null);

  // =========================================================================
  // NEW CAPABILITIES: VISUAL CONFIG / RAW CONFIG / MODEL SELECTOR / AI PROMPT
  // =========================================================================
  const [labSchema, setLabSchema] = useState<StrategyLabSchema>({
    models: DEFAULT_LAB_MODELS,
    parameters: DEFAULT_LAB_PARAM_SPECS,
    default_selected_models: ['confluence', 'indicators', 'exits', 'capital'],
  });
  const [configEditorMode, setConfigEditorMode] = useState<'visual' | 'raw' | 'ai_prompt'>('visual');
  const [selectedModels, setSelectedModels] = useState<
    ('confluence' | 'indicators' | 'exits' | 'capital')[]
  >(['confluence', 'indicators', 'exits', 'capital']);
  const [rawConfigText, setRawConfigText] = useState<string>(() =>
    formatRawConfigText(DEFAULT_PARAMS, ['confluence', 'indicators', 'exits', 'capital'])
  );
  const [rawConfigValid, setRawConfigValid] = useState<boolean | null>(true);
  const [rawConfigErrors, setRawConfigErrors] = useState<string[]>([]);
  const [rawConfigDiff, setRawConfigDiff] = useState<StrategyLabParamDiff[]>([]);
  const [validatingRawConfig, setValidatingRawConfig] = useState<boolean>(false);
  const [generatedAiPrompt, setGeneratedAiPrompt] = useState<string>('');
  const [generatingAiPrompt, setGeneratingAiPrompt] = useState<boolean>(false);

  const editableParamsCount = useMemo(() => {
    const specs = labSchema.parameters || DEFAULT_LAB_PARAM_SPECS;
    return (Object.keys(specs) as (keyof StrategyLabParams)[]).filter((k) =>
      selectedModels.includes(specs[k].model)
    ).length;
  }, [labSchema.parameters, selectedModels]);

  // Compute live diff between current params and baselineParams for Visual & Raw preview
  const liveParamsDiff = useMemo<StrategyLabParamDiff[]>(() => {
    const specs = labSchema.parameters || DEFAULT_LAB_PARAM_SPECS;
    const changes: StrategyLabParamDiff[] = [];
    for (const k of Object.keys(specs) as (keyof StrategyLabParams)[]) {
      const oldV = baselineParams[k];
      const newV = params[k];
      const isDiff =
        typeof oldV === 'number' && typeof newV === 'number'
          ? Math.abs(oldV - newV) > 1e-7
          : oldV !== newV;
      if (isDiff) {
        changes.push({
          param: k,
          model: specs[k].model,
          old_value: oldV,
          new_value: newV,
          unit: specs[k].unit || '',
          label_fr: specs[k].label_fr,
          label_en: specs[k].label_en,
        });
      }
    }
    return changes;
  }, [params, baselineParams, labSchema.parameters]);

  const toggleModelSelection = (modelId: 'confluence' | 'indicators' | 'exits' | 'capital') => {
    setSelectedModels((prev) => {
      const exists = prev.includes(modelId);
      const next = exists ? prev.filter((m) => m !== modelId) : [...prev, modelId];
      // Reset any unsaved edits on unselected model back to baselineParams to guarantee preservation
      if (exists) {
        const specs = labSchema.parameters || DEFAULT_LAB_PARAM_SPECS;
        setParams((curr) => {
          const copy = { ...curr };
          for (const k of Object.keys(specs) as (keyof StrategyLabParams)[]) {
            if (specs[k].model === modelId) {
              (copy as any)[k] = baselineParams[k];
            }
          }
          return copy;
        });
      }
      // Keep Raw Config synchronized with the newly selected models
      const nextRaw = formatRawConfigText(
        params,
        next,
        labSchema.models || DEFAULT_LAB_MODELS,
        labSchema.parameters || DEFAULT_LAB_PARAM_SPECS
      );
      setRawConfigText(nextRaw);
      setRawConfigErrors([]);
      setRawConfigValid(true);
      return next;
    });
  };

  const handleValidateRawConfig = useCallback(
    async (textToValidate?: string, silent = false): Promise<{ ok: boolean; params?: StrategyLabParams; changes?: StrategyLabParamDiff[]; errors?: string[] }> => {
      const targetText = textToValidate !== undefined ? textToValidate : rawConfigText;
      setValidatingRawConfig(true);
      try {
        const res = await apiFetch('/api/admin/strategy-lab/raw-config/validate', {
          method: 'POST',
          body: JSON.stringify({
            raw_config: targetText,
            reference_params: baselineParams,
            selected_models: selectedModels,
            trading_style: tradingStyle,
          }),
        });
        setRawConfigValid(true);
        setRawConfigErrors([]);
        setRawConfigDiff(res.changes || []);
        if (res.params) {
          setParams({ ...DEFAULT_PARAMS, ...res.params });
        }
        if (!silent) {
          onShowToast(
            'success',
            lang === 'en'
              ? `Raw Config validated (${res.changes_count || 0} parameter change(s)).`
              : `Raw Config validée (${res.changes_count || 0} paramètre(s) modifié(s)).`
          );
        }
        return { ok: true, params: res.params, changes: res.changes || [] };
      } catch (err: any) {
        setRawConfigValid(false);
        const errMsg = err.message || 'Invalid Raw Config';
        setRawConfigErrors([errMsg]);
        if (!silent) {
          onShowToast('error', errMsg);
        }
        return { ok: false, errors: [errMsg] };
      } finally {
        setValidatingRawConfig(false);
      }
    },
    [rawConfigText, baselineParams, selectedModels, tradingStyle, onShowToast, lang]
  );

  const handleGenerateAiPrompt = useCallback(async () => {
    setGeneratingAiPrompt(true);
    try {
      const res = await apiFetch('/api/admin/strategy-lab/ai-prompt', {
        method: 'POST',
        body: JSON.stringify({
          symbol,
          timeframe,
          trading_style: tradingStyle,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          max_candles: maxCandles,
          params,
          selected_models: selectedModels,
          run_id: activeRun?.id,
          active_run: activeRun
            ? {
                start_date: activeRun.start_date,
                end_date: activeRun.end_date,
                candles_count: activeRun.candles_count,
                data_source: activeRun.data_source,
                metrics: activeRun.metrics,
                signals_summary: activeRun.signals_summary,
              }
            : undefined,
        }),
      });
      if (res.prompt) {
        setGeneratedAiPrompt(res.prompt);
      }
    } catch (err: any) {
      onShowToast(
        'error',
        err.message || (lang === 'en' ? 'Failed to generate AI Prompt.' : 'Impossible de générer le prompt IA.')
      );
    } finally {
      setGeneratingAiPrompt(false);
    }
  }, [symbol, timeframe, tradingStyle, startDate, endDate, maxCandles, params, selectedModels, activeRun, onShowToast, lang]);

  // Automatically refresh AI Prompt when opening the AI Prompt tab or when parameters/run change
  useEffect(() => {
    if (configEditorMode === 'ai_prompt') {
      handleGenerateAiPrompt();
    }
  }, [configEditorMode, handleGenerateAiPrompt]);

  const loadLabOverview = useCallback(async () => {
    try {
      const res = await apiFetch('/api/admin/strategy-lab/overview');
      if (res.symbols) setSymbols(res.symbols);
      if (res.timeframes) setTimeframes(res.timeframes);
      if (res.schema) {
        setLabSchema(res.schema);
      }
      if (res.presets) {
        setPresets(res.presets);
        if (res.presets.length > 0 && !activeRun) {
          const firstPreset = res.presets[0];
          const merged = { ...DEFAULT_PARAMS, ...firstPreset.params };
          setParams(merged);
          setBaselineParams(merged);
          setRawConfigText(
            formatRawConfigText(
              merged,
              selectedModels,
              res.schema?.models || DEFAULT_LAB_MODELS,
              res.schema?.parameters || DEFAULT_LAB_PARAM_SPECS
            )
          );
        }
      }
      if (res.runs) setSavedRuns(res.runs);
    } catch (err: any) {
      onShowToast(
        'error',
        err.message || (lang === 'en' ? 'Error loading Strategy Lab.' : 'Erreur lors du chargement du Strategy Lab.')
      );
    }
  }, [activeRun, selectedModels, onShowToast, lang]);

  const executeBacktest = useCallback(
    async (customParams?: StrategyLabParams, isBaselineCompare = false, useRawMode = false) => {
      let targetParams = customParams || params;
      if (useRawMode && !isBaselineCompare) {
        const val = await handleValidateRawConfig(rawConfigText, true);
        if (!val.ok || !val.params) {
          onShowToast(
            'error',
            (val.errors && val.errors[0]) ||
              (lang === 'en'
                ? 'Invalid configuration: fix Raw Config errors before running backtest.'
                : 'Configuration invalide : corrigez les erreurs Raw Config avant de lancer le backtest.')
          );
          return;
        }
        targetParams = val.params;
      }

      if (isBaselineCompare) {
        setRunningCompare(true);
      } else {
        setRunningBacktest(true);
      }
      try {
        const payload: Record<string, any> = {
          symbol,
          timeframe,
          trading_style: tradingStyle,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          max_candles: maxCandles,
          params: targetParams,
          reference_params: baselineParams,
          selected_models: selectedModels,
          save_run: !isBaselineCompare,
          name: isBaselineCompare
            ? `${lang === 'en' ? 'Baseline' : 'Référence'} ${symbol} ${timeframe}`
            : `${symbol} ${timeframe} (${tradingStyle.toUpperCase()}) • Score≥${targetParams.min_teddy_score} • SL ${targetParams.sl_atr_mult}xATR`,
        };
        if (useRawMode && !isBaselineCompare) {
          payload.raw_config = rawConfigText;
        }
        const res = await apiFetch('/api/admin/strategy-lab/backtest', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        if (isBaselineCompare) {
          setCompareRun(res.run);
          onShowToast(
            'info',
            lang === 'en'
              ? 'Baseline scenario (A) computed for A/B comparison.'
              : 'Scénario de référence (A) calculé pour comparaison A/B.'
          );
        } else {
          setActiveRun(res.run);
          if (res.runs) setSavedRuns(res.runs);
          setSelectedTrade(null);
          if (res.run?.params) {
            const normalizedRunParams = { ...DEFAULT_PARAMS, ...res.run.params };
            setParams(normalizedRunParams);
            setRawConfigText(
              formatRawConfigText(
                normalizedRunParams,
                selectedModels,
                labSchema.models || DEFAULT_LAB_MODELS,
                labSchema.parameters || DEFAULT_LAB_PARAM_SPECS
              )
            );
          }
          onShowToast(
            'success',
            lang === 'en'
              ? `Simulation completed in ${res.run.execution_ms || 0} ms (${res.run.metrics.total_trades} trades over ${res.run.candles_count} candles).`
              : `Simulation terminée en ${res.run.execution_ms || 0} ms (${res.run.metrics.total_trades} trades sur ${res.run.candles_count} bougies).`
          );
        }
      } catch (err: any) {
        onShowToast('error', err.message || (lang === 'en' ? 'Backtest failed.' : 'Échec du backtest.'));
      } finally {
        setRunningBacktest(false);
        setRunningCompare(false);
      }
    },
    [
      symbol,
      timeframe,
      tradingStyle,
      startDate,
      endDate,
      maxCandles,
      params,
      baselineParams,
      selectedModels,
      rawConfigText,
      handleValidateRawConfig,
      labSchema.models,
      labSchema.parameters,
      onShowToast,
      lang,
    ]
  );

  // Run initial backtest on mount so the Lab is immediately populated with real data
  useEffect(() => {
    loadLabOverview();
    executeBacktest(DEFAULT_PARAMS, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleParamChange = <K extends keyof StrategyLabParams>(key: K, value: StrategyLabParams[K]) => {
    const specs = labSchema.parameters || DEFAULT_LAB_PARAM_SPECS;
    const paramModel = specs[key]?.model;
    if (paramModel && !selectedModels.includes(paramModel)) {
      onShowToast(
        'info',
        lang === 'en'
          ? `Model "${paramModel}" is currently locked. Check its box in the Models selector to edit "${key}".`
          : `Le modèle « ${paramModel} » est verrouillé. Cochez-le dans la sélection des modèles pour modifier « ${key} ».`
      );
      return;
    }
    setParams((prev) => {
      const next = { ...prev, [key]: value };
      setRawConfigText(
        formatRawConfigText(
          next,
          selectedModels,
          labSchema.models || DEFAULT_LAB_MODELS,
          specs
        )
      );
      setRawConfigValid(true);
      setRawConfigErrors([]);
      return next;
    });
  };

  const applyPreset = (preset: StrategyLabPreset) => {
    const merged = { ...DEFAULT_PARAMS, ...preset.params };
    setParams(merged);
    setBaselineParams(merged);
    setRawConfigText(
      formatRawConfigText(
        merged,
        selectedModels,
        labSchema.models || DEFAULT_LAB_MODELS,
        labSchema.parameters || DEFAULT_LAB_PARAM_SPECS
      )
    );
    setRawConfigErrors([]);
    setRawConfigValid(true);
    setRawConfigDiff([]);
    if (preset.timeframe) setTimeframe(preset.timeframe);
    if (preset.trading_style) setTradingStyle(preset.trading_style);
    onShowToast(
      'info',
      lang === 'en'
        ? `Preset "${preset.name}" loaded. Click Run Backtest to evaluate.`
        : `Preset « ${preset.name} » chargé. Cliquez sur Lancer le Backtest pour évaluer.`
    );
  };

  const handleSavePreset = async () => {
    if (!presetNameInput.trim()) {
      onShowToast(
        'error',
        lang === 'en' ? 'Please enter a name for the strategy.' : 'Veuillez saisir un nom pour la stratégie.'
      );
      return;
    }
    try {
      const res = await apiFetch('/api/admin/strategy-lab/preset', {
        method: 'POST',
        body: JSON.stringify({
          action: 'save',
          name: presetNameInput.trim(),
          description: presetDescInput.trim(),
          symbol,
          timeframe,
          trading_style: tradingStyle,
          params,
          tags: presetTagsInput,
          is_favorite: true,
        }),
      });
      if (res.presets) setPresets(res.presets);
      setShowSavePresetModal(false);
      setPresetNameInput('');
      setPresetDescInput('');
      onShowToast(
        'success',
        lang === 'en' ? 'Strategy saved in Bitsure Presets.' : 'Stratégie sauvegardée dans les Presets Bitsure.'
      );
    } catch (err: any) {
      onShowToast('error', err.message || (lang === 'en' ? 'Error saving preset.' : 'Erreur lors de la sauvegarde.'));
    }
  };

  const handleLoadSavedRun = async (runSummary: StrategyLabRun, asComparison = false) => {
    if (!runSummary.id) return;
    try {
      const res = await apiFetch(`/api/admin/strategy-lab/run-detail?id=${runSummary.id}`);
      if (res.run) {
        if (asComparison) {
          setCompareRun(res.run);
          setLabSection('compare');
          onShowToast(
            'info',
            lang === 'en'
              ? `Experiment #${runSummary.id} loaded as Baseline (A).`
              : `Expérience #${runSummary.id} chargée comme Référence (A).`
          );
        } else {
          setActiveRun(res.run);
          const restoredParams = { ...DEFAULT_PARAMS, ...res.run.params };
          setParams(restoredParams);
          setBaselineParams(restoredParams);
          setRawConfigText(
            formatRawConfigText(
              restoredParams,
              selectedModels,
              labSchema.models || DEFAULT_LAB_MODELS,
              labSchema.parameters || DEFAULT_LAB_PARAM_SPECS
            )
          );
          setRawConfigErrors([]);
          setRawConfigValid(true);
          setRawConfigDiff([]);
          setSymbol(res.run.symbol);
          setTimeframe(res.run.timeframe);
          setTradingStyle(res.run.trading_style);
          onShowToast(
            'success',
            lang === 'en'
              ? `Experiment #${runSummary.id} restored to workspace.`
              : `Expérience #${runSummary.id} restaurée dans l'espace de travail.`
          );
        }
      }
    } catch (err: any) {
      onShowToast(
        'error',
        err.message ||
          (lang === 'en'
            ? 'Unable to load experiment details.'
            : 'Impossible de charger les détails de cette expérience.')
      );
    }
  };

  const handleRunSweep = async () => {
    setRunningSweep(true);
    try {
      const parsedValues = sweepValuesInput
        .split(',')
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n));
      if (parsedValues.length < 2) {
        onShowToast(
          'error',
          lang === 'en'
            ? 'Provide at least 2 numeric values separated by commas.'
            : 'Indiquez au moins 2 valeurs numériques séparées par des virgules.'
        );
        setRunningSweep(false);
        return;
      }
      const res = await apiFetch('/api/admin/strategy-lab/sweep', {
        method: 'POST',
        body: JSON.stringify({
          symbol,
          timeframe,
          trading_style: tradingStyle,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          max_candles: Math.min(maxCandles, 700),
          params,
          param_name: sweepParamName,
          values: parsedValues,
        }),
      });
      setSweepResult(res.sweep);
      onShowToast(
        'success',
        lang === 'en'
          ? `Sensitivity sweep completed (${res.sweep.results.length} variants tested).`
          : `Balayage de sensibilité terminé (${res.sweep.results.length} variantes testées).`
      );
    } catch (err: any) {
      onShowToast(
        'error',
        err.message || (lang === 'en' ? 'Parameter sweep failed.' : 'Erreur lors du balayage de paramètres.')
      );
    } finally {
      setRunningSweep(false);
    }
  };

  const exportTradesCsv = () => {
    if (!activeRun?.trades || activeRun.trades.length === 0) {
      onShowToast('info', lang === 'en' ? 'No trades to export.' : 'Aucun trade à exporter.');
      return;
    }
    const headers =
      lang === 'en'
        ? [
            'ID',
            'Symbol',
            'Side',
            'Entry_UTC',
            'Exit_UTC',
            'Entry_Price',
            'Exit_Price',
            'Initial_SL',
            'Initial_TP',
            'Quantity',
            'PnL_USDT',
            'PnL_Pct',
            'R_Multiple',
            'Fees_USDT',
            'MFE_Pct',
            'MAE_Pct',
            'Teddy_Score',
            'Exit_Reason',
          ]
        : [
            'ID',
            'Symbole',
            'Direction',
            'Entree_UTC',
            'Sortie_UTC',
            'Prix_Entree',
            'Prix_Sortie',
            'SL_Initial',
            'TP_Initial',
            'Quantite',
            'PnL_USDT',
            'PnL_Pct',
            'Multiple_R',
            'Frais_USDT',
            'MFE_Pct',
            'MAE_Pct',
            'Teddy_Score',
            'Motif_Sortie',
          ];
    const rows = activeRun.trades.map((t) =>
      [
        t.id,
        t.symbol,
        t.side,
        t.entry_time,
        t.exit_time,
        t.entry_price,
        t.exit_price,
        t.sl_initial,
        t.tp_initial,
        t.qty,
        t.pnl_usdt,
        t.pnl_pct,
        t.r_multiple,
        t.fees_usdt,
        t.mfe_pct,
        t.mae_pct,
        t.teddy_score,
        t.exit_reason,
      ].join(',')
    );
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `bitsure_lab_${activeRun.symbol}_${activeRun.timeframe}_trades.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const exportReportJson = () => {
    if (!activeRun) return;
    const jsonStr = JSON.stringify(
      {
        exported_at: new Date().toISOString(),
        symbol: activeRun.symbol,
        timeframe: activeRun.timeframe,
        trading_style: activeRun.trading_style,
        data_source: activeRun.data_source,
        candles_count: activeRun.candles_count,
        params: activeRun.params,
        metrics: activeRun.metrics,
        diagnostics: activeRun.diagnostics,
        trades_count: activeRun.trades?.length || 0,
      },
      null,
      2
    );
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `bitsure_strategy_report_${activeRun.symbol}_${activeRun.timeframe}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Filtered trades for Trade Journal table
  const filteredTrades = useMemo(() => {
    const list = activeRun?.trades || [];
    return list.filter((t) => {
      if (tradeSideFilter !== 'ALL' && t.side !== tradeSideFilter) return false;
      if (tradeOutcomeFilter === 'WIN' && t.pnl_usdt <= 0) return false;
      if (tradeOutcomeFilter === 'LOSS' && t.pnl_usdt > 0) return false;
      if (tradeReasonFilter !== 'ALL' && t.exit_reason !== tradeReasonFilter) return false;
      return true;
    });
  }, [activeRun?.trades, tradeSideFilter, tradeOutcomeFilter, tradeReasonFilter]);

  // Modified parameters count vs baseline
  const modifiedParamsKeys = useMemo(() => {
    return (Object.keys(params) as (keyof StrategyLabParams)[]).filter(
      (k) => params[k] !== baselineParams[k]
    );
  }, [params, baselineParams]);

  const m = activeRun?.metrics;

  return (
    <div className="space-y-6">
      {/* =====================================================================
          TOP HEADER BAR — ADMIN-ONLY ISOLATION BADGE & QUICK ACTIONS
         ===================================================================== */}
      <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 flex flex-col xl:flex-row xl:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-[10px] font-mono-tabular font-bold uppercase bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
              <FlaskConical className="w-3.5 h-3.5" />
              {tr(lang, 'ADMINISTRATION EXCLUSIVE • STRATEGY LAB', 'EXCLUSIVE ADMIN • STRATEGY LAB')}
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-[10px] font-mono-tabular font-semibold bg-[#3B82F6]/15 text-[#60A5FA] border border-[#3B82F6]/30">
              <ShieldCheck className="w-3.5 h-3.5" />
              {tr(lang, '100% ISOLÉ DU TRADING RÉEL (ZÉRO ORDRE LIVE)', '100% ISOLATED FROM LIVE TRADING (ZERO LIVE ORDERS)')}
            </span>
            {activeRun && (
              <span className="text-[11px] font-mono-tabular text-[#64748B]">
                Source : <strong className="text-[#94A3B8]">{activeRun.data_source}</strong> ({activeRun.candles_count} {tr(lang, 'bougies', 'candles')})
              </span>
            )}
          </div>
          <h1 className="font-display text-xl sm:text-2xl font-bold text-[#F1F5F9]">
            {tr(lang, 'Laboratoire Quantitatif & Backtesting Interactif Bitsure', 'Bitsure Quantitative Lab & Interactive Backtesting')}
          </h1>
          <p className="text-xs text-[#94A3B8]">
            {tr(
              lang,
              "Testez, modifiez, comparez (A/B) et diagnostiquez les règles du moteur de signaux Bitsure sur données historiques réelles sans aucun risque d'exécution.",
              'Test, modify, compare (A/B), and diagnose Bitsure signal engine rules on real historical data with zero execution risk.'
            )}
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            type="button"
            onClick={() => setShowSavePresetModal(true)}
            className="px-3.5 py-2 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-xs font-medium text-[#F1F5F9] flex items-center gap-1.5 transition-colors"
          >
            <Save className="w-3.5 h-3.5 text-[#10B981]" />
            <span>{tr(lang, 'Sauvegarder Preset', 'Save Preset')}</span>
          </button>
          <button
            type="button"
            onClick={exportTradesCsv}
            disabled={!activeRun?.trades?.length}
            className="px-3.5 py-2 rounded-lg bg-[#1E293B] hover:bg-[#334155] disabled:opacity-40 border border-white/10 text-xs font-medium text-[#F1F5F9] flex items-center gap-1.5 transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-[#60A5FA]" />
            <span>Export CSV</span>
          </button>
          <button
            type="button"
            onClick={exportReportJson}
            disabled={!activeRun}
            className="px-3.5 py-2 rounded-lg bg-[#1E293B] hover:bg-[#334155] disabled:opacity-40 border border-white/10 text-xs font-medium text-[#F1F5F9] flex items-center gap-1.5 transition-colors"
          >
            <Copy className="w-3.5 h-3.5 text-[#F59E0B]" />
            <span>{tr(lang, 'Rapport JSON', 'JSON Report')}</span>
          </button>
          <button
            type="button"
            onClick={() => executeBacktest(params, false)}
            disabled={runningBacktest}
            className="px-5 py-2.5 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-[#090D16] font-semibold text-xs flex items-center gap-2 shadow-lg shadow-[#10B981]/10 transition-all"
          >
            <Play className={`w-4 h-4 fill-current ${runningBacktest ? 'animate-pulse' : ''}`} />
            <span>{runningBacktest ? tr(lang, 'Simulation en cours...', 'Simulating...') : tr(lang, 'Lancer le Backtest', 'Run Backtest')}</span>
          </button>
        </div>
      </div>

      {/* =====================================================================
          MARKET, TIMEFRAME, PERIOD & PRESET SELECTOR STRIP
         ===================================================================== */}
      <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3 items-end">
        <div>
          <label className="block text-[11px] font-mono-tabular uppercase text-[#64748B] mb-1">
            {tr(lang, 'Paire Crypto (Binance)', 'Crypto Pair (Binance)')}
          </label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs font-mono-tabular font-semibold text-[#F1F5F9]"
          >
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-mono-tabular uppercase text-[#64748B] mb-1">
            {tr(lang, 'Unité de Temps (Timeframe)', 'Timeframe')}
          </label>
          <div className="flex bg-[#090D16] border border-white/15 rounded-lg p-0.5">
            {timeframes.map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setTimeframe(tf)}
                className={`flex-1 py-1.5 rounded text-[11px] font-mono-tabular transition-colors ${
                  timeframe === tf
                    ? 'bg-[#10B981] text-[#090D16] font-bold'
                    : 'text-[#94A3B8] hover:text-[#F1F5F9]'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-[11px] font-mono-tabular uppercase text-[#64748B] mb-1">
            {tr(lang, 'Style de Stratégie', 'Strategy Style')}
          </label>
          <select
            value={tradingStyle}
            onChange={(e) => setTradingStyle(e.target.value)}
            className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
          >
            <option value="scalp">{tr(lang, 'Scalping Réactif', 'Reactive Scalping')}</option>
            <option value="day">{tr(lang, 'Day Trading Officiel', 'Official Day Trading')}</option>
            <option value="swing">{tr(lang, 'Swing Institutionnel', 'Institutional Swing')}</option>
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-mono-tabular uppercase text-[#64748B] mb-1">
            {tr(lang, 'Profondeur (Bougies)', 'Depth (Candles)')}
          </label>
          <select
            value={maxCandles}
            onChange={(e) => setMaxCandles(Number(e.target.value))}
            className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs font-mono-tabular text-[#F1F5F9]"
          >
            <option value={300}>{tr(lang, '300 bougies (Court terme)', '300 candles (Short term)')}</option>
            <option value={600}>{tr(lang, '600 bougies (Standard)', '600 candles (Standard)')}</option>
            <option value={1000}>{tr(lang, '1 000 bougies (Étendu)', '1,000 candles (Extended)')}</option>
            <option value={1500}>{tr(lang, '1 500 bougies (Cycle profond)', '1,500 candles (Deep cycle)')}</option>
            <option value={2000}>{tr(lang, '2 000 bougies (Stress-test)', '2,000 candles (Stress-test)')}</option>
          </select>
        </div>

        <div className="xl:col-span-2">
          <label className="block text-[11px] font-mono-tabular uppercase text-[#64748B] mb-1">
            {tr(lang, 'Charger un Preset Officiel ou Sauvegardé', 'Load Official or Saved Preset')}
          </label>
          <div className="flex gap-2">
            <select
              onChange={(e) => {
                const found = presets.find((p) => String(p.id) === e.target.value);
                if (found) applyPreset(found);
              }}
              defaultValue=""
              className="flex-1 px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
            >
              <option value="" disabled>
                {tr(lang, 'Sélectionner une configuration pré-enregistrée...', 'Select a pre-saved configuration...')}
              </option>
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.is_favorite ? '★ ' : ''}
                  {p.name} ({p.timeframe.toUpperCase()})
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => {
                setParams(baselineParams);
                setRawConfigText(
                  formatRawConfigText(
                    baselineParams,
                    selectedModels,
                    labSchema.models || DEFAULT_LAB_MODELS,
                    labSchema.parameters || DEFAULT_LAB_PARAM_SPECS
                  )
                );
                setRawConfigErrors([]);
                setRawConfigValid(true);
                setRawConfigDiff([]);
                onShowToast('info', tr(lang, 'Paramètres réinitialisés à la valeur de référence.', 'Parameters reset to baseline.'));
              }}
              title={tr(lang, 'Réinitialiser les paramètres modifiés', 'Reset modified parameters')}
              className="px-3 py-2 bg-[#1E293B] hover:bg-[#334155] border border-white/10 rounded-lg text-xs text-[#94A3B8] hover:text-[#F1F5F9] flex items-center gap-1"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              {modifiedParamsKeys.length > 0 && (
                <span className="font-mono-tabular text-[10px] text-[#F59E0B]">
                  ({modifiedParamsKeys.length})
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* =====================================================================
          MAIN WORKSPACE GRID: LEFT STRATEGY EDITOR (4 COLS) + RIGHT ANALYTICS (8 COLS)
         ===================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: INTERACTIVE STRATEGY PARAMETER EDITOR (VISUAL / RAW / AI PROMPT) */}
        <div className="lg:col-span-4 bg-[#111827] border border-white/[0.08] rounded-xl overflow-hidden">
          <div className="p-4 border-b border-white/[0.07] flex items-center justify-between bg-[#0B101B]">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-[#10B981]" />
              <h2 className="font-display text-sm font-semibold text-[#F1F5F9]">
                {tr(lang, 'Éditeur de Règles & Paramètres', 'Rules & Parameters Editor')}
              </h2>
            </div>
            {liveParamsDiff.length > 0 ? (
              <span className="px-2 py-0.5 rounded text-[10px] font-mono-tabular bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30">
                {liveParamsDiff.length} {tr(lang, 'modifié(s)', 'modified')}
              </span>
            ) : (
              <span className="text-[10px] font-mono-tabular text-[#64748B]">
                {tr(lang, 'Référence active', 'Baseline active')}
              </span>
            )}
          </div>

          {/* =================================================================
              MODE SWITCHER: VISUAL CONFIG / RAW CONFIG / AI PROMPT
             ================================================================= */}
          <div className="grid grid-cols-3 border-b border-white/[0.07] bg-[#090D16] p-1 gap-1 text-xs font-medium">
            {[
              { id: 'visual', label: 'Visual Config', icon: Sliders },
              { id: 'raw', label: 'Raw Config', icon: Copy },
              { id: 'ai_prompt', label: 'AI Prompt', icon: Sparkles },
            ].map((modeTab) => {
              const MIcon = modeTab.icon;
              const isAct = configEditorMode === modeTab.id;
              return (
                <button
                  key={modeTab.id}
                  type="button"
                  onClick={() => {
                    setConfigEditorMode(modeTab.id as any);
                    if (modeTab.id === 'raw') {
                      setRawConfigText(
                        formatRawConfigText(
                          params,
                          selectedModels,
                          labSchema.models || DEFAULT_LAB_MODELS,
                          labSchema.parameters || DEFAULT_LAB_PARAM_SPECS
                        )
                      );
                    }
                  }}
                  className={`py-2 px-2 rounded-lg flex items-center justify-center gap-1.5 transition-colors ${
                    isAct
                      ? 'bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 font-semibold'
                      : 'text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.04]'
                  }`}
                >
                  <MIcon className="w-3.5 h-3.5" />
                  <span>{modeTab.label}</span>
                </button>
              );
            })}
          </div>

          {/* =================================================================
              MODELS / COMPONENTS SELECTOR (PARTIAL MODEL MODIFICATION)
             ================================================================= */}
          <div className="p-3.5 border-b border-white/[0.07] bg-[#0B101B]/70 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono-tabular uppercase tracking-wider text-[#94A3B8] font-semibold">
                {tr(lang, 'Modèles / Composants Ciblés', 'Selected Strategy Models')}
              </span>
              <span className="px-2 py-0.5 rounded bg-[#10B981]/10 border border-[#10B981]/25 text-[10px] font-mono-tabular text-[#10B981] font-semibold">
                {selectedModels.length} {tr(lang, 'modèle(s) sélectionné(s)', 'models selected')} • {editableParamsCount}{' '}
                {tr(lang, 'paramètres éditables', 'parameters editable')}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              {(labSchema.models || DEFAULT_LAB_MODELS).map((mMeta) => {
                const checked = selectedModels.includes(mMeta.id);
                const modelParamCount = (
                  Object.keys(labSchema.parameters || DEFAULT_LAB_PARAM_SPECS) as (keyof StrategyLabParams)[]
                ).filter((k) => (labSchema.parameters || DEFAULT_LAB_PARAM_SPECS)[k]?.model === mMeta.id).length;
                return (
                  <label
                    key={mMeta.id}
                    className={`flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg border text-[11px] cursor-pointer transition-colors ${
                      checked
                        ? 'bg-[#10B981]/10 border-[#10B981]/35 text-[#F1F5F9]'
                        : 'bg-[#090D16]/70 border-white/[0.06] text-[#64748B] hover:text-[#94A3B8]'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleModelSelection(mMeta.id)}
                        className="accent-[#10B981] shrink-0"
                      />
                      <span className="truncate font-medium">
                        {mMeta.id === 'confluence'
                          ? 'Signal & Confluence'
                          : mMeta.id === 'indicators'
                          ? 'Indicators & RSI'
                          : mMeta.id === 'exits'
                          ? 'Exit & SL/TP Model'
                          : 'Capital & Execution'}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono-tabular text-[#64748B] shrink-0">
                      {modelParamCount}p
                    </span>
                  </label>
                );
              })}
            </div>
            <div className="text-[10px] text-[#64748B] flex items-center justify-between">
              <span>
                {tr(
                  lang,
                  'Les modèles non cochés restent verrouillés sur la configuration de référence.',
                  'Unchecked models remain locked to the reference configuration.'
                )}
              </span>
              <button
                type="button"
                onClick={() => {
                  const allIds: ('confluence' | 'indicators' | 'exits' | 'capital')[] = [
                    'confluence',
                    'indicators',
                    'exits',
                    'capital',
                  ];
                  setSelectedModels(allIds);
                  setRawConfigText(
                    formatRawConfigText(
                      params,
                      allIds,
                      labSchema.models || DEFAULT_LAB_MODELS,
                      labSchema.parameters || DEFAULT_LAB_PARAM_SPECS
                    )
                  );
                }}
                className="text-[#60A5FA] hover:underline font-mono-tabular shrink-0 ml-2"
              >
                {tr(lang, 'Tout cocher', 'Select all')}
              </button>
            </div>
          </div>

          {/* =================================================================
              MODE 1: VISUAL CONFIG
             ================================================================= */}
          {configEditorMode === 'visual' && (
            <>
              {/* Parameter Category Tabs */}
              <div className="grid grid-cols-4 border-b border-white/[0.07] bg-[#090D16] text-[11px] font-medium">
                {[
                  { id: 'confluence', label: tr(lang, 'Score & Filtres', 'Score & Filters') },
                  { id: 'exits', label: 'SL / TP / Trail' },
                  { id: 'indicators', label: tr(lang, 'Indicateurs', 'Indicators') },
                  { id: 'capital', label: tr(lang, 'Capital & Frais', 'Capital & Fees') },
                ].map((tab) => {
                  const isModelLocked = !selectedModels.includes(tab.id as any);
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setParamCategory(tab.id as any)}
                      className={`py-2.5 px-2 text-center border-b-2 transition-colors ${
                        paramCategory === tab.id
                          ? 'border-[#10B981] text-[#10B981] bg-[#10B981]/5 font-semibold'
                          : 'border-transparent text-[#94A3B8] hover:text-[#F1F5F9]'
                      } ${isModelLocked ? 'opacity-60' : ''}`}
                    >
                      {tab.label} {isModelLocked ? '🔒' : ''}
                    </button>
                  );
                })}
              </div>

              <div className="p-4 space-y-4 max-h-[680px] overflow-y-auto">
                {/* Lock notice when current tab's model is unselected */}
                {!selectedModels.includes(paramCategory) && (
                  <div className="p-3 rounded-lg bg-[#F59E0B]/10 border border-[#F59E0B]/30 text-xs text-[#FBBF24] flex items-center justify-between gap-2">
                    <span>
                      {tr(
                        lang,
                        'Ce modèle est non sélectionné : ses paramètres sont préservés tels quels depuis la référence.',
                        'This model is unselected: its parameters are preserved unchanged from baseline.'
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={() => toggleModelSelection(paramCategory)}
                      className="px-2.5 py-1 rounded bg-[#F59E0B]/20 hover:bg-[#F59E0B]/30 text-[#FDE68A] font-mono-tabular text-[11px] shrink-0"
                    >
                      {tr(lang, 'Déverrouiller', 'Unlock')}
                    </button>
                  </div>
                )}

                <fieldset
                  disabled={!selectedModels.includes(paramCategory)}
                  className={!selectedModels.includes(paramCategory) ? 'opacity-50 pointer-events-none space-y-4' : 'space-y-4'}
                >
                  {/* CATEGORY 1: CONFLUENCE, TEDDY SCORE & FILTERS */}
                  {paramCategory === 'confluence' && (
                    <div className="space-y-4">
                      <div>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-[#94A3B8]">
                            {tr(lang, "Score Teddy Minimum d'Entrée", 'Minimum Entry Teddy Score')}{' '}
                            <span className="text-[10px] font-mono-tabular text-[#64748B]">(min_teddy_score • int [20..95])</span>
                          </span>
                          <span className="font-mono-tabular font-bold text-[#10B981]">
                            {params.min_teddy_score} / 100
                          </span>
                        </div>
                        <input
                          type="range"
                          min={20}
                          max={95}
                          step={1}
                          value={params.min_teddy_score}
                          onChange={(e) => handleParamChange('min_teddy_score', Number(e.target.value))}
                          className="w-full accent-[#10B981]"
                        />
                        <div className="flex justify-between text-[10px] font-mono-tabular text-[#64748B]">
                          <span>{tr(lang, '20 (Min)', '20 (Min)')}</span>
                          <span>{tr(lang, '58 (Officiel)', '58 (Official)')}</span>
                          <span>{tr(lang, '95 (Max)', '95 (Max)')}</span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-2.5">
                        <label className="flex items-center justify-between p-2.5 rounded-lg bg-[#090D16] border border-white/10 text-xs cursor-pointer">
                          <div>
                            <div className="text-[#F1F5F9]">{tr(lang, 'Autoriser LONG', 'Allow LONG')}</div>
                            <div className="text-[10px] font-mono-tabular text-[#64748B]">allow_long (bool)</div>
                          </div>
                          <input
                            type="checkbox"
                            checked={params.allow_long}
                            onChange={(e) => handleParamChange('allow_long', e.target.checked)}
                            className="accent-[#10B981]"
                          />
                        </label>
                        <label className="flex items-center justify-between p-2.5 rounded-lg bg-[#090D16] border border-white/10 text-xs cursor-pointer">
                          <div>
                            <div className="text-[#F1F5F9]">{tr(lang, 'Autoriser SHORT', 'Allow SHORT')}</div>
                            <div className="text-[10px] font-mono-tabular text-[#64748B]">allow_short (bool)</div>
                          </div>
                          <input
                            type="checkbox"
                            checked={params.allow_short}
                            onChange={(e) => handleParamChange('allow_short', e.target.checked)}
                            className="accent-[#10B981]"
                          />
                        </label>
                      </div>

                      <div className="space-y-2">
                        {[
                          {
                            key: 'require_ema_alignment' as const,
                            label: tr(lang, 'Exiger alignement EMA rapide / lente', 'Require Fast / Slow EMA alignment'),
                            desc: tr(lang, 'Bloque les achats sous EMA rapide et ventes au-dessus', 'Blocks buys below fast EMA and sells above'),
                          },
                          {
                            key: 'require_macd_confirmation' as const,
                            label: tr(lang, 'Exiger confirmation impulsion MACD', 'Require MACD momentum confirmation'),
                            desc: tr(lang, 'Filtre les entrées à contre-courant de l’histogramme MACD', 'Filters entries against the MACD histogram'),
                          },
                          {
                            key: 'require_trend_filter_ema200' as const,
                            label: tr(lang, `Filtre directionnel strict EMA ${params.ema_trend}`, `Strict directional EMA ${params.ema_trend} filter`),
                            desc: tr(lang, 'LONG uniquement au-dessus de EMA tendance, SHORT en-dessous', 'LONG only above trend EMA, SHORT only below'),
                          },
                          {
                            key: 'block_against_strong_trend' as const,
                            label: tr(lang, 'Protection anti contre-tendance forte (ADX ≥ 30)', 'Strong counter-trend protection (ADX ≥ 30)'),
                            desc: tr(lang, 'Interdit de shorter un rallye puissant ou d’acheter un krach', 'Prevents shorting strong rallies or buying sharp crashes'),
                          },
                        ].map((item) => (
                          <label
                            key={item.key}
                            className="flex items-start justify-between gap-3 p-2.5 rounded-lg bg-[#090D16] border border-white/[0.07] hover:border-white/15 cursor-pointer transition-colors"
                          >
                            <div>
                              <div className="text-xs font-medium text-[#F1F5F9]">{item.label}</div>
                              <div className="text-[10px] font-mono-tabular text-[#64748B]">{item.key} (bool)</div>
                              <div className="text-[11px] text-[#64748B]">{item.desc}</div>
                            </div>
                            <input
                              type="checkbox"
                              checked={Boolean(params[item.key])}
                              onChange={(e) => handleParamChange(item.key, e.target.checked)}
                              className="mt-1 accent-[#10B981]"
                            />
                          </label>
                        ))}
                      </div>

                      <div className="grid grid-cols-2 gap-3 pt-1">
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Seuil ADX Min (Tendance)', 'Min ADX Threshold (Trend)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">adx_min • float [5..60] pts</span>
                          </label>
                          <input
                            type="number"
                            step="1"
                            min={5}
                            max={60}
                            value={params.adx_min}
                            onChange={(e) => handleParamChange('adx_min', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Volatilité ATR Min (%)', 'Min ATR Volatility (%)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">min_atr_pct • float [0..5] %</span>
                          </label>
                          <input
                            type="number"
                            step="0.02"
                            min={0}
                            max={5}
                            value={params.min_atr_pct}
                            onChange={(e) => handleParamChange('min_atr_pct', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Ratio Volume Min (vs MA)', 'Min Volume Ratio (vs MA)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">min_volume_ratio • float [0..5] x</span>
                          </label>
                          <input
                            type="number"
                            step="0.05"
                            min={0}
                            max={5}
                            value={params.min_volume_ratio}
                            onChange={(e) => handleParamChange('min_volume_ratio', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Cooldown (Bougies)', 'Cooldown (Candles)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">cooldown_candles • int [0..100]</span>
                          </label>
                          <input
                            type="number"
                            step="1"
                            min={0}
                            max={100}
                            value={params.cooldown_candles}
                            onChange={(e) => handleParamChange('cooldown_candles', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* CATEGORY 2: STOP LOSS, TAKE PROFIT, BREAK-EVEN & TRAILING */}
                  {paramCategory === 'exits' && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Mode Stop Loss', 'Stop Loss Mode')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">sl_mode • enum [atr, fixed_pct]</span>
                          </label>
                          <select
                            value={params.sl_mode}
                            onChange={(e) => handleParamChange('sl_mode', e.target.value as any)}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs text-[#F1F5F9]"
                          >
                            <option value="atr">{tr(lang, 'Dynamique (Multiple ATR)', 'Dynamic (ATR Multiple)')}</option>
                            <option value="fixed_pct">{tr(lang, 'Pourcentage Fixe (%)', 'Fixed Percentage (%)')}</option>
                          </select>
                        </div>
                        {params.sl_mode === 'atr' ? (
                          <div>
                            <label className="block text-[11px] text-[#94A3B8] mb-1">
                              {tr(lang, 'Multiplicateur SL (ATR)', 'SL Multiplier (ATR)')}
                              <span className="block text-[10px] font-mono-tabular text-[#64748B]">sl_atr_mult • float [0.3..10] xATR</span>
                            </label>
                            <input
                              type="number"
                              step="0.1"
                              min={0.3}
                              max={10}
                              value={params.sl_atr_mult}
                              onChange={(e) => handleParamChange('sl_atr_mult', Number(e.target.value))}
                              className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                            />
                          </div>
                        ) : (
                          <div>
                            <label className="block text-[11px] text-[#94A3B8] mb-1">
                              {tr(lang, 'Distance SL Fixe (%)', 'Fixed SL Distance (%)')}
                              <span className="block text-[10px] font-mono-tabular text-[#64748B]">sl_fixed_pct • float [0.1..25] %</span>
                            </label>
                            <input
                              type="number"
                              step="0.1"
                              min={0.1}
                              max={25}
                              value={params.sl_fixed_pct}
                              onChange={(e) => handleParamChange('sl_fixed_pct', Number(e.target.value))}
                              className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                            />
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Mode Take Profit', 'Take Profit Mode')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">tp_mode • enum [rr, atr, fixed_pct]</span>
                          </label>
                          <select
                            value={params.tp_mode}
                            onChange={(e) => handleParamChange('tp_mode', e.target.value as any)}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs text-[#F1F5F9]"
                          >
                            <option value="rr">{tr(lang, 'Multiple du Risque (R:R)', 'Risk Multiple (R:R)')}</option>
                            <option value="atr">{tr(lang, 'Multiple ATR', 'ATR Multiple')}</option>
                            <option value="fixed_pct">{tr(lang, 'Pourcentage Fixe (%)', 'Fixed Percentage (%)')}</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Ratio R:R Minimum Cible', 'Minimum Target R:R Ratio')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">min_rr_ratio • float [0.5..10] R</span>
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            min={0.5}
                            max={10}
                            value={params.min_rr_ratio}
                            onChange={(e) => handleParamChange('min_rr_ratio', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                      </div>

                      {params.tp_mode === 'atr' && (
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Multiplicateur Take Profit (ATR)', 'Take Profit ATR Multiplier')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">tp_atr_mult • float [0.5..20] xATR</span>
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            min={0.5}
                            max={20}
                            value={params.tp_atr_mult}
                            onChange={(e) => handleParamChange('tp_atr_mult', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                      )}

                      {params.tp_mode === 'fixed_pct' && (
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Distance Take Profit Fixe (%)', 'Fixed Take Profit Distance (%)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">tp_fixed_pct • float [0.2..50] %</span>
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            min={0.2}
                            max={50}
                            value={params.tp_fixed_pct}
                            onChange={(e) => handleParamChange('tp_fixed_pct', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                          />
                        </div>
                      )}

                      {/* Partial TP */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.07] space-y-2.5">
                        <label className="flex items-center justify-between text-xs font-medium text-[#F1F5F9] cursor-pointer">
                          <div>
                            <span>{tr(lang, 'Take Profit Partiel (TP1 Automatique)', 'Partial Take Profit (Auto TP1)')}</span>
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">partial_tp_enabled (bool)</span>
                          </div>
                          <input
                            type="checkbox"
                            checked={params.partial_tp_enabled}
                            onChange={(e) => handleParamChange('partial_tp_enabled', e.target.checked)}
                            className="accent-[#10B981]"
                          />
                        </label>
                        {params.partial_tp_enabled && (
                          <div className="grid grid-cols-2 gap-2.5 pt-1">
                            <div>
                              <span className="block text-[10px] text-[#64748B]">
                                {tr(lang, 'Déclenchement (en R)', 'Trigger (in R)')} (partial_tp_rr [0.3..10])
                              </span>
                              <input
                                type="number"
                                step="0.1"
                                min={0.3}
                                max={10}
                                value={params.partial_tp_rr}
                                onChange={(e) => handleParamChange('partial_tp_rr', Number(e.target.value))}
                                className="w-full mt-0.5 px-2 py-1 bg-[#111827] border border-white/10 rounded text-xs font-mono-tabular"
                              />
                            </div>
                            <div>
                              <span className="block text-[10px] text-[#64748B]">
                                {tr(lang, 'Part clôturée (%)', 'Closed Portion (%)')} (partial_tp_close_pct [10..90])
                              </span>
                              <input
                                type="number"
                                step="5"
                                min={10}
                                max={90}
                                value={params.partial_tp_close_pct}
                                onChange={(e) => handleParamChange('partial_tp_close_pct', Number(e.target.value))}
                                className="w-full mt-0.5 px-2 py-1 bg-[#111827] border border-white/10 rounded text-xs font-mono-tabular"
                              />
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Break-Even */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.07] space-y-2.5">
                        <label className="flex items-center justify-between text-xs font-medium text-[#F1F5F9] cursor-pointer">
                          <div>
                            <span>{tr(lang, 'Mise à Break-Even Automatique', 'Automatic Break-Even')}</span>
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">breakeven_enabled (bool)</span>
                          </div>
                          <input
                            type="checkbox"
                            checked={params.breakeven_enabled}
                            onChange={(e) => handleParamChange('breakeven_enabled', e.target.checked)}
                            className="accent-[#10B981]"
                          />
                        </label>
                        {params.breakeven_enabled && (
                          <div>
                            <span className="block text-[10px] text-[#64748B]">
                              {tr(lang, "Seuil d'activation Break-Even (Multiple R)", 'Break-Even Activation Threshold (R Multiple)')} (breakeven_trigger_rr [0.3..10])
                            </span>
                            <input
                              type="number"
                              step="0.1"
                              min={0.3}
                              max={10}
                              value={params.breakeven_trigger_rr}
                              onChange={(e) => handleParamChange('breakeven_trigger_rr', Number(e.target.value))}
                              className="w-full mt-0.5 px-2 py-1 bg-[#111827] border border-white/10 rounded text-xs font-mono-tabular"
                            />
                          </div>
                        )}
                      </div>

                      {/* Trailing Stop */}
                      <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.07] space-y-2.5">
                        <label className="flex items-center justify-between text-xs font-medium text-[#F1F5F9] cursor-pointer">
                          <div>
                            <span>{tr(lang, 'Trailing Stop Dynamique (ATR)', 'Dynamic Trailing Stop (ATR)')}</span>
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">trailing_stop_enabled (bool)</span>
                          </div>
                          <input
                            type="checkbox"
                            checked={params.trailing_stop_enabled}
                            onChange={(e) => handleParamChange('trailing_stop_enabled', e.target.checked)}
                            className="accent-[#10B981]"
                          />
                        </label>
                        {params.trailing_stop_enabled && (
                          <div className="grid grid-cols-2 gap-2.5 pt-1">
                            <div>
                              <span className="block text-[10px] text-[#64748B]">
                                {tr(lang, 'Activation (en R)', 'Activation (in R)')} (trailing_activation_rr [0.4..10])
                              </span>
                              <input
                                type="number"
                                step="0.1"
                                min={0.4}
                                max={10}
                                value={params.trailing_activation_rr}
                                onChange={(e) => handleParamChange('trailing_activation_rr', Number(e.target.value))}
                                className="w-full mt-0.5 px-2 py-1 bg-[#111827] border border-white/10 rounded text-xs font-mono-tabular"
                              />
                            </div>
                            <div>
                              <span className="block text-[10px] text-[#64748B]">
                                {tr(lang, 'Distance suivi (x ATR)', 'Trailing Distance (x ATR)')} (trailing_distance_atr [0.3..10])
                              </span>
                              <input
                                type="number"
                                step="0.1"
                                min={0.3}
                                max={10}
                                value={params.trailing_distance_atr}
                                onChange={(e) => handleParamChange('trailing_distance_atr', Number(e.target.value))}
                                className="w-full mt-0.5 px-2 py-1 bg-[#111827] border border-white/10 rounded text-xs font-mono-tabular"
                              />
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <label className="flex items-center justify-between p-2.5 rounded-lg bg-[#090D16] border border-white/10 text-xs cursor-pointer">
                          <div>
                            <span className="text-[#94A3B8]">{tr(lang, 'Sortie signal opposé', 'Exit on opposite signal')}</span>
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">exit_on_opposite_signal</span>
                          </div>
                          <input
                            type="checkbox"
                            checked={params.exit_on_opposite_signal}
                            onChange={(e) => handleParamChange('exit_on_opposite_signal', e.target.checked)}
                            className="accent-[#10B981]"
                          />
                        </label>
                        <div>
                          <label className="block text-[10px] text-[#64748B] mb-1">
                            {tr(lang, 'Durée Max (Bougies)', 'Max Duration (Candles)')} (max_bars_in_trade [4..1000])
                          </label>
                          <input
                            type="number"
                            min={4}
                            max={1000}
                            value={params.max_bars_in_trade}
                            onChange={(e) => handleParamChange('max_bars_in_trade', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* CATEGORY 3: TECHNICAL INDICATORS PARAMETERS */}
                  {paramCategory === 'indicators' && (
                    <div className="space-y-3.5">
                      <div className="grid grid-cols-3 gap-2.5">
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'EMA Rapide', 'Fast EMA')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">ema_fast [3..100]</span>
                          </label>
                          <input
                            type="number"
                            min={3}
                            max={100}
                            value={params.ema_fast}
                            onChange={(e) => handleParamChange('ema_fast', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'EMA Lente', 'Slow EMA')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">ema_slow [5..250]</span>
                          </label>
                          <input
                            type="number"
                            min={5}
                            max={250}
                            value={params.ema_slow}
                            onChange={(e) => handleParamChange('ema_slow', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'EMA Tendance', 'Trend EMA')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">ema_trend [20..500]</span>
                          </label>
                          <input
                            type="number"
                            min={20}
                            max={500}
                            value={params.ema_trend}
                            onChange={(e) => handleParamChange('ema_trend', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-2.5">
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Période RSI', 'RSI Period')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">rsi_period [4..50]</span>
                          </label>
                          <input
                            type="number"
                            min={4}
                            max={50}
                            value={params.rsi_period}
                            onChange={(e) => handleParamChange('rsi_period', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'RSI Survente', 'RSI Oversold')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">rsi_oversold [10..49]</span>
                          </label>
                          <input
                            type="number"
                            min={10}
                            max={49}
                            value={params.rsi_oversold}
                            onChange={(e) => handleParamChange('rsi_oversold', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'RSI Surachat', 'RSI Overbought')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">rsi_overbought [51..90]</span>
                          </label>
                          <input
                            type="number"
                            min={51}
                            max={90}
                            value={params.rsi_overbought}
                            onChange={(e) => handleParamChange('rsi_overbought', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-2.5">
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Période ATR', 'ATR Period')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">atr_period [5..50]</span>
                          </label>
                          <input
                            type="number"
                            min={5}
                            max={50}
                            value={params.atr_period}
                            onChange={(e) => handleParamChange('atr_period', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Période ADX', 'ADX Period')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">adx_period [5..50]</span>
                          </label>
                          <input
                            type="number"
                            min={5}
                            max={50}
                            value={params.adx_period}
                            onChange={(e) => handleParamChange('adx_period', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-[#94A3B8] mb-1">
                            {tr(lang, 'MA Volume', 'Volume MA')}
                            <span className="block text-[9px] font-mono-tabular text-[#64748B]">volume_ma_period [5..100]</span>
                          </label>
                          <input
                            type="number"
                            min={5}
                            max={100}
                            value={params.volume_ma_period}
                            onChange={(e) => handleParamChange('volume_ma_period', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* CATEGORY 4: CAPITAL, POSITION SIZING, FEES & SLIPPAGE */}
                  {paramCategory === 'capital' && (
                    <div className="space-y-3.5">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Capital Initial (USDT)', 'Initial Capital (USDT)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">initial_capital [100..10M]</span>
                          </label>
                          <input
                            type="number"
                            step="500"
                            min={100}
                            max={10000000}
                            value={params.initial_capital}
                            onChange={(e) => handleParamChange('initial_capital', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Levier Simulé (x)', 'Simulated Leverage (x)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">leverage [1..50] x</span>
                          </label>
                          <input
                            type="number"
                            step="1"
                            min={1}
                            max={50}
                            value={params.leverage}
                            onChange={(e) => handleParamChange('leverage', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-[11px] text-[#94A3B8] mb-1">
                          {tr(lang, 'Mode de Dimensionnement (Position Sizing)', 'Position Sizing Mode')}
                          <span className="block text-[10px] font-mono-tabular text-[#64748B]">position_sizing_mode • enum [risk_pct, capital_pct, fixed_usdt]</span>
                        </label>
                        <select
                          value={params.position_sizing_mode}
                          onChange={(e) => handleParamChange('position_sizing_mode', e.target.value as any)}
                          className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs text-[#F1F5F9]"
                        >
                          <option value="risk_pct">
                            {tr(lang, 'Risque en % du Capital par Trade (basé sur distance SL)', 'Risk % of Capital per Trade (based on SL distance)')}
                          </option>
                          <option value="capital_pct">{tr(lang, '% Fixe du Capital Alloué', 'Fixed % of Allocated Capital')}</option>
                          <option value="fixed_usdt">{tr(lang, 'Montant Fixe en USDT par Trade', 'Fixed USDT Amount per Trade')}</option>
                        </select>
                      </div>

                      {params.position_sizing_mode === 'risk_pct' && (
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Risque par Trade (% du capital perdu si SL touché)', 'Risk per Trade (% of capital lost if SL hit)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">risk_per_trade_pct [0.1..25] %</span>
                          </label>
                          <input
                            type="number"
                            step="0.25"
                            min={0.1}
                            max={25}
                            value={params.risk_per_trade_pct}
                            onChange={(e) => handleParamChange('risk_per_trade_pct', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      )}

                      {params.position_sizing_mode === 'capital_pct' && (
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Allocation Capital par Position (%)', 'Capital Allocation per Position (%)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">capital_allocation_pct [1..100] %</span>
                          </label>
                          <input
                            type="number"
                            step="1"
                            min={1}
                            max={100}
                            value={params.capital_allocation_pct}
                            onChange={(e) => handleParamChange('capital_allocation_pct', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      )}

                      {params.position_sizing_mode === 'fixed_usdt' && (
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Mise Fixe par Position (USDT)', 'Fixed Size per Position (USDT)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">fixed_position_usdt [10..1M] USDT</span>
                          </label>
                          <input
                            type="number"
                            step="100"
                            min={10}
                            max={1000000}
                            value={params.fixed_position_usdt}
                            onChange={(e) => handleParamChange('fixed_position_usdt', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      )}

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Frais Taker (bps, 4 = 0.04%)', 'Taker Fees (bps, 4 = 0.04%)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">fee_bps [0..100] bps</span>
                          </label>
                          <input
                            type="number"
                            step="0.5"
                            min={0}
                            max={100}
                            value={params.fee_bps}
                            onChange={(e) => handleParamChange('fee_bps', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Slippage Estimé (bps)', 'Estimated Slippage (bps)')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">slippage_bps [0..100] bps</span>
                          </label>
                          <input
                            type="number"
                            step="0.5"
                            min={0}
                            max={100}
                            value={params.slippage_bps}
                            onChange={(e) => handleParamChange('slippage_bps', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Trades Max / Jour', 'Max Trades / Day')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">max_trades_per_day [1..100]</span>
                          </label>
                          <input
                            type="number"
                            min={1}
                            max={100}
                            value={params.max_trades_per_day}
                            onChange={(e) => handleParamChange('max_trades_per_day', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-[#94A3B8] mb-1">
                            {tr(lang, 'Coupe-circuit Pertes Conséc.', 'Max Consecutive Losses')}
                            <span className="block text-[10px] font-mono-tabular text-[#64748B]">max_consecutive_losses [1..50]</span>
                          </label>
                          <input
                            type="number"
                            min={1}
                            max={50}
                            value={params.max_consecutive_losses}
                            onChange={(e) => handleParamChange('max_consecutive_losses', Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </fieldset>

                {/* Live Configuration Changes Summary before Backtest */}
                <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.07] space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-mono-tabular">
                    <span className="uppercase text-[#94A3B8] font-semibold">
                      {tr(lang, 'Changements de Configuration (Diff)', 'Configuration Changes')}
                    </span>
                    <span className={liveParamsDiff.length > 0 ? 'text-[#F59E0B] font-bold' : 'text-[#64748B]'}>
                      {liveParamsDiff.length > 0
                        ? `${liveParamsDiff.length} ${tr(lang, 'paramètre(s) modifié(s)', 'parameters changed')}`
                        : tr(lang, 'Aucun changement détecté', 'No configuration changes detected.')}
                    </span>
                  </div>
                  {liveParamsDiff.length > 0 && (
                    <div className="space-y-1 max-h-28 overflow-y-auto pt-1">
                      {liveParamsDiff.map((chg) => (
                        <div
                          key={chg.param}
                          className="flex items-center justify-between text-[11px] font-mono-tabular bg-[#111827] px-2 py-1 rounded border border-white/[0.05]"
                        >
                          <span className="text-[#F1F5F9] font-semibold">{chg.param}</span>
                          <span className="text-[#94A3B8]">
                            <span className="text-[#64748B]">{String(chg.old_value)}</span>
                            <span className="mx-1.5 text-[#10B981]">→</span>
                            <span className="text-[#10B981] font-bold">{String(chg.new_value)}</span>
                          </span>
                        </div>
                      ))}
                      <div className="text-[10px] text-[#64748B] pt-0.5">
                        {tr(lang, 'Tous les autres paramètres restent inchangés.', 'All other parameters remain unchanged.')}
                      </div>
                    </div>
                  )}
                </div>

                {/* Action Buttons inside Visual Parameter Editor */}
                <div className="pt-2 border-t border-white/[0.07] flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={() => executeBacktest(params, false, false)}
                    disabled={runningBacktest}
                    className="w-full py-2.5 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-[#090D16] font-semibold text-xs flex items-center justify-center gap-2 transition-colors"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>
                      {runningBacktest
                        ? tr(lang, 'Calcul en cours...', 'Computing...')
                        : tr(lang, 'Simuler ce Scénario (B)', 'Simulate Scenario (B)')}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => executeBacktest(baselineParams, true, false)}
                    disabled={runningCompare}
                    className="w-full py-2 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-xs text-[#F1F5F9] flex items-center justify-center gap-2 transition-colors"
                  >
                    <GitCompare className="w-3.5 h-3.5 text-[#60A5FA]" />
                    <span>
                      {runningCompare
                        ? tr(lang, 'Calcul référence...', 'Computing baseline...')
                        : tr(lang, 'Épingler la Référence Actuelle pour Comparaison A/B', 'Pin Current Baseline for A/B Comparison')}
                    </span>
                  </button>
                </div>
              </div>
            </>
          )}

          {/* =================================================================
              MODE 2: RAW CONFIG (TEXT EDITOR, STRICT PARSER & DIFF PREVIEW)
             ================================================================= */}
          {configEditorMode === 'raw' && (
            <div className="p-4 space-y-4">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="text-xs text-[#94A3B8]">
                  {tr(
                    lang,
                    'Éditez ou collez les paramètres existants au format KEY=VALUE. Toute variable inconnue ou hors modèle sélectionné est rejetée.',
                    'Edit or paste existing parameters in KEY=VALUE format. Any unknown variable or unselected model parameter is strictly rejected.'
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard?.writeText(rawConfigText);
                      onShowToast('success', tr(lang, 'Raw Config copiée dans le presse-papiers.', 'Raw Config copied to clipboard.'));
                    }}
                    className="px-2.5 py-1 rounded bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-[11px] font-mono-tabular text-[#F1F5F9] flex items-center gap-1"
                  >
                    <Copy className="w-3 h-3 text-[#10B981]" />
                    <span>{tr(lang, 'Copier', 'Copy')}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const resetTxt = formatRawConfigText(
                        baselineParams,
                        selectedModels,
                        labSchema.models || DEFAULT_LAB_MODELS,
                        labSchema.parameters || DEFAULT_LAB_PARAM_SPECS
                      );
                      setParams(baselineParams);
                      setRawConfigText(resetTxt);
                      setRawConfigValid(true);
                      setRawConfigErrors([]);
                      setRawConfigDiff([]);
                      onShowToast('info', tr(lang, 'Raw Config restaurée à la référence.', 'Raw Config reverted to baseline.'));
                    }}
                    className="px-2.5 py-1 rounded bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-[11px] font-mono-tabular text-[#94A3B8] hover:text-[#F1F5F9] flex items-center gap-1"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>{tr(lang, 'Réinitialiser', 'Reset')}</span>
                  </button>
                </div>
              </div>

              {/* Raw Config Textarea */}
              <div>
                <textarea
                  value={rawConfigText}
                  onChange={(e) => {
                    setRawConfigText(e.target.value);
                    setRawConfigValid(null);
                  }}
                  rows={14}
                  spellCheck={false}
                  placeholder="min_teddy_score=58&#10;rsi_oversold=32.0&#10;rsi_overbought=68.0"
                  className="w-full p-3 rounded-lg bg-[#090D16] border border-white/15 focus:border-[#10B981] text-xs font-mono-tabular text-[#F1F5F9] leading-relaxed focus:outline-none"
                />
              </div>

              {/* Validation Error Banner */}
              {rawConfigErrors.length > 0 && (
                <div className="p-3 rounded-lg bg-[#F43F5E]/10 border border-[#F43F5E]/30 space-y-1">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-[#F43F5E]">
                    <XCircle className="w-4 h-4 shrink-0" />
                    <span>Invalid configuration</span>
                  </div>
                  {rawConfigErrors.map((err, i) => (
                    <div key={i} className="text-[11px] font-mono-tabular text-[#FDA4AF]">
                      {err}
                    </div>
                  ))}
                </div>
              )}

              {/* Diff Preview Before Backtest */}
              <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.07] space-y-2">
                <div className="flex items-center justify-between text-xs font-mono-tabular">
                  <span className="uppercase text-[#94A3B8] font-semibold">
                    Configuration changes
                  </span>
                  {rawConfigValid === true && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-[#10B981]">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      {tr(lang, 'Validé', 'Validated')}
                    </span>
                  )}
                </div>

                {rawConfigErrors.length > 0 ? (
                  <div className="text-xs font-mono-tabular text-[#F43F5E]">
                    Invalid configuration — {tr(lang, 'lancement bloqué.', 'launch blocked.')}
                  </div>
                ) : (rawConfigDiff.length > 0 ? rawConfigDiff : liveParamsDiff).length === 0 ? (
                  <div className="text-xs font-mono-tabular text-[#64748B]">
                    No configuration changes detected.
                  </div>
                ) : (
                  <div className="space-y-1.5 max-h-40 overflow-y-auto">
                    {(rawConfigDiff.length > 0 ? rawConfigDiff : liveParamsDiff).map((chg) => (
                      <div
                        key={chg.param}
                        className="p-2 rounded bg-[#111827] border border-white/[0.06] flex items-center justify-between text-xs font-mono-tabular"
                      >
                        <div>
                          <div className="font-bold text-[#F1F5F9]">{chg.param}</div>
                          <div className="text-[10px] text-[#64748B]">{chg.model}</div>
                        </div>
                        <div className="text-right">
                          <span className="text-[#94A3B8]">{String(chg.old_value)}</span>
                          <span className="mx-1.5 text-[#10B981]">→</span>
                          <span className="text-[#10B981] font-bold">{String(chg.new_value)}</span>
                        </div>
                      </div>
                    ))}
                    <div className="text-[11px] font-mono-tabular text-[#94A3B8] pt-1">
                      {(rawConfigDiff.length > 0 ? rawConfigDiff : liveParamsDiff).length} parameters changed. All other parameters remain unchanged.
                    </div>
                  </div>
                )}
              </div>

              {/* Separation of Strategy Config & Backtest Config */}
              <div className="p-3 rounded-lg bg-[#090D16]/60 border border-white/[0.05] text-[11px] font-mono-tabular space-y-1 text-[#94A3B8]">
                <div className="text-[10px] uppercase text-[#64748B] font-bold">
                  BACKTEST CONFIG ({tr(lang, 'Séparé des variables de modèles', 'Separated from model variables')})
                </div>
                <div>Asset: <strong className="text-[#F1F5F9]">{symbol}</strong> • Timeframe: <strong className="text-[#F1F5F9]">{timeframe}</strong> • Style: <strong className="text-[#F1F5F9]">{tradingStyle.toUpperCase()}</strong></div>
                <div>Period: <strong className="text-[#F1F5F9]">{activeRun?.start_date || startDate || 'Auto'}</strong> → <strong className="text-[#F1F5F9]">{activeRun?.end_date || endDate || 'Latest closed candle'}</strong> ({maxCandles} candles)</div>
                <div>Initial simulated capital: <strong className="text-[#10B981]">{params.initial_capital} USDT</strong></div>
              </div>

              {/* Raw Config Actions */}
              <div className="flex flex-col gap-2 pt-1">
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => handleValidateRawConfig(rawConfigText, false)}
                    disabled={validatingRawConfig}
                    className="py-2 px-3 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/15 text-xs font-semibold text-[#F1F5F9] flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 text-[#10B981]" />
                    <span>
                      {validatingRawConfig
                        ? tr(lang, 'Validation...', 'Validating...')
                        : tr(lang, 'Valider Raw Config', 'Validate Raw Config')}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowSavePresetModal(true)}
                    className="py-2 px-3 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/15 text-xs font-semibold text-[#F1F5F9] flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <Save className="w-3.5 h-3.5 text-[#60A5FA]" />
                    <span>{tr(lang, 'Sauver Preset', 'Save Preset')}</span>
                  </button>
                </div>

                <button
                  type="button"
                  onClick={() => executeBacktest(params, false, true)}
                  disabled={runningBacktest || rawConfigErrors.length > 0}
                  className="w-full py-2.5 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-40 text-[#090D16] font-semibold text-xs flex items-center justify-center gap-2 transition-colors"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>
                    {runningBacktest
                      ? tr(lang, 'Simulation en cours...', 'Simulating...')
                      : tr(lang, 'Valider & Lancer le Backtest (Nouvelle Expérience)', 'Validate & Run Backtest (New Experiment)')}
                  </span>
                </button>
              </div>
            </div>
          )}

          {/* =================================================================
              MODE 3: AI PROMPT GENERATOR (100% LOCAL, NO EXTERNAL AI CALL)
             ================================================================= */}
          {configEditorMode === 'ai_prompt' && (
            <div className="p-4 space-y-4">
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-[#F1F5F9] flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-[#10B981]" />
                    <span>AI Prompt Generator</span>
                  </span>
                  <span className="text-[10px] font-mono-tabular px-2 py-0.5 rounded bg-[#10B981]/10 text-[#10B981] border border-[#10B981]/25">
                    {tr(lang, '100% Local • Sans clé API', '100% Local • No API Key')}
                  </span>
                </div>
                <p className="text-[11px] text-[#94A3B8]">
                  {tr(
                    lang,
                    "Prompt structuré généré dynamiquement à partir de vos vrais paramètres Bitsure, des modèles cochés et des résultats du backtest actif. Copiez-le dans n'importe quelle IA externe (ChatGPT, Claude, Gemini), puis collez sa réponse dans Raw Config.",
                    'Structured prompt dynamically generated from your real Bitsure parameters, selected models, and active backtest results. Copy it into any external AI, then paste its response into Raw Config.'
                  )}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (!generatedAiPrompt) return;
                    navigator.clipboard?.writeText(generatedAiPrompt);
                    onShowToast(
                      'success',
                      tr(lang, 'Prompt IA copié ! Collez-le dans votre IA externe.', 'AI Prompt copied! Paste it into your external AI.')
                    );
                  }}
                  disabled={!generatedAiPrompt}
                  className="flex-1 py-2.5 px-3 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-40 text-[#090D16] font-semibold text-xs flex items-center justify-center gap-1.5 transition-colors shadow-lg shadow-[#10B981]/10"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy AI Prompt</span>
                </button>
                <button
                  type="button"
                  onClick={handleGenerateAiPrompt}
                  disabled={generatingAiPrompt}
                  className="py-2.5 px-3 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-xs text-[#F1F5F9] flex items-center gap-1"
                >
                  <RotateCcw className={`w-3.5 h-3.5 ${generatingAiPrompt ? 'animate-spin' : ''}`} />
                  <span>{tr(lang, 'Actualiser', 'Refresh')}</span>
                </button>
              </div>

              <textarea
                readOnly
                value={generatedAiPrompt}
                rows={18}
                className="w-full p-3 rounded-lg bg-[#090D16] border border-white/15 text-[11px] font-mono-tabular text-[#E2E8F0] leading-relaxed focus:outline-none"
              />

              <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.07] text-[11px] text-[#94A3B8] space-y-1">
                <div className="font-semibold text-[#F1F5F9]">
                  {tr(lang, 'Flux recommandé :', 'Recommended workflow:')}
                </div>
                <div>1. {tr(lang, 'Cliquez sur « Copy AI Prompt » et collez-le dans votre IA.', 'Click "Copy AI Prompt" and paste it into your AI.')}</div>
                <div>2. {tr(lang, "Copiez la section PROPOSED CHANGES de la réponse de l'IA.", "Copy the PROPOSED CHANGES section from the AI's response.")}</div>
                <div>3. {tr(lang, 'Collez-la dans l’onglet « Raw Config », vérifiez le Diff et lancez le backtest.', 'Paste it into the "Raw Config" tab, inspect the Diff, and run the backtest.')}</div>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: ANALYTICS, CHARTS, DIAGNOSTICS, TRADES & SWEEP */}
        <div className="lg:col-span-8 space-y-6">
          {/* Sub-navigation tabs */}
          <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-1.5 flex flex-wrap gap-1">
            {[
              { id: 'overview', label: tr(lang, 'Synthèse & Courbe Equity', 'Overview & Equity Curve'), icon: TrendingUp },
              { id: 'chart', label: tr(lang, 'Graphique & Signaux', 'Chart & Signals'), icon: Activity },
              {
                id: 'trades',
                label: `${tr(lang, 'Journal des Trades', 'Trade Journal')} (${activeRun?.trades?.length || 0})`,
                icon: Layers,
              },
              { id: 'diagnostics', label: tr(lang, 'Diagnostic des Filtres', 'Filter Diagnostics'), icon: Filter },
              {
                id: 'compare',
                label: compareRun
                  ? tr(lang, 'Comparateur A/B (Actif)', 'A/B Comparator (Active)')
                  : tr(lang, 'Comparateur A/B', 'A/B Comparator'),
                icon: GitCompare,
              },
              { id: 'sweep', label: tr(lang, 'Optimisation (Sweep)', 'Sensitivity Sweep'), icon: Sparkles },
              { id: 'history', label: `${tr(lang, 'Historique', 'History')} (${savedRuns.length})`, icon: Bookmark },
            ].map((tab) => {
              const Icon = tab.icon;
              const active = labSection === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setLabSection(tab.id as any)}
                  className={`px-3 py-2 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors ${
                    active
                      ? 'bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30'
                      : 'text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-white/[0.04]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* =================================================================
              KPI SUMMARY CARDS (Always visible for immediate feedback)
             ================================================================= */}
          {m && (
            <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
              <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-3.5">
                <div className="text-[10px] font-mono-tabular uppercase text-[#64748B]">
                  {tr(lang, 'Rendement Net', 'Net Return')}
                </div>
                <div
                  className={`text-lg font-mono-tabular font-bold mt-0.5 ${
                    m.total_return_pct >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                  }`}
                >
                  {m.total_return_pct >= 0 ? '+' : ''}
                  {m.total_return_pct.toFixed(2)}%
                </div>
                <div className="text-[11px] font-mono-tabular text-[#94A3B8]">
                  {m.net_profit_usdt >= 0 ? '+' : ''}
                  {m.net_profit_usdt.toFixed(2)} USDT
                </div>
              </div>

              <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-3.5">
                <div className="text-[10px] font-mono-tabular uppercase text-[#64748B]">
                  Win Rate &amp; Trades
                </div>
                <div className="text-lg font-mono-tabular font-bold text-[#F1F5F9] mt-0.5">
                  {m.win_rate_pct.toFixed(1)}%
                </div>
                <div className="text-[11px] font-mono-tabular text-[#94A3B8]">
                  {m.winning_trades}W / {m.losing_trades}L ({m.total_trades})
                </div>
              </div>

              <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-3.5">
                <div className="text-[10px] font-mono-tabular uppercase text-[#64748B]">
                  Profit Factor
                </div>
                <div
                  className={`text-lg font-mono-tabular font-bold mt-0.5 ${
                    m.profit_factor >= 1.3
                      ? 'text-[#10B981]'
                      : m.profit_factor >= 1.0
                      ? 'text-[#F59E0B]'
                      : 'text-[#F43F5E]'
                  }`}
                >
                  {m.profit_factor.toFixed(2)}
                </div>
                <div className="text-[11px] font-mono-tabular text-[#94A3B8]">
                  Payoff : {m.payoff_ratio.toFixed(2)}x
                </div>
              </div>

              <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-3.5">
                <div className="text-[10px] font-mono-tabular uppercase text-[#64748B]">
                  {tr(lang, 'Drawdown Max', 'Max Drawdown')}
                </div>
                <div className="text-lg font-mono-tabular font-bold text-[#F43F5E] mt-0.5">
                  -{m.max_drawdown_pct.toFixed(2)}%
                </div>
                <div className="text-[11px] font-mono-tabular text-[#94A3B8]">
                  -{m.max_drawdown_usdt.toFixed(0)} USDT
                </div>
              </div>

              <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-3.5">
                <div className="text-[10px] font-mono-tabular uppercase text-[#64748B]">
                  {tr(lang, 'Espérance / Trade', 'Expectancy / Trade')}
                </div>
                <div
                  className={`text-lg font-mono-tabular font-bold mt-0.5 ${
                    m.expectancy_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                  }`}
                >
                  {m.expectancy_usdt >= 0 ? '+' : ''}
                  {m.expectancy_usdt.toFixed(2)}$
                </div>
                <div className="text-[11px] font-mono-tabular text-[#94A3B8]">
                  {tr(lang, 'Moy :', 'Avg:')} {m.avg_r_multiple >= 0 ? '+' : ''}
                  {m.avg_r_multiple.toFixed(2)} R
                </div>
              </div>

              <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-3.5">
                <div className="text-[10px] font-mono-tabular uppercase text-[#64748B]">
                  Sharpe / Sortino
                </div>
                <div className="text-lg font-mono-tabular font-bold text-[#60A5FA] mt-0.5">
                  {m.sharpe_ratio.toFixed(2)}
                </div>
                <div className="text-[11px] font-mono-tabular text-[#94A3B8]">
                  Sortino : {m.sortino_ratio.toFixed(2)}
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              SECTION 1: OVERVIEW, EQUITY CURVE, DRAWDOWN & DIAGNOSTIC INSIGHTS
             ================================================================= */}
          {labSection === 'overview' && activeRun && m && (
            <div className="space-y-6">
              {/* Automatic Quantitative Diagnostics Banner */}
              {activeRun.diagnostics && activeRun.diagnostics.length > 0 && (
                <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-4 space-y-2.5">
                  <div className="text-xs font-mono-tabular uppercase tracking-wider text-[#94A3B8] flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-[#10B981]" />
                    <span>
                      {tr(
                        lang,
                        'Diagnostic Automatique du Comportement de la Stratégie',
                        'Automated Strategy Behavior Diagnostics'
                      )}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {activeRun.diagnostics.map((d, idx) => (
                      <div
                        key={idx}
                        className={`p-3 rounded-lg border text-xs space-y-1 ${
                          d.severity === 'success'
                            ? 'bg-[#10B981]/10 border-[#10B981]/30 text-[#34D399]'
                            : d.severity === 'warning'
                            ? 'bg-[#F59E0B]/10 border-[#F59E0B]/30 text-[#FBBF24]'
                            : d.severity === 'error'
                            ? 'bg-[#F43F5E]/10 border-[#F43F5E]/30 text-[#FB7185]'
                            : 'bg-[#3B82F6]/10 border-[#3B82F6]/30 text-[#60A5FA]'
                        }`}
                      >
                        <div className="font-semibold flex items-center gap-1.5">
                          {d.severity === 'success' && <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />}
                          {d.severity === 'warning' && <AlertTriangle className="w-3.5 h-3.5 shrink-0" />}
                          {d.severity === 'error' && <XCircle className="w-3.5 h-3.5 shrink-0" />}
                          <span>{d.title}</span>
                        </div>
                        <p className="text-[11px] text-[#E2E8F0] leading-relaxed">{d.detail}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Equity Curve & Underwater Drawdown Chart */}
              <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="font-display text-sm font-semibold text-[#F1F5F9]">
                      {tr(
                        lang,
                        "Courbe d'Équité du Portefeuille & Drawdown (USDT)",
                        'Portfolio Equity Curve & Drawdown (USDT)'
                      )}
                    </h3>
                    <p className="text-xs text-[#64748B]">
                      {tr(lang, 'Capital Initial :', 'Initial Capital:')} {m.initial_capital.toLocaleString()} USDT →{' '}
                      {tr(lang, 'Final :', 'Final:')}{' '}
                      <strong className="text-[#F1F5F9]">{m.final_capital.toLocaleString()} USDT</strong>{' '}
                      (Benchmark Buy &amp; Hold : {m.buy_hold_return_pct >= 0 ? '+' : ''}
                      {m.buy_hold_return_pct}% | Alpha : {m.alpha_vs_buy_hold_pct >= 0 ? '+' : ''}
                      {m.alpha_vs_buy_hold_pct}%)
                    </p>
                  </div>
                  <div className="text-xs font-mono-tabular text-[#94A3B8]">
                    {tr(lang, 'Frais totaux déduits :', 'Total fees deducted:')}{' '}
                    <span className="text-[#F59E0B]">{m.total_fees_usdt.toFixed(2)} USDT</span>
                  </div>
                </div>

                <EquityAndDrawdownChart
                  data={activeRun.equity_curve || []}
                  initialCapital={m.initial_capital}
                  lang={lang}
                />
              </div>

              {/* Detailed Institutional Breakdown Table */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-3">
                  <h4 className="font-display text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                    {tr(lang, 'Statistiques Détaillées Long vs Short & Séries', 'Detailed Long vs Short & Streak Statistics')}
                  </h4>
                  <div className="space-y-2 text-xs font-mono-tabular">
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">
                        {tr(lang, 'Performance LONG', 'LONG Performance')} ({m.long_trades} trades)
                      </span>
                      <span className={m.long_pnl_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                        {m.long_pnl_usdt >= 0 ? '+' : ''}
                        {m.long_pnl_usdt.toFixed(2)} USDT ({m.long_win_rate_pct}% WR)
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">
                        {tr(lang, 'Performance SHORT', 'SHORT Performance')} ({m.short_trades} trades)
                      </span>
                      <span className={m.short_pnl_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                        {m.short_pnl_usdt >= 0 ? '+' : ''}
                        {m.short_pnl_usdt.toFixed(2)} USDT ({m.short_win_rate_pct}% WR)
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">
                        {tr(lang, 'Gain Moyen / Perte Moyenne', 'Average Win / Average Loss')}
                      </span>
                      <span className="text-[#F1F5F9]">
                        <strong className="text-[#10B981]">+{m.avg_win_usdt.toFixed(2)}$</strong> /{' '}
                        <strong className="text-[#F43F5E]">{m.avg_loss_usdt.toFixed(2)}$</strong>
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">{tr(lang, 'Meilleur / Pire Trade', 'Best / Worst Trade')}</span>
                      <span className="text-[#F1F5F9]">
                        <strong className="text-[#10B981]">+{m.best_trade_usdt.toFixed(2)}$</strong> /{' '}
                        <strong className="text-[#F43F5E]">{m.worst_trade_usdt.toFixed(2)}$</strong>
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">
                        {tr(lang, 'Série Max Gains / Pertes consécutifs', 'Max Consecutive Wins / Losses')}
                      </span>
                      <span className="text-[#F1F5F9]">
                        {m.max_win_streak} W / {m.max_loss_streak} L
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-[#94A3B8]">
                        {tr(lang, "Durée moyenne d'exposition", 'Average holding duration')}
                      </span>
                      <span className="text-[#F1F5F9]">
                        {m.avg_bars_held} {tr(lang, 'bougies', 'candles')} (~{m.avg_duration_minutes} min)
                      </span>
                    </div>
                  </div>
                </div>

                <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-3">
                  <h4 className="font-display text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                    {tr(lang, 'Répartition des Sorties par Motif (Exit Breakdown)', 'Exit Breakdown by Reason')}
                  </h4>
                  <div className="space-y-2 text-xs font-mono-tabular">
                    {Object.entries(m.by_exit_reason || {}).map(([reason, stats]) => (
                      <div
                        key={reason}
                        className="flex items-center justify-between p-2 rounded-lg bg-[#090D16] border border-white/[0.06]"
                      >
                        <div>
                          <span className="font-semibold text-[#F1F5F9]">{reason}</span>
                          <span className="ml-2 text-[11px] text-[#64748B]">
                            ({stats.count} trades • {stats.wins} {tr(lang, 'gagnants', 'winners')})
                          </span>
                        </div>
                        <span
                          className={`font-bold ${
                            stats.pnl_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                          }`}
                        >
                          {stats.pnl_usdt >= 0 ? '+' : ''}
                          {stats.pnl_usdt.toFixed(2)} USDT
                        </span>
                      </div>
                    ))}
                    {Object.keys(m.by_exit_reason || {}).length === 0 && (
                      <div className="text-[#64748B] py-4 text-center">
                        {tr(lang, 'Aucune sortie enregistrée.', 'No exits recorded.')}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              SECTION 2: HISTORICAL PRICE CHART WITH ENTRY / EXIT MARKERS & EMAs
             ================================================================= */}
          {labSection === 'chart' && activeRun && (
            <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="font-display text-sm font-semibold text-[#F1F5F9]">
                    {tr(
                      lang,
                      `Graphique Historique ${activeRun.symbol} (${activeRun.timeframe}) & Signaux Exécutés`,
                      `Historical Chart ${activeRun.symbol} (${activeRun.timeframe}) & Executed Signals`
                    )}
                  </h3>
                  <p className="text-xs text-[#64748B]">
                    {tr(
                      lang,
                      `Superposition Prix Close, EMA Rapide (${activeRun.params.ema_fast}), EMA Lente (${activeRun.params.ema_slow}), EMA Tendance (${activeRun.params.ema_trend}) et marqueurs d'entrée/sortie.`,
                      `Close Price overlay, Fast EMA (${activeRun.params.ema_fast}), Slow EMA (${activeRun.params.ema_slow}), Trend EMA (${activeRun.params.ema_trend}), and entry/exit markers.`
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-[11px] font-mono-tabular">
                  <span className="inline-flex items-center gap-1 text-[#10B981]">● EMA {activeRun.params.ema_fast}</span>
                  <span className="inline-flex items-center gap-1 text-[#3B82F6]">● EMA {activeRun.params.ema_slow}</span>
                  <span className="inline-flex items-center gap-1 text-[#F59E0B]">● EMA {activeRun.params.ema_trend}</span>
                </div>
              </div>

              <LabCandlesSignalsChart
                candles={activeRun.candles || []}
                trades={activeRun.trades || []}
                params={activeRun.params}
                selectedTrade={selectedTrade}
                onSelectTrade={setSelectedTrade}
                onInspectInJournal={(trade) => {
                  setSelectedTrade(trade);
                  setLabSection('trades');
                }}
                lang={lang}
              />
            </div>
          )}

          {/* =================================================================
              SECTION 3: INTERACTIVE TRADE JOURNAL & TRADE INSPECTOR
             ================================================================= */}
          {labSection === 'trades' && activeRun && (
            <div className="space-y-4">
              <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <select
                    value={tradeSideFilter}
                    onChange={(e) => setTradeSideFilter(e.target.value as any)}
                    className="px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                  >
                    <option value="ALL">{tr(lang, 'Toutes Directions (BUY & SELL)', 'All Directions (BUY & SELL)')}</option>
                    <option value="BUY">{tr(lang, 'LONG (BUY) uniquement', 'LONG (BUY) only')}</option>
                    <option value="SELL">{tr(lang, 'SHORT (SELL) uniquement', 'SHORT (SELL) only')}</option>
                  </select>

                  <select
                    value={tradeOutcomeFilter}
                    onChange={(e) => setTradeOutcomeFilter(e.target.value as any)}
                    className="px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                  >
                    <option value="ALL">{tr(lang, 'Tous Résultats (Gains & Pertes)', 'All Outcomes (Wins & Losses)')}</option>
                    <option value="WIN">{tr(lang, 'Trades Gagnants uniquement', 'Winning Trades only')}</option>
                    <option value="LOSS">{tr(lang, 'Trades Perdants uniquement', 'Losing Trades only')}</option>
                  </select>

                  <select
                    value={tradeReasonFilter}
                    onChange={(e) => setTradeReasonFilter(e.target.value)}
                    className="px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                  >
                    <option value="ALL">{tr(lang, 'Tous Motifs de Sortie', 'All Exit Reasons')}</option>
                    <option value="TAKE_PROFIT">TAKE_PROFIT</option>
                    <option value="STOP_LOSS">STOP_LOSS</option>
                    <option value="TRAILING_SL">TRAILING_SL</option>
                    <option value="BREAKEVEN_SL">BREAKEVEN_SL</option>
                    <option value="OPPOSITE_SIGNAL">OPPOSITE_SIGNAL</option>
                    <option value="TIME_STOP">TIME_STOP</option>
                  </select>
                </div>

                <div className="text-xs font-mono-tabular text-[#94A3B8]">
                  {tr(lang, 'Affichés :', 'Showing:')} <strong className="text-[#F1F5F9]">{filteredTrades.length}</strong> /{' '}
                  {activeRun.trades?.length || 0} trades
                </div>
              </div>

              {/* Selected Trade Deep Inspector */}
              {selectedTrade && (
                <div className="bg-[#0B101B] border border-[#10B981]/40 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-mono-tabular font-bold ${
                          selectedTrade.side === 'BUY'
                            ? 'bg-[#10B981]/20 text-[#10B981]'
                            : 'bg-[#F43F5E]/20 text-[#FB7185]'
                        }`}
                      >
                        TRADE #{selectedTrade.id} • {selectedTrade.side}
                      </span>
                      <span className="text-xs font-mono-tabular text-[#94A3B8]">
                        Teddy Score : <strong className="text-[#F1F5F9]">{selectedTrade.teddy_score}/100</strong>
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelectedTrade(null)}
                      className="text-xs text-[#94A3B8] hover:text-[#F1F5F9]"
                    >
                      {tr(lang, "Fermer l'inspecteur ✕", 'Close inspector ✕')}
                    </button>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono-tabular">
                    <div className="p-2.5 rounded bg-[#111827]">
                      <div className="text-[10px] text-[#64748B]">{tr(lang, 'Entrée → Sortie', 'Entry → Exit')}</div>
                      <div className="text-[#F1F5F9] font-semibold">
                        {selectedTrade.entry_price} → {selectedTrade.exit_price}
                      </div>
                    </div>
                    <div className="p-2.5 rounded bg-[#111827]">
                      <div className="text-[10px] text-[#64748B]">{tr(lang, 'SL Initial / TP Initial', 'Initial SL / Initial TP')}</div>
                      <div className="text-[#F1F5F9]">
                        {selectedTrade.sl_initial} / {selectedTrade.tp_initial}
                      </div>
                    </div>
                    <div className="p-2.5 rounded bg-[#111827]">
                      <div className="text-[10px] text-[#64748B]">Excursion MFE / MAE</div>
                      <div>
                        <span className="text-[#10B981]">+{selectedTrade.mfe_pct}%</span> /{' '}
                        <span className="text-[#F43F5E]">{selectedTrade.mae_pct}%</span>
                      </div>
                    </div>
                    <div className="p-2.5 rounded bg-[#111827]">
                      <div className="text-[10px] text-[#64748B]">{tr(lang, 'Résultat Net (Multiple R)', 'Net Result (R Multiple)')}</div>
                      <div
                        className={`font-bold ${
                          selectedTrade.pnl_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                        }`}
                      >
                        {selectedTrade.pnl_usdt >= 0 ? '+' : ''}
                        {selectedTrade.pnl_usdt} USDT ({selectedTrade.r_multiple >= 0 ? '+' : ''}
                        {selectedTrade.r_multiple}R)
                      </div>
                    </div>
                  </div>

                  <div className="text-xs text-[#94A3B8]">
                    <strong>{tr(lang, "Règles déclenchées à l'entrée :", 'Entry rules triggered:')}</strong>{' '}
                    {selectedTrade.entry_reasons?.join(' • ') || tr(lang, 'Confluence validée', 'Validated confluence')}
                  </div>
                </div>
              )}

              {/* Trades Table */}
              <div className="bg-[#111827] border border-white/[0.08] rounded-xl overflow-hidden">
                <div className="overflow-x-auto max-h-[520px]">
                  <table className="w-full text-left border-collapse text-xs font-mono-tabular">
                    <thead>
                      <tr className="border-b border-white/[0.08] bg-[#090D16] text-[10px] uppercase text-[#64748B]">
                        <th className="py-2.5 px-3">#</th>
                        <th className="py-2.5 px-3">{tr(lang, 'Côté', 'Side')}</th>
                        <th className="py-2.5 px-3">{tr(lang, 'Date Entrée', 'Entry Time')}</th>
                        <th className="py-2.5 px-3">{tr(lang, 'Entrée / Sortie', 'Entry / Exit')}</th>
                        <th className="py-2.5 px-3">Score</th>
                        <th className="py-2.5 px-3">MFE / MAE</th>
                        <th className="py-2.5 px-3">{tr(lang, 'Sortie', 'Exit')}</th>
                        <th className="py-2.5 px-3 text-right">PnL (USDT)</th>
                        <th className="py-2.5 px-3 text-right">R</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05]">
                      {filteredTrades.map((t) => (
                        <tr
                          key={t.id}
                          onClick={() => setSelectedTrade(t)}
                          className="hover:bg-white/[0.03] cursor-pointer transition-colors"
                        >
                          <td className="py-2.5 px-3 text-[#64748B]">#{t.id}</td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                t.side === 'BUY'
                                  ? 'bg-[#10B981]/15 text-[#10B981]'
                                  : 'bg-[#F43F5E]/15 text-[#FB7185]'
                              }`}
                            >
                              {t.side}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-[#94A3B8]">
                            {String(t.entry_time).slice(0, 16).replace('T', ' ')}
                          </td>
                          <td className="py-2.5 px-3 text-[#F1F5F9]">
                            {t.entry_price} → {t.exit_price}
                          </td>
                          <td className="py-2.5 px-3 text-[#10B981]">{t.teddy_score}</td>
                          <td className="py-2.5 px-3">
                            <span className="text-[#10B981]">+{t.mfe_pct}%</span> /{' '}
                            <span className="text-[#F43F5E]">{t.mae_pct}%</span>
                          </td>
                          <td className="py-2.5 px-3">
                            <span className="px-1.5 py-0.5 rounded bg-white/[0.05] text-[#94A3B8] text-[10px]">
                              {t.exit_reason}
                            </span>
                          </td>
                          <td
                            className={`py-2.5 px-3 text-right font-bold ${
                              t.pnl_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                            }`}
                          >
                            {t.pnl_usdt >= 0 ? '+' : ''}
                            {t.pnl_usdt.toFixed(2)}
                          </td>
                          <td
                            className={`py-2.5 px-3 text-right ${
                              t.r_multiple >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                            }`}
                          >
                            {t.r_multiple >= 0 ? '+' : ''}
                            {t.r_multiple}R
                          </td>
                        </tr>
                      ))}
                      {filteredTrades.length === 0 && (
                        <tr>
                          <td colSpan={9} className="py-8 text-center text-[#64748B]">
                            {tr(lang, 'Aucun trade ne correspond aux filtres sélectionnés.', 'No trades match the selected filters.')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              SECTION 4: FILTER REJECTION DIAGNOSTICS ("WHY SIGNALS WERE BLOCKED")
             ================================================================= */}
          {labSection === 'diagnostics' && activeRun?.signals_summary && (
            <div className="space-y-6">
              <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-4">
                <h3 className="font-display text-sm font-semibold text-[#F1F5F9]">
                  {tr(lang, 'Entonnoir de Sélection & Causes de Rejet des Signaux', 'Signal Selection Funnel & Rejection Reasons')}
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  {tr(
                    lang,
                    `Permet d'identifier immédiatement quel filtre bloque le plus d'opportunités sur ${activeRun.signals_summary.total_candles_evaluated} bougies analysées.`,
                    `Immediately identifies which filter blocks the most opportunities across ${activeRun.signals_summary.total_candles_evaluated} evaluated candles.`
                  )}
                </p>

                <div className="space-y-2.5">
                  {Object.entries(activeRun.signals_summary.rejection_counts || {})
                    .sort((a, b) => b[1] - a[1])
                    .map(([key, count]) => {
                      const total = Math.max(1, activeRun.signals_summary!.total_candles_evaluated);
                      const pct = Math.min(100, (count / total) * 100);
                      const labelMap = lang === 'en' ? REJECTION_LABELS_EN : REJECTION_LABELS;
                      return (
                        <div key={key} className="space-y-1">
                          <div className="flex justify-between text-xs font-mono-tabular">
                            <span className="text-[#F1F5F9]">{labelMap[key] || key}</span>
                            <span className="text-[#94A3B8]">
                              {count} {tr(lang, 'bougies', 'candles')} ({pct.toFixed(1)}%)
                            </span>
                          </div>
                          <div className="w-full h-2 rounded-full bg-[#090D16] overflow-hidden">
                            <div
                              className="h-full bg-[#3B82F6] rounded-full"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>

              <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-3">
                <h4 className="font-display text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                  {tr(
                    lang,
                    'Échantillon des Signaux Proches du Seuil mais Filtrés (Near-Misses)',
                    'Sample of Near-Miss Signals Filtered Out'
                  )}
                </h4>
                <div className="overflow-x-auto max-h-80">
                  <table className="w-full text-left text-xs font-mono-tabular">
                    <thead>
                      <tr className="border-b border-white/[0.08] text-[10px] uppercase text-[#64748B]">
                        <th className="py-2 px-2">{tr(lang, 'Horodatage', 'Timestamp')}</th>
                        <th className="py-2 px-2">{tr(lang, 'Candidat', 'Candidate')}</th>
                        <th className="py-2 px-2">{tr(lang, 'Prix', 'Price')}</th>
                        <th className="py-2 px-2">Score</th>
                        <th className="py-2 px-2">{tr(lang, 'Raison exacte du blocage', 'Exact blocking reason')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05]">
                      {(activeRun.signals_summary.rejected_sample || []).map((s, idx) => (
                        <tr key={idx}>
                          <td className="py-2 px-2 text-[#94A3B8]">
                            {String(s.timestamp).slice(0, 16).replace('T', ' ')}
                          </td>
                          <td className="py-2 px-2">
                            <span
                              className={
                                s.candidate === 'BUY' ? 'text-[#10B981] font-bold' : 'text-[#FB7185] font-bold'
                              }
                            >
                              {s.candidate}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-[#F1F5F9]">{s.price}</td>
                          <td className="py-2 px-2 text-[#F59E0B]">{s.score}/100</td>
                          <td className="py-2 px-2 text-[#94A3B8]">{s.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              SECTION 5: SIDE-BY-SIDE A/B STRATEGY COMPARATOR
             ================================================================= */}
          {labSection === 'compare' && (
            <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="font-display text-sm font-semibold text-[#F1F5F9]">
                    {tr(
                      lang,
                      'Comparateur Quantitatif A / B (Référence vs Scénario Modifié)',
                      'Quantitative A / B Comparator (Baseline vs Modified Scenario)'
                    )}
                  </h3>
                  <p className="text-xs text-[#94A3B8]">
                    {tr(
                      lang,
                      "Comparez objectivement l'impact de vos modifications de paramètres sur la rentabilité et le risque.",
                      'Objectively compare the impact of your parameter modifications on profitability and risk.'
                    )}
                  </p>
                </div>
                {!compareRun && (
                  <button
                    type="button"
                    onClick={() => executeBacktest(baselineParams, true)}
                    disabled={runningCompare}
                    className="px-3.5 py-2 rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] text-xs font-semibold text-white"
                  >
                    {runningCompare
                      ? tr(lang, 'Calcul...', 'Computing...')
                      : tr(lang, 'Générer la Référence (A) Maintenant', 'Generate Baseline (A) Now')}
                  </button>
                )}
              </div>

              {compareRun && activeRun ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs font-mono-tabular">
                    <thead>
                      <tr className="border-b border-white/10 bg-[#090D16] text-[10px] uppercase text-[#64748B]">
                        <th className="py-3 px-4">{tr(lang, 'Métrique', 'Metric')}</th>
                        <th className="py-3 px-4 text-[#60A5FA]">
                          {tr(lang, 'Stratégie A (Référence', 'Strategy A (Baseline')} • Score≥{compareRun.params.min_teddy_score})
                        </th>
                        <th className="py-3 px-4 text-[#10B981]">
                          {tr(lang, 'Stratégie B (Actuelle', 'Strategy B (Current')} • Score≥{activeRun.params.min_teddy_score})
                        </th>
                        <th className="py-3 px-4 text-right">Delta (B vs A)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.06]">
                      {[
                        {
                          label: tr(lang, 'Rendement Net (%)', 'Net Return (%)'),
                          a: compareRun.metrics.total_return_pct,
                          b: activeRun.metrics.total_return_pct,
                          suffix: '%',
                          higherIsBetter: true,
                        },
                        {
                          label: tr(lang, 'Profit Net (USDT)', 'Net Profit (USDT)'),
                          a: compareRun.metrics.net_profit_usdt,
                          b: activeRun.metrics.net_profit_usdt,
                          suffix: ' USDT',
                          higherIsBetter: true,
                        },
                        {
                          label: 'Win Rate (%)',
                          a: compareRun.metrics.win_rate_pct,
                          b: activeRun.metrics.win_rate_pct,
                          suffix: '%',
                          higherIsBetter: true,
                        },
                        {
                          label: 'Profit Factor',
                          a: compareRun.metrics.profit_factor,
                          b: activeRun.metrics.profit_factor,
                          suffix: '',
                          higherIsBetter: true,
                        },
                        {
                          label: tr(lang, 'Drawdown Max (%)', 'Max Drawdown (%)'),
                          a: compareRun.metrics.max_drawdown_pct,
                          b: activeRun.metrics.max_drawdown_pct,
                          suffix: '%',
                          higherIsBetter: false,
                        },
                        {
                          label: tr(lang, 'Ratio de Sharpe', 'Sharpe Ratio'),
                          a: compareRun.metrics.sharpe_ratio,
                          b: activeRun.metrics.sharpe_ratio,
                          suffix: '',
                          higherIsBetter: true,
                        },
                        {
                          label: tr(lang, 'Espérance par Trade ($)', 'Expectancy per Trade ($)'),
                          a: compareRun.metrics.expectancy_usdt,
                          b: activeRun.metrics.expectancy_usdt,
                          suffix: '$',
                          higherIsBetter: true,
                        },
                        {
                          label: tr(lang, 'Nombre de Trades', 'Total Trades'),
                          a: compareRun.metrics.total_trades,
                          b: activeRun.metrics.total_trades,
                          suffix: '',
                          higherIsBetter: true,
                        },
                      ].map((row) => {
                        const diff = Number((row.b - row.a).toFixed(2));
                        const improved = row.higherIsBetter ? diff > 0 : diff < 0;
                        return (
                          <tr key={row.label}>
                            <td className="py-2.5 px-4 text-[#94A3B8]">{row.label}</td>
                            <td className="py-2.5 px-4 text-[#F1F5F9]">
                              {row.a}
                              {row.suffix}
                            </td>
                            <td className="py-2.5 px-4 font-bold text-[#F1F5F9]">
                              {row.b}
                              {row.suffix}
                            </td>
                            <td
                              className={`py-2.5 px-4 text-right font-bold ${
                                diff === 0
                                  ? 'text-[#64748B]'
                                  : improved
                                  ? 'text-[#10B981]'
                                  : 'text-[#F43F5E]'
                              }`}
                            >
                              {diff > 0 ? '+' : ''}
                              {diff}
                              {row.suffix}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-8 text-center text-xs text-[#64748B] border border-dashed border-white/10 rounded-xl">
                  {tr(
                    lang,
                    "Cliquez sur « Épingler la Référence Actuelle pour Comparaison A/B » ou sélectionnez une expérience dans l'historique pour comparer deux stratégies côte à côte.",
                    'Click "Pin Current Baseline for A/B Comparison" or select an experiment in History to compare two strategies side by side.'
                  )}
                </div>
              )}
            </div>
          )}

          {/* =================================================================
              SECTION 6: CONTROLLED PARAMETER SENSITIVITY SWEEP (GRID TEST)
             ================================================================= */}
          {labSection === 'sweep' && (
            <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-4">
              <div>
                <h3 className="font-display text-sm font-semibold text-[#F1F5F9]">
                  {tr(lang, 'Balayage de Sensibilité (Grid Sweep Contrôlé)', 'Sensitivity Sweep (Controlled Grid Test)')}
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  {tr(
                    lang,
                    "Testez automatiquement plusieurs valeurs d'un paramètre clé sur le même historique pour vérifier la robustesse de la stratégie sans suroptimisation aveugle.",
                    'Automatically test multiple values of a key parameter on the exact same historical data to verify strategy robustness without blind overfitting.'
                  )}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                <div>
                  <label className="block text-[11px] text-[#94A3B8] mb-1">
                    {tr(lang, 'Paramètre à Faire Varier', 'Parameter to Sweep')}
                  </label>
                  <select
                    value={sweepParamName}
                    onChange={(e) => {
                      const val = e.target.value;
                      setSweepParamName(val);
                      if (val === 'min_teddy_score') setSweepValuesInput('48, 54, 58, 62, 68, 74');
                      if (val === 'sl_atr_mult') setSweepValuesInput('1.0, 1.3, 1.5, 1.8, 2.2, 2.6');
                      if (val === 'min_rr_ratio') setSweepValuesInput('1.2, 1.5, 1.8, 2.2, 2.6, 3.0');
                      if (val === 'adx_min') setSweepValuesInput('14, 18, 20, 24, 28, 32');
                    }}
                    className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                  >
                    <option value="min_teddy_score">{tr(lang, 'Score Teddy Minimum', 'Minimum Teddy Score')}</option>
                    <option value="sl_atr_mult">{tr(lang, 'Multiplicateur Stop Loss (ATR)', 'Stop Loss Multiplier (ATR)')}</option>
                    <option value="min_rr_ratio">{tr(lang, 'Ratio Risque/Rendement (R:R)', 'Risk/Reward Ratio (R:R)')}</option>
                    <option value="adx_min">{tr(lang, 'Seuil ADX Minimum', 'Minimum ADX Threshold')}</option>
                    <option value="rsi_oversold">{tr(lang, 'Seuil RSI Survente', 'RSI Oversold Threshold')}</option>
                    <option value="cooldown_candles">{tr(lang, 'Cooldown (Bougies)', 'Cooldown (Candles)')}</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] text-[#94A3B8] mb-1">
                    {tr(lang, 'Valeurs à Tester (max 8, séparées par virgule)', 'Values to Test (max 8, comma-separated)')}
                  </label>
                  <input
                    type="text"
                    value={sweepValuesInput}
                    onChange={(e) => setSweepValuesInput(e.target.value)}
                    className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs font-mono-tabular text-[#F1F5F9]"
                  />
                </div>

                <button
                  type="button"
                  onClick={handleRunSweep}
                  disabled={runningSweep}
                  className="py-2 px-4 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-[#090D16] font-semibold text-xs flex items-center justify-center gap-2"
                >
                  <Sparkles className="w-4 h-4" />
                  <span>{runningSweep ? tr(lang, 'Balayage en cours...', 'Sweeping...') : tr(lang, 'Lancer le Balayage', 'Run Sweep')}</span>
                </button>
              </div>

              {sweepResult && (
                <div className="space-y-4 pt-2">
                  {sweepResult.best && (
                    <div className="p-3 rounded-lg bg-[#10B981]/10 border border-[#10B981]/30 text-xs flex items-center justify-between">
                      <div>
                        <strong className="text-[#10B981]">
                          {tr(lang, 'Meilleure variante identifiée :', 'Best variant identified:')}
                        </strong>{' '}
                        {sweepResult.param_label} ={' '}
                        <strong className="font-mono-tabular text-[#F1F5F9]">
                          {sweepResult.best.param_value}
                        </strong>{' '}
                        ({tr(lang, 'Rendement :', 'Return:')} {sweepResult.best.total_return_pct >= 0 ? '+' : ''}
                        {sweepResult.best.total_return_pct}% | Profit Factor :{' '}
                        {sweepResult.best.profit_factor} | Drawdown : -{sweepResult.best.max_drawdown_pct}%)
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          handleParamChange(
                            sweepResult.param_name as keyof StrategyLabParams,
                            sweepResult.best.param_value
                          );
                          onShowToast(
                            'success',
                            tr(
                              lang,
                              `Valeur ${sweepResult.best.param_value} appliquée dans l'éditeur.`,
                              `Value ${sweepResult.best.param_value} applied in editor.`
                            )
                          );
                        }}
                        className="px-3 py-1 rounded bg-[#10B981] text-[#090D16] font-semibold text-[11px]"
                      >
                        {tr(lang, 'Appliquer cette valeur', 'Apply value')}
                      </button>
                    </div>
                  )}

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs font-mono-tabular">
                      <thead>
                        <tr className="border-b border-white/10 bg-[#090D16] text-[10px] uppercase text-[#64748B]">
                          <th className="py-2.5 px-3">{sweepResult.param_label}</th>
                          <th className="py-2.5 px-3">Trades</th>
                          <th className="py-2.5 px-3">Win Rate</th>
                          <th className="py-2.5 px-3">Profit Factor</th>
                          <th className="py-2.5 px-3">{tr(lang, 'Drawdown Max', 'Max Drawdown')}</th>
                          <th className="py-2.5 px-3">Sharpe</th>
                          <th className="py-2.5 px-3 text-right">{tr(lang, 'Rendement Net', 'Net Return')}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.05]">
                        {sweepResult.results.map((r: any, idx: number) => (
                          <tr key={idx} className="hover:bg-white/[0.03]">
                            <td className="py-2 px-3 font-bold text-[#F1F5F9]">{r.param_value}</td>
                            <td className="py-2 px-3 text-[#94A3B8]">{r.total_trades}</td>
                            <td className="py-2 px-3 text-[#F1F5F9]">{r.win_rate_pct}%</td>
                            <td className="py-2 px-3 text-[#F1F5F9]">{r.profit_factor}</td>
                            <td className="py-2 px-3 text-[#F43F5E]">-{r.max_drawdown_pct}%</td>
                            <td className="py-2 px-3 text-[#60A5FA]">{r.sharpe_ratio}</td>
                            <td
                              className={`py-2 px-3 text-right font-bold ${
                                r.total_return_pct >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'
                              }`}
                            >
                              {r.total_return_pct >= 0 ? '+' : ''}
                              {r.total_return_pct}% ({r.net_profit_usdt >= 0 ? '+' : ''}
                              {r.net_profit_usdt}$)
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* =================================================================
              SECTION 7: SAVED EXPERIMENTS HISTORY & NOTES
             ================================================================= */}
          {labSection === 'history' && (
            <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-display text-sm font-semibold text-[#F1F5F9]">
                    {tr(lang, 'Historique des Expériences Sauvegardées', 'Saved Experiments History')} ({savedRuns.length})
                  </h3>
                  <p className="text-xs text-[#94A3B8]">
                    {tr(
                      lang,
                      'Rechargez une simulation passée ou épinglez-la comme référence A/B.',
                      'Reload a past simulation or pin it as an A/B baseline.'
                    )}
                  </p>
                </div>
              </div>

              <div className="space-y-2.5 max-h-[540px] overflow-y-auto">
                {savedRuns.map((run) => (
                  <div
                    key={run.id}
                    className="p-3.5 rounded-xl bg-[#090D16] border border-white/[0.07] hover:border-white/15 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-[#F1F5F9]">
                          #{run.id} • {run.name}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono-tabular bg-white/[0.05] text-[#94A3B8]">
                          {run.symbol} {run.timeframe}
                        </span>
                      </div>
                      <div className="text-[11px] font-mono-tabular text-[#64748B] flex flex-wrap gap-3">
                        <span>
                          {tr(lang, 'Rendement :', 'Return:')}{' '}
                          <strong
                            className={
                              (run.metrics?.total_return_pct || 0) >= 0
                                ? 'text-[#10B981]'
                                : 'text-[#F43F5E]'
                            }
                          >
                            {(run.metrics?.total_return_pct || 0) >= 0 ? '+' : ''}
                            {run.metrics?.total_return_pct}%
                          </strong>
                        </span>
                        <span>WR : {run.metrics?.win_rate_pct}%</span>
                        <span>PF : {run.metrics?.profit_factor}</span>
                        <span>DD : -{run.metrics?.max_drawdown_pct}%</span>
                        <span>Trades : {run.metrics?.total_trades}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleLoadSavedRun(run, false)}
                        className="px-2.5 py-1.5 rounded bg-[#1E293B] hover:bg-[#334155] text-[11px] text-[#F1F5F9] flex items-center gap-1"
                      >
                        <Eye className="w-3 h-3 text-[#10B981]" />
                        <span>{tr(lang, 'Charger', 'Load')}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleLoadSavedRun(run, true)}
                        className="px-2.5 py-1.5 rounded bg-[#1E293B] hover:bg-[#334155] text-[11px] text-[#60A5FA] flex items-center gap-1"
                      >
                        <GitCompare className="w-3 h-3" />
                        <span>{tr(lang, 'Comparer (A)', 'Compare (A)')}</span>
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          const res = await apiFetch('/api/admin/strategy-lab/run-meta', {
                            method: 'POST',
                            body: JSON.stringify({ action: 'delete', run_id: run.id }),
                          });
                          if (res.runs) setSavedRuns(res.runs);
                        }}
                        className="p-1.5 rounded bg-[#F43F5E]/10 hover:bg-[#F43F5E]/20 text-[#FB7185]"
                        title={tr(lang, 'Supprimer cette expérience', 'Delete this experiment')}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
                {savedRuns.length === 0 && (
                  <div className="py-8 text-center text-xs text-[#64748B]">
                    {tr(lang, 'Aucune expérience enregistrée pour le moment.', 'No saved experiments yet.')}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modal: Save Preset */}
      {showSavePresetModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-white/15 rounded-2xl max-w-md w-full p-6 space-y-4">
            <h3 className="font-display text-base font-bold text-[#F1F5F9]">
              {tr(lang, 'Sauvegarder la Configuration dans les Presets Bitsure', 'Save Configuration to Bitsure Presets')}
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-[#94A3B8] mb-1">{tr(lang, 'Nom du Preset', 'Preset Name')}</label>
                <input
                  type="text"
                  placeholder={tr(lang, 'Ex: BTC 15m Haute Confluence v2', 'e.g. BTC 15m High Confluence v2')}
                  value={presetNameInput}
                  onChange={(e) => setPresetNameInput(e.target.value)}
                  className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                />
              </div>
              <div>
                <label className="block text-xs text-[#94A3B8] mb-1">
                  {tr(lang, 'Notes / Hypothèse de recherche', 'Research Notes / Hypothesis')}
                </label>
                <textarea
                  rows={3}
                  placeholder={tr(
                    lang,
                    "Décrivez les règles modifiées et l'objectif de ce preset...",
                    'Describe the modified rules and objective of this preset...'
                  )}
                  value={presetDescInput}
                  onChange={(e) => setPresetDescInput(e.target.value)}
                  className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                />
              </div>
              <div>
                <label className="block text-xs text-[#94A3B8] mb-1">Tags</label>
                <input
                  type="text"
                  value={presetTagsInput}
                  onChange={(e) => setPresetTagsInput(e.target.value)}
                  className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs font-mono-tabular text-[#F1F5F9]"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowSavePresetModal(false)}
                className="px-4 py-2 rounded-lg bg-[#1E293B] text-xs text-[#94A3B8]"
              >
                {tr(lang, 'Annuler', 'Cancel')}
              </button>
              <button
                type="button"
                onClick={handleSavePreset}
                className="px-4 py-2 rounded-lg bg-[#10B981] text-[#090D16] font-semibold text-xs"
              >
                {tr(lang, 'Enregistrer', 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
