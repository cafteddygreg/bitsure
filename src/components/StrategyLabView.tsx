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
import {
  StrategyLabParams,
  StrategyLabPreset,
  StrategyLabRun,
  StrategyLabTrade,
} from '../types';

const EquityAndDrawdownChart: React.FC<{
  data: NonNullable<StrategyLabRun['equity_curve']>;
  initialCapital: number;
}> = ({ data, initialCapital }) => {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (!data || data.length < 2) {
    return (
      <div className="h-64 flex items-center justify-center text-xs text-[#64748B]">
        Données d&apos;équité insuffisantes.
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
          Équité : <strong className="text-[#10B981]">{activePoint.equity.toLocaleString()} USDT</strong>
        </span>
        <span className="text-[#94A3B8]">
          Drawdown : <strong className="text-[#F43F5E]">{activePoint.drawdown_pct.toFixed(2)}%</strong>
        </span>
        <span className="text-[#94A3B8]">
          Prix Actif : <strong className="text-[#F1F5F9]">{activePoint.price.toLocaleString()} USDT</strong>
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
  params: StrategyLabParams;
}> = ({ candles, params }) => {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (!candles || candles.length < 2) {
    return (
      <div className="h-80 flex items-center justify-center text-xs text-[#64748B]">
        Aucune bougie disponible.
      </div>
    );
  }

  const width = 920;
  const height = 360;
  const padL = 12;
  const padR = 68;
  const padT = 16;
  const padB = 22;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const prices: number[] = [];
  candles.forEach((c) => {
    prices.push(c.high, c.low, c.ema_fast, c.ema_slow);
  });
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const pRange = Math.max(0.0001, maxP - minP);

  const getX = (i: number) => padL + (i / Math.max(1, candles.length - 1)) * plotW;
  const getY = (val: number) => padT + plotH - ((val - minP) / pRange) * plotH;

  const closeLine = candles.map((c, i) => `${getX(i).toFixed(1)},${getY(c.close).toFixed(1)}`).join(' ');
  const emaFastLine = candles.map((c, i) => `${getX(i).toFixed(1)},${getY(c.ema_fast).toFixed(1)}`).join(' ');
  const emaSlowLine = candles.map((c, i) => `${getX(i).toFixed(1)},${getY(c.ema_slow).toFixed(1)}`).join(' ');
  const emaTrendLine = candles.map((c, i) => `${getX(i).toFixed(1)},${getY(c.ema_trend).toFixed(1)}`).join(' ');

  const activeC = hoverIdx !== null && candles[hoverIdx] ? candles[hoverIdx] : candles[candles.length - 1];

  return (
    <div className="space-y-2 select-none">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono-tabular px-3 py-2 rounded bg-[#090D16] border border-white/[0.06]">
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
        {activeC.marker && (
          <span
            className={`px-2 py-0.5 rounded font-bold ${
              activeC.marker.side === 'BUY'
                ? 'bg-[#10B981]/20 text-[#10B981]'
                : 'bg-[#F43F5E]/20 text-[#FB7185]'
            }`}
          >
            {activeC.marker.type} {activeC.marker.side} @ {activeC.marker.price}
          </span>
        )}
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-80 bg-[#090D16]/80 rounded-lg border border-white/[0.06]"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const relX = ((e.clientX - rect.left) / rect.width) * width;
          const idx = Math.round(((relX - padL) / plotW) * (candles.length - 1));
          if (idx >= 0 && idx < candles.length) setHoverIdx(idx);
        }}
        onMouseLeave={() => setHoverIdx(null)}
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

        <polyline fill="none" stroke="#F59E0B" strokeWidth="1.2" strokeDasharray="4 4" points={emaTrendLine} />
        <polyline fill="none" stroke="#3B82F6" strokeWidth="1.3" points={emaSlowLine} />
        <polyline fill="none" stroke="#10B981" strokeWidth="1.3" points={emaFastLine} />
        <polyline fill="none" stroke="#F1F5F9" strokeWidth="1.6" points={closeLine} />

        {/* Entry & Exit Signal Markers */}
        {candles.map((c, i) => {
          if (!c.marker) return null;
          const cx = getX(i);
          const cy = getY(c.close);
          const isBuy = c.marker.side === 'BUY';
          const isEntry = c.marker.type === 'ENTRY';
          const color = isBuy ? '#10B981' : '#F43F5E';
          return (
            <g key={i}>
              <circle
                cx={cx}
                cy={cy}
                r={isEntry ? 5.5 : 4}
                fill={isEntry ? color : '#090D16'}
                stroke={color}
                strokeWidth={2}
              />
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

interface StrategyLabViewProps {
  onShowToast: (type: 'success' | 'error' | 'info', text: string) => void;
}

export const StrategyLabView: React.FC<StrategyLabViewProps> = ({ onShowToast }) => {
  // Available markets, presets & saved runs
  const [symbols, setSymbols] = useState<string[]>([
    'BTCUSDT',
    'ETHUSDT',
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

  const loadLabOverview = useCallback(async () => {
    try {
      const res = await apiFetch('/api/admin/strategy-lab/overview');
      if (res.symbols) setSymbols(res.symbols);
      if (res.timeframes) setTimeframes(res.timeframes);
      if (res.presets) {
        setPresets(res.presets);
        if (res.presets.length > 0 && !activeRun) {
          const firstPreset = res.presets[0];
          setParams({ ...DEFAULT_PARAMS, ...firstPreset.params });
          setBaselineParams({ ...DEFAULT_PARAMS, ...firstPreset.params });
        }
      }
      if (res.runs) setSavedRuns(res.runs);
    } catch (err: any) {
      onShowToast('error', err.message || 'Erreur lors du chargement du Strategy Lab.');
    }
  }, [activeRun, onShowToast]);

  const executeBacktest = useCallback(
    async (customParams?: StrategyLabParams, isBaselineCompare = false) => {
      const targetParams = customParams || params;
      if (isBaselineCompare) {
        setRunningCompare(true);
      } else {
        setRunningBacktest(true);
      }
      try {
        const res = await apiFetch('/api/admin/strategy-lab/backtest', {
          method: 'POST',
          body: JSON.stringify({
            symbol,
            timeframe,
            trading_style: tradingStyle,
            start_date: startDate || undefined,
            end_date: endDate || undefined,
            max_candles: maxCandles,
            params: targetParams,
            save_run: !isBaselineCompare,
            name: isBaselineCompare
              ? `Référence ${symbol} ${timeframe}`
              : `${symbol} ${timeframe} (${tradingStyle.toUpperCase()}) • Score≥${targetParams.min_teddy_score} • SL ${targetParams.sl_atr_mult}xATR`,
          }),
        });
        if (isBaselineCompare) {
          setCompareRun(res.run);
          onShowToast('info', 'Scénario de référence (A) calculé pour comparaison A/B.');
        } else {
          setActiveRun(res.run);
          if (res.runs) setSavedRuns(res.runs);
          setSelectedTrade(null);
          onShowToast(
            'success',
            `Simulation terminée en ${res.run.execution_ms || 0} ms (${res.run.metrics.total_trades} trades sur ${res.run.candles_count} bougies).`
          );
        }
      } catch (err: any) {
        onShowToast('error', err.message || 'Échec du backtest.');
      } finally {
        setRunningBacktest(false);
        setRunningCompare(false);
      }
    },
    [symbol, timeframe, tradingStyle, startDate, endDate, maxCandles, params, onShowToast]
  );

  // Run initial backtest on mount so the Lab is immediately populated with real data
  useEffect(() => {
    loadLabOverview();
    executeBacktest(DEFAULT_PARAMS, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleParamChange = <K extends keyof StrategyLabParams>(key: K, value: StrategyLabParams[K]) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  };

  const applyPreset = (preset: StrategyLabPreset) => {
    const merged = { ...DEFAULT_PARAMS, ...preset.params };
    setParams(merged);
    setBaselineParams(merged);
    if (preset.timeframe) setTimeframe(preset.timeframe);
    if (preset.trading_style) setTradingStyle(preset.trading_style);
    onShowToast('info', `Preset « ${preset.name} » chargé. Cliquez sur Lancer le Backtest pour évaluer.`);
  };

  const handleSavePreset = async () => {
    if (!presetNameInput.trim()) {
      onShowToast('error', 'Veuillez saisir un nom pour la stratégie.');
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
      onShowToast('success', 'Stratégie sauvegardée dans les Presets Bitsure.');
    } catch (err: any) {
      onShowToast('error', err.message || 'Erreur lors de la sauvegarde.');
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
          onShowToast('info', `Expérience #${runSummary.id} chargée comme Référence (A).`);
        } else {
          setActiveRun(res.run);
          setParams({ ...DEFAULT_PARAMS, ...res.run.params });
          setSymbol(res.run.symbol);
          setTimeframe(res.run.timeframe);
          setTradingStyle(res.run.trading_style);
          onShowToast('success', `Expérience #${runSummary.id} restaurée dans l'espace de travail.`);
        }
      }
    } catch (err: any) {
      onShowToast('error', err.message || 'Impossible de charger les détails de cette expérience.');
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
        onShowToast('error', 'Indiquez au moins 2 valeurs numériques séparées par des virgules.');
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
      onShowToast('success', `Balayage de sensibilité terminé (${res.sweep.results.length} variantes testées).`);
    } catch (err: any) {
      onShowToast('error', err.message || 'Erreur lors du balayage de paramètres.');
    } finally {
      setRunningSweep(false);
    }
  };

  const exportTradesCsv = () => {
    if (!activeRun?.trades || activeRun.trades.length === 0) {
      onShowToast('info', 'Aucun trade à exporter.');
      return;
    }
    const headers = [
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
              ADMINISTRATION EXCLUSIVE • STRATEGY LAB
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-[10px] font-mono-tabular font-semibold bg-[#3B82F6]/15 text-[#60A5FA] border border-[#3B82F6]/30">
              <ShieldCheck className="w-3.5 h-3.5" />
              100% ISOLÉ DU TRADING RÉEL (ZÉRO ORDRE LIVE)
            </span>
            {activeRun && (
              <span className="text-[11px] font-mono-tabular text-[#64748B]">
                Source : <strong className="text-[#94A3B8]">{activeRun.data_source}</strong> ({activeRun.candles_count} bougies)
              </span>
            )}
          </div>
          <h1 className="font-display text-xl sm:text-2xl font-bold text-[#F1F5F9]">
            Laboratoire Quantitatif &amp; Backtesting Interactif Bitsure
          </h1>
          <p className="text-xs text-[#94A3B8]">
            Testez, modifiez, comparez (A/B) et diagnostiquez les règles du moteur de signaux Bitsure sur données historiques réelles sans aucun risque d&apos;exécution.
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            type="button"
            onClick={() => setShowSavePresetModal(true)}
            className="px-3.5 py-2 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-xs font-medium text-[#F1F5F9] flex items-center gap-1.5 transition-colors"
          >
            <Save className="w-3.5 h-3.5 text-[#10B981]" />
            <span>Sauvegarder Preset</span>
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
            <span>Rapport JSON</span>
          </button>
          <button
            type="button"
            onClick={() => executeBacktest(params, false)}
            disabled={runningBacktest}
            className="px-5 py-2.5 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-[#090D16] font-semibold text-xs flex items-center gap-2 shadow-lg shadow-[#10B981]/10 transition-all"
          >
            <Play className={`w-4 h-4 fill-current ${runningBacktest ? 'animate-pulse' : ''}`} />
            <span>{runningBacktest ? 'Simulation en cours...' : 'Lancer le Backtest'}</span>
          </button>
        </div>
      </div>

      {/* =====================================================================
          MARKET, TIMEFRAME, PERIOD & PRESET SELECTOR STRIP
         ===================================================================== */}
      <div className="bg-[#111827] border border-white/[0.07] rounded-xl p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3 items-end">
        <div>
          <label className="block text-[11px] font-mono-tabular uppercase text-[#64748B] mb-1">
            Paire Crypto (Binance)
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
            Unité de Temps (Timeframe)
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
            Style de Stratégie
          </label>
          <select
            value={tradingStyle}
            onChange={(e) => setTradingStyle(e.target.value)}
            className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
          >
            <option value="scalp">Scalping Réactif</option>
            <option value="day">Day Trading Officiel</option>
            <option value="swing">Swing Institutionnel</option>
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-mono-tabular uppercase text-[#64748B] mb-1">
            Profondeur (Bougies)
          </label>
          <select
            value={maxCandles}
            onChange={(e) => setMaxCandles(Number(e.target.value))}
            className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs font-mono-tabular text-[#F1F5F9]"
          >
            <option value={300}>300 bougies (Court terme)</option>
            <option value={600}>600 bougies (Standard)</option>
            <option value={1000}>1 000 bougies (Étendu)</option>
            <option value={1500}>1 500 bougies (Cycle profond)</option>
            <option value={2000}>2 000 bougies (Stress-test)</option>
          </select>
        </div>

        <div className="xl:col-span-2">
          <label className="block text-[11px] font-mono-tabular uppercase text-[#64748B] mb-1">
            Charger un Preset Officiel ou Sauvegardé
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
                Sélectionner une configuration pré-enregistrée...
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
                onShowToast('info', 'Paramètres réinitialisés à la valeur de référence.');
              }}
              title="Réinitialiser les paramètres modifiés"
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
        {/* LEFT COLUMN: INTERACTIVE STRATEGY PARAMETER EDITOR */}
        <div className="lg:col-span-4 bg-[#111827] border border-white/[0.08] rounded-xl overflow-hidden">
          <div className="p-4 border-b border-white/[0.07] flex items-center justify-between bg-[#0B101B]">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-[#10B981]" />
              <h2 className="font-display text-sm font-semibold text-[#F1F5F9]">
                Éditeur de Règles &amp; Paramètres
              </h2>
            </div>
            {modifiedParamsKeys.length > 0 ? (
              <span className="px-2 py-0.5 rounded text-[10px] font-mono-tabular bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30">
                {modifiedParamsKeys.length} modifié(s)
              </span>
            ) : (
              <span className="text-[10px] font-mono-tabular text-[#64748B]">Référence active</span>
            )}
          </div>

          {/* Parameter Category Tabs */}
          <div className="grid grid-cols-4 border-b border-white/[0.07] bg-[#090D16] text-[11px] font-medium">
            {[
              { id: 'confluence', label: 'Score & Filtres' },
              { id: 'exits', label: 'SL / TP / Trail' },
              { id: 'indicators', label: 'Indicateurs' },
              { id: 'capital', label: 'Capital & Frais' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setParamCategory(tab.id as any)}
                className={`py-2.5 px-2 text-center border-b-2 transition-colors ${
                  paramCategory === tab.id
                    ? 'border-[#10B981] text-[#10B981] bg-[#10B981]/5 font-semibold'
                    : 'border-transparent text-[#94A3B8] hover:text-[#F1F5F9]'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="p-4 space-y-4 max-h-[680px] overflow-y-auto">
            {/* CATEGORY 1: CONFLUENCE, TEDDY SCORE & FILTERS */}
            {paramCategory === 'confluence' && (
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[#94A3B8]">Score Teddy Minimum d&apos;Entrée</span>
                    <span className="font-mono-tabular font-bold text-[#10B981]">
                      {params.min_teddy_score} / 100
                    </span>
                  </div>
                  <input
                    type="range"
                    min={30}
                    max={88}
                    step={1}
                    value={params.min_teddy_score}
                    onChange={(e) => handleParamChange('min_teddy_score', Number(e.target.value))}
                    className="w-full accent-[#10B981]"
                  />
                  <div className="flex justify-between text-[10px] font-mono-tabular text-[#64748B]">
                    <span>30 (Agressif)</span>
                    <span>58 (Officiel)</span>
                    <span>85 (Ultra-Sélectif)</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  <label className="flex items-center justify-between p-2.5 rounded-lg bg-[#090D16] border border-white/10 text-xs cursor-pointer">
                    <span className="text-[#F1F5F9]">Autoriser LONG</span>
                    <input
                      type="checkbox"
                      checked={params.allow_long}
                      onChange={(e) => handleParamChange('allow_long', e.target.checked)}
                      className="accent-[#10B981]"
                    />
                  </label>
                  <label className="flex items-center justify-between p-2.5 rounded-lg bg-[#090D16] border border-white/10 text-xs cursor-pointer">
                    <span className="text-[#F1F5F9]">Autoriser SHORT</span>
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
                      label: 'Exiger alignement EMA rapide / lente',
                      desc: 'Bloque les achats sous EMA rapide et ventes au-dessus',
                    },
                    {
                      key: 'require_macd_confirmation' as const,
                      label: 'Exiger confirmation impulsion MACD',
                      desc: 'Filtre les entrées à contre-courant de l’histogramme MACD',
                    },
                    {
                      key: 'require_trend_filter_ema200' as const,
                      label: `Filtre directionnel strict EMA ${params.ema_trend}`,
                      desc: 'LONG uniquement au-dessus de EMA tendance, SHORT en-dessous',
                    },
                    {
                      key: 'block_against_strong_trend' as const,
                      label: 'Protection anti contre-tendance forte (ADX ≥ 30)',
                      desc: 'Interdit de shorter un rallye puissant ou d’acheter un krach',
                    },
                  ].map((item) => (
                    <label
                      key={item.key}
                      className="flex items-start justify-between gap-3 p-2.5 rounded-lg bg-[#090D16] border border-white/[0.07] hover:border-white/15 cursor-pointer transition-colors"
                    >
                      <div>
                        <div className="text-xs font-medium text-[#F1F5F9]">{item.label}</div>
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
                      Seuil ADX Min (Tendance)
                    </label>
                    <input
                      type="number"
                      step="1"
                      min={5}
                      max={50}
                      value={params.adx_min}
                      onChange={(e) => handleParamChange('adx_min', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Volatilité ATR Min (%)
                    </label>
                    <input
                      type="number"
                      step="0.02"
                      min={0}
                      max={3}
                      value={params.min_atr_pct}
                      onChange={(e) => handleParamChange('min_atr_pct', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Ratio Volume Min (vs MA)
                    </label>
                    <input
                      type="number"
                      step="0.05"
                      min={0}
                      max={3}
                      value={params.min_volume_ratio}
                      onChange={(e) => handleParamChange('min_volume_ratio', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Cooldown (Bougies)
                    </label>
                    <input
                      type="number"
                      step="1"
                      min={0}
                      max={30}
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
                    <label className="block text-[11px] text-[#94A3B8] mb-1">Mode Stop Loss</label>
                    <select
                      value={params.sl_mode}
                      onChange={(e) => handleParamChange('sl_mode', e.target.value as any)}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs text-[#F1F5F9]"
                    >
                      <option value="atr">Dynamique (Multiple ATR)</option>
                      <option value="fixed_pct">Pourcentage Fixe (%)</option>
                    </select>
                  </div>
                  {params.sl_mode === 'atr' ? (
                    <div>
                      <label className="block text-[11px] text-[#94A3B8] mb-1">
                        Multiplicateur SL (ATR)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        min={0.4}
                        max={8}
                        value={params.sl_atr_mult}
                        onChange={(e) => handleParamChange('sl_atr_mult', Number(e.target.value))}
                        className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                      />
                    </div>
                  ) : (
                    <div>
                      <label className="block text-[11px] text-[#94A3B8] mb-1">
                        Distance SL Fixe (%)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        min={0.2}
                        max={15}
                        value={params.sl_fixed_pct}
                        onChange={(e) => handleParamChange('sl_fixed_pct', Number(e.target.value))}
                        className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                      />
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">Mode Take Profit</label>
                    <select
                      value={params.tp_mode}
                      onChange={(e) => handleParamChange('tp_mode', e.target.value as any)}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs text-[#F1F5F9]"
                    >
                      <option value="rr">Multiple du Risque (R:R)</option>
                      <option value="atr">Multiple ATR</option>
                      <option value="fixed_pct">Pourcentage Fixe (%)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Ratio R:R Minimum Cible
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      min={0.8}
                      max={8}
                      value={params.min_rr_ratio}
                      onChange={(e) => handleParamChange('min_rr_ratio', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular text-[#F1F5F9]"
                    />
                  </div>
                </div>

                {/* Partial TP */}
                <div className="p-3 rounded-lg bg-[#090D16] border border-white/[0.07] space-y-2.5">
                  <label className="flex items-center justify-between text-xs font-medium text-[#F1F5F9] cursor-pointer">
                    <span>Take Profit Partiel (TP1 Automatique)</span>
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
                        <span className="block text-[10px] text-[#64748B]">Déclenchement (en R)</span>
                        <input
                          type="number"
                          step="0.1"
                          value={params.partial_tp_rr}
                          onChange={(e) => handleParamChange('partial_tp_rr', Number(e.target.value))}
                          className="w-full mt-0.5 px-2 py-1 bg-[#111827] border border-white/10 rounded text-xs font-mono-tabular"
                        />
                      </div>
                      <div>
                        <span className="block text-[10px] text-[#64748B]">Part clôturée (%)</span>
                        <input
                          type="number"
                          step="5"
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
                    <span>Mise à Break-Even Automatique</span>
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
                        Seuil d&apos;activation Break-Even (Multiple R)
                      </span>
                      <input
                        type="number"
                        step="0.1"
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
                    <span>Trailing Stop Dynamique (ATR)</span>
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
                        <span className="block text-[10px] text-[#64748B]">Activation (en R)</span>
                        <input
                          type="number"
                          step="0.1"
                          value={params.trailing_activation_rr}
                          onChange={(e) => handleParamChange('trailing_activation_rr', Number(e.target.value))}
                          className="w-full mt-0.5 px-2 py-1 bg-[#111827] border border-white/10 rounded text-xs font-mono-tabular"
                        />
                      </div>
                      <div>
                        <span className="block text-[10px] text-[#64748B]">Distance suivi (x ATR)</span>
                        <input
                          type="number"
                          step="0.1"
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
                    <span className="text-[#94A3B8]">Sortie signal opposé</span>
                    <input
                      type="checkbox"
                      checked={params.exit_on_opposite_signal}
                      onChange={(e) => handleParamChange('exit_on_opposite_signal', e.target.checked)}
                      className="accent-[#10B981]"
                    />
                  </label>
                  <div>
                    <label className="block text-[10px] text-[#64748B] mb-1">
                      Durée Max (Bougies)
                    </label>
                    <input
                      type="number"
                      min={4}
                      max={500}
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
                    <label className="block text-[10px] text-[#94A3B8] mb-1">EMA Rapide</label>
                    <input
                      type="number"
                      value={params.ema_fast}
                      onChange={(e) => handleParamChange('ema_fast', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-[#94A3B8] mb-1">EMA Lente</label>
                    <input
                      type="number"
                      value={params.ema_slow}
                      onChange={(e) => handleParamChange('ema_slow', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-[#94A3B8] mb-1">EMA Tendance</label>
                    <input
                      type="number"
                      value={params.ema_trend}
                      onChange={(e) => handleParamChange('ema_trend', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2.5">
                  <div>
                    <label className="block text-[10px] text-[#94A3B8] mb-1">Période RSI</label>
                    <input
                      type="number"
                      value={params.rsi_period}
                      onChange={(e) => handleParamChange('rsi_period', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-[#94A3B8] mb-1">RSI Survente</label>
                    <input
                      type="number"
                      value={params.rsi_oversold}
                      onChange={(e) => handleParamChange('rsi_oversold', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-[#94A3B8] mb-1">RSI Surachat</label>
                    <input
                      type="number"
                      value={params.rsi_overbought}
                      onChange={(e) => handleParamChange('rsi_overbought', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2.5">
                  <div>
                    <label className="block text-[10px] text-[#94A3B8] mb-1">Période ATR</label>
                    <input
                      type="number"
                      value={params.atr_period}
                      onChange={(e) => handleParamChange('atr_period', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-[#94A3B8] mb-1">Période ADX</label>
                    <input
                      type="number"
                      value={params.adx_period}
                      onChange={(e) => handleParamChange('adx_period', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-[#94A3B8] mb-1">MA Volume</label>
                    <input
                      type="number"
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
                      Capital Initial (USDT)
                    </label>
                    <input
                      type="number"
                      step="500"
                      value={params.initial_capital}
                      onChange={(e) => handleParamChange('initial_capital', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Levier Simulé (x)
                    </label>
                    <input
                      type="number"
                      step="1"
                      min={1}
                      max={25}
                      value={params.leverage}
                      onChange={(e) => handleParamChange('leverage', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] text-[#94A3B8] mb-1">
                    Mode de Dimensionnement (Position Sizing)
                  </label>
                  <select
                    value={params.position_sizing_mode}
                    onChange={(e) => handleParamChange('position_sizing_mode', e.target.value as any)}
                    className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs text-[#F1F5F9]"
                  >
                    <option value="risk_pct">Risque en % du Capital par Trade (basé sur distance SL)</option>
                    <option value="capital_pct">% Fixe du Capital Alloué</option>
                    <option value="fixed_usdt">Montant Fixe en USDT par Trade</option>
                  </select>
                </div>

                {params.position_sizing_mode === 'risk_pct' && (
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Risque par Trade (% du capital perdu si SL touché)
                    </label>
                    <input
                      type="number"
                      step="0.25"
                      min={0.1}
                      max={10}
                      value={params.risk_per_trade_pct}
                      onChange={(e) => handleParamChange('risk_per_trade_pct', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                )}

                {params.position_sizing_mode === 'capital_pct' && (
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Allocation Capital par Position (%)
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
                      Mise Fixe par Position (USDT)
                    </label>
                    <input
                      type="number"
                      step="100"
                      value={params.fixed_position_usdt}
                      onChange={(e) => handleParamChange('fixed_position_usdt', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Frais Taker (bps, 4 = 0.04%)
                    </label>
                    <input
                      type="number"
                      step="0.5"
                      min={0}
                      max={50}
                      value={params.fee_bps}
                      onChange={(e) => handleParamChange('fee_bps', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Slippage Estimé (bps)
                    </label>
                    <input
                      type="number"
                      step="0.5"
                      min={0}
                      max={50}
                      value={params.slippage_bps}
                      onChange={(e) => handleParamChange('slippage_bps', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Trades Max / Jour
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={params.max_trades_per_day}
                      onChange={(e) => handleParamChange('max_trades_per_day', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-[#94A3B8] mb-1">
                      Coupe-circuit Pertes Conséc.
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={params.max_consecutive_losses}
                      onChange={(e) => handleParamChange('max_consecutive_losses', Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded text-xs font-mono-tabular"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Action Buttons inside Parameter Editor */}
            <div className="pt-3 border-t border-white/[0.07] flex flex-col gap-2">
              <button
                type="button"
                onClick={() => executeBacktest(params, false)}
                disabled={runningBacktest}
                className="w-full py-2.5 rounded-lg bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-[#090D16] font-semibold text-xs flex items-center justify-center gap-2 transition-colors"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{runningBacktest ? 'Calcul en cours...' : 'Simuler ce Scénario (B)'}</span>
              </button>
              <button
                type="button"
                onClick={() => executeBacktest(baselineParams, true)}
                disabled={runningCompare}
                className="w-full py-2 rounded-lg bg-[#1E293B] hover:bg-[#334155] border border-white/10 text-xs text-[#F1F5F9] flex items-center justify-center gap-2 transition-colors"
              >
                <GitCompare className="w-3.5 h-3.5 text-[#60A5FA]" />
                <span>
                  {runningCompare
                    ? 'Calcul référence...'
                    : 'Épingler la Référence Actuelle pour Comparaison A/B'}
                </span>
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: ANALYTICS, CHARTS, DIAGNOSTICS, TRADES & SWEEP */}
        <div className="lg:col-span-8 space-y-6">
          {/* Sub-navigation tabs */}
          <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-1.5 flex flex-wrap gap-1">
            {[
              { id: 'overview', label: 'Synthèse & Courbe Equity', icon: TrendingUp },
              { id: 'chart', label: 'Graphique & Signaux', icon: Activity },
              {
                id: 'trades',
                label: `Journal des Trades (${activeRun?.trades?.length || 0})`,
                icon: Layers,
              },
              { id: 'diagnostics', label: 'Diagnostic des Filtres', icon: Filter },
              {
                id: 'compare',
                label: compareRun ? 'Comparateur A/B (Actif)' : 'Comparateur A/B',
                icon: GitCompare,
              },
              { id: 'sweep', label: 'Optimisation (Sweep)', icon: Sparkles },
              { id: 'history', label: `Historique (${savedRuns.length})`, icon: Bookmark },
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
                  Rendement Net
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
                  Drawdown Max
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
                  Espérance / Trade
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
                  Moy : {m.avg_r_multiple >= 0 ? '+' : ''}
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
                    <span>Diagnostic Automatique du Comportement de la Stratégie</span>
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
                      Courbe d&apos;Équité du Portefeuille &amp; Drawdown (USDT)
                    </h3>
                    <p className="text-xs text-[#64748B]">
                      Capital Initial : {m.initial_capital.toLocaleString()} USDT → Final :{' '}
                      <strong className="text-[#F1F5F9]">{m.final_capital.toLocaleString()} USDT</strong>{' '}
                      (Benchmark Buy &amp; Hold : {m.buy_hold_return_pct >= 0 ? '+' : ''}
                      {m.buy_hold_return_pct}% | Alpha : {m.alpha_vs_buy_hold_pct >= 0 ? '+' : ''}
                      {m.alpha_vs_buy_hold_pct}%)
                    </p>
                  </div>
                  <div className="text-xs font-mono-tabular text-[#94A3B8]">
                    Frais totaux déduits : <span className="text-[#F59E0B]">{m.total_fees_usdt.toFixed(2)} USDT</span>
                  </div>
                </div>

                <EquityAndDrawdownChart
                  data={activeRun.equity_curve || []}
                  initialCapital={m.initial_capital}
                />
              </div>

              {/* Detailed Institutional Breakdown Table */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-3">
                  <h4 className="font-display text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                    Statistiques Détaillées Long vs Short &amp; Séries
                  </h4>
                  <div className="space-y-2 text-xs font-mono-tabular">
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">Performance LONG ({m.long_trades} trades)</span>
                      <span className={m.long_pnl_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                        {m.long_pnl_usdt >= 0 ? '+' : ''}
                        {m.long_pnl_usdt.toFixed(2)} USDT ({m.long_win_rate_pct}% WR)
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">Performance SHORT ({m.short_trades} trades)</span>
                      <span className={m.short_pnl_usdt >= 0 ? 'text-[#10B981]' : 'text-[#F43F5E]'}>
                        {m.short_pnl_usdt >= 0 ? '+' : ''}
                        {m.short_pnl_usdt.toFixed(2)} USDT ({m.short_win_rate_pct}% WR)
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">Gain Moyen / Perte Moyenne</span>
                      <span className="text-[#F1F5F9]">
                        <strong className="text-[#10B981]">+{m.avg_win_usdt.toFixed(2)}$</strong> /{' '}
                        <strong className="text-[#F43F5E]">{m.avg_loss_usdt.toFixed(2)}$</strong>
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">Meilleur / Pire Trade</span>
                      <span className="text-[#F1F5F9]">
                        <strong className="text-[#10B981]">+{m.best_trade_usdt.toFixed(2)}$</strong> /{' '}
                        <strong className="text-[#F43F5E]">{m.worst_trade_usdt.toFixed(2)}$</strong>
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/[0.05]">
                      <span className="text-[#94A3B8]">Série Max Gains / Pertes consécutifs</span>
                      <span className="text-[#F1F5F9]">
                        {m.max_win_streak} W / {m.max_loss_streak} L
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-[#94A3B8]">Durée moyenne d&apos;exposition</span>
                      <span className="text-[#F1F5F9]">
                        {m.avg_bars_held} bougies (~{m.avg_duration_minutes} min)
                      </span>
                    </div>
                  </div>
                </div>

                <div className="bg-[#111827] border border-white/[0.08] rounded-xl p-5 space-y-3">
                  <h4 className="font-display text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                    Répartition des Sorties par Motif (Exit Breakdown)
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
                            ({stats.count} trades • {stats.wins} gagnants)
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
                      <div className="text-[#64748B] py-4 text-center">Aucune sortie enregistrée.</div>
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
                    Graphique Historique {activeRun.symbol} ({activeRun.timeframe}) &amp; Signaux Exécutés
                  </h3>
                  <p className="text-xs text-[#64748B]">
                    Superposition Prix Close, EMA Rapide ({activeRun.params.ema_fast}), EMA Lente ({activeRun.params.ema_slow}), EMA Tendance ({activeRun.params.ema_trend}) et marqueurs d&apos;entrée/sortie.
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
                params={activeRun.params}
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
                    <option value="ALL">Toutes Directions (BUY &amp; SELL)</option>
                    <option value="BUY">LONG (BUY) uniquement</option>
                    <option value="SELL">SHORT (SELL) uniquement</option>
                  </select>

                  <select
                    value={tradeOutcomeFilter}
                    onChange={(e) => setTradeOutcomeFilter(e.target.value as any)}
                    className="px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                  >
                    <option value="ALL">Tous Résultats (Gains &amp; Pertes)</option>
                    <option value="WIN">Trades Gagnants uniquement</option>
                    <option value="LOSS">Trades Perdants uniquement</option>
                  </select>

                  <select
                    value={tradeReasonFilter}
                    onChange={(e) => setTradeReasonFilter(e.target.value)}
                    className="px-2.5 py-1.5 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                  >
                    <option value="ALL">Tous Motifs de Sortie</option>
                    <option value="TAKE_PROFIT">TAKE_PROFIT</option>
                    <option value="STOP_LOSS">STOP_LOSS</option>
                    <option value="TRAILING_SL">TRAILING_SL</option>
                    <option value="BREAKEVEN_SL">BREAKEVEN_SL</option>
                    <option value="OPPOSITE_SIGNAL">OPPOSITE_SIGNAL</option>
                    <option value="TIME_STOP">TIME_STOP</option>
                  </select>
                </div>

                <div className="text-xs font-mono-tabular text-[#94A3B8]">
                  Affichés : <strong className="text-[#F1F5F9]">{filteredTrades.length}</strong> /{' '}
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
                      Fermer l&apos;inspecteur ✕
                    </button>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono-tabular">
                    <div className="p-2.5 rounded bg-[#111827]">
                      <div className="text-[10px] text-[#64748B]">Entrée → Sortie</div>
                      <div className="text-[#F1F5F9] font-semibold">
                        {selectedTrade.entry_price} → {selectedTrade.exit_price}
                      </div>
                    </div>
                    <div className="p-2.5 rounded bg-[#111827]">
                      <div className="text-[10px] text-[#64748B]">SL Initial / TP Initial</div>
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
                      <div className="text-[10px] text-[#64748B]">Résultat Net (Multiple R)</div>
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
                    <strong>Règles déclenchées à l&apos;entrée :</strong>{' '}
                    {selectedTrade.entry_reasons?.join(' • ') || 'Confluence validée'}
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
                        <th className="py-2.5 px-3">Côté</th>
                        <th className="py-2.5 px-3">Date Entrée</th>
                        <th className="py-2.5 px-3">Entrée / Sortie</th>
                        <th className="py-2.5 px-3">Score</th>
                        <th className="py-2.5 px-3">MFE / MAE</th>
                        <th className="py-2.5 px-3">Sortie</th>
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
                            Aucun trade ne correspond aux filtres sélectionnés.
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
                  Entonnoir de Sélection &amp; Causes de Rejet des Signaux
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  Permet d&apos;identifier immédiatement quel filtre bloque le plus d&apos;opportunités sur{' '}
                  {activeRun.signals_summary.total_candles_evaluated} bougies analysées.
                </p>

                <div className="space-y-2.5">
                  {Object.entries(activeRun.signals_summary.rejection_counts || {})
                    .sort((a, b) => b[1] - a[1])
                    .map(([key, count]) => {
                      const total = Math.max(1, activeRun.signals_summary!.total_candles_evaluated);
                      const pct = Math.min(100, (count / total) * 100);
                      return (
                        <div key={key} className="space-y-1">
                          <div className="flex justify-between text-xs font-mono-tabular">
                            <span className="text-[#F1F5F9]">{REJECTION_LABELS[key] || key}</span>
                            <span className="text-[#94A3B8]">
                              {count} bougies ({pct.toFixed(1)}%)
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
                  Échantillon des Signaux Proches du Seuil mais Filtrés (Near-Misses)
                </h4>
                <div className="overflow-x-auto max-h-80">
                  <table className="w-full text-left text-xs font-mono-tabular">
                    <thead>
                      <tr className="border-b border-white/[0.08] text-[10px] uppercase text-[#64748B]">
                        <th className="py-2 px-2">Horodatage</th>
                        <th className="py-2 px-2">Candidat</th>
                        <th className="py-2 px-2">Prix</th>
                        <th className="py-2 px-2">Score</th>
                        <th className="py-2 px-2">Raison exacte du blocage</th>
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
                    Comparateur Quantitatif A / B (Référence vs Scénario Modifié)
                  </h3>
                  <p className="text-xs text-[#94A3B8]">
                    Comparez objectivement l&apos;impact de vos modifications de paramètres sur la rentabilité et le risque.
                  </p>
                </div>
                {!compareRun && (
                  <button
                    type="button"
                    onClick={() => executeBacktest(baselineParams, true)}
                    disabled={runningCompare}
                    className="px-3.5 py-2 rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] text-xs font-semibold text-white"
                  >
                    {runningCompare ? 'Calcul...' : 'Générer la Référence (A) Maintenant'}
                  </button>
                )}
              </div>

              {compareRun && activeRun ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs font-mono-tabular">
                    <thead>
                      <tr className="border-b border-white/10 bg-[#090D16] text-[10px] uppercase text-[#64748B]">
                        <th className="py-3 px-4">Métrique</th>
                        <th className="py-3 px-4 text-[#60A5FA]">
                          Stratégie A (Référence • Score≥{compareRun.params.min_teddy_score})
                        </th>
                        <th className="py-3 px-4 text-[#10B981]">
                          Stratégie B (Actuelle • Score≥{activeRun.params.min_teddy_score})
                        </th>
                        <th className="py-3 px-4 text-right">Delta (B vs A)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.06]">
                      {[
                        {
                          label: 'Rendement Net (%)',
                          a: compareRun.metrics.total_return_pct,
                          b: activeRun.metrics.total_return_pct,
                          suffix: '%',
                          higherIsBetter: true,
                        },
                        {
                          label: 'Profit Net (USDT)',
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
                          label: 'Drawdown Max (%)',
                          a: compareRun.metrics.max_drawdown_pct,
                          b: activeRun.metrics.max_drawdown_pct,
                          suffix: '%',
                          higherIsBetter: false,
                        },
                        {
                          label: 'Ratio de Sharpe',
                          a: compareRun.metrics.sharpe_ratio,
                          b: activeRun.metrics.sharpe_ratio,
                          suffix: '',
                          higherIsBetter: true,
                        },
                        {
                          label: 'Espérance par Trade ($)',
                          a: compareRun.metrics.expectancy_usdt,
                          b: activeRun.metrics.expectancy_usdt,
                          suffix: '$',
                          higherIsBetter: true,
                        },
                        {
                          label: 'Nombre de Trades',
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
                  Cliquez sur « Épingler la Référence Actuelle pour Comparaison A/B » ou sélectionnez une expérience dans l&apos;historique pour comparer deux stratégies côte à côte.
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
                  Balayage de Sensibilité (Grid Sweep Contrôlé)
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  Testez automatiquement plusieurs valeurs d&apos;un paramètre clé sur le même historique pour vérifier la robustesse de la stratégie sans suroptimisation aveugle.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                <div>
                  <label className="block text-[11px] text-[#94A3B8] mb-1">
                    Paramètre à Faire Varier
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
                    <option value="min_teddy_score">Score Teddy Minimum</option>
                    <option value="sl_atr_mult">Multiplicateur Stop Loss (ATR)</option>
                    <option value="min_rr_ratio">Ratio Risque/Rendement (R:R)</option>
                    <option value="adx_min">Seuil ADX Minimum</option>
                    <option value="rsi_oversold">Seuil RSI Survente</option>
                    <option value="cooldown_candles">Cooldown (Bougies)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] text-[#94A3B8] mb-1">
                    Valeurs à Tester (max 8, séparées par virgule)
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
                  <span>{runningSweep ? 'Balayage en cours...' : 'Lancer le Balayage'}</span>
                </button>
              </div>

              {sweepResult && (
                <div className="space-y-4 pt-2">
                  {sweepResult.best && (
                    <div className="p-3 rounded-lg bg-[#10B981]/10 border border-[#10B981]/30 text-xs flex items-center justify-between">
                      <div>
                        <strong className="text-[#10B981]">Meilleure variante identifiée :</strong>{' '}
                        {sweepResult.param_label} ={' '}
                        <strong className="font-mono-tabular text-[#F1F5F9]">
                          {sweepResult.best.param_value}
                        </strong>{' '}
                        (Rendement : {sweepResult.best.total_return_pct >= 0 ? '+' : ''}
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
                            `Valeur ${sweepResult.best.param_value} appliquée dans l'éditeur.`
                          );
                        }}
                        className="px-3 py-1 rounded bg-[#10B981] text-[#090D16] font-semibold text-[11px]"
                      >
                        Appliquer cette valeur
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
                          <th className="py-2.5 px-3">Drawdown Max</th>
                          <th className="py-2.5 px-3">Sharpe</th>
                          <th className="py-2.5 px-3 text-right">Rendement Net</th>
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
                    Historique des Expériences Sauvegardées ({savedRuns.length})
                  </h3>
                  <p className="text-xs text-[#94A3B8]">
                    Rechargez une simulation passée ou épinglez-la comme référence A/B.
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
                          Rendement :{' '}
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
                        <span>Charger</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleLoadSavedRun(run, true)}
                        className="px-2.5 py-1.5 rounded bg-[#1E293B] hover:bg-[#334155] text-[11px] text-[#60A5FA] flex items-center gap-1"
                      >
                        <GitCompare className="w-3 h-3" />
                        <span>Comparer (A)</span>
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
                        title="Supprimer cette expérience"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
                {savedRuns.length === 0 && (
                  <div className="py-8 text-center text-xs text-[#64748B]">
                    Aucune expérience enregistrée pour le moment.
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
              Sauvegarder la Configuration dans les Presets Bitsure
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-[#94A3B8] mb-1">Nom du Preset</label>
                <input
                  type="text"
                  placeholder="Ex: BTC 15m Haute Confluence v2"
                  value={presetNameInput}
                  onChange={(e) => setPresetNameInput(e.target.value)}
                  className="w-full px-3 py-2 bg-[#090D16] border border-white/15 rounded-lg text-xs text-[#F1F5F9]"
                />
              </div>
              <div>
                <label className="block text-xs text-[#94A3B8] mb-1">Notes / Hypothèse de recherche</label>
                <textarea
                  rows={3}
                  placeholder="Décrivez les règles modifiées et l'objectif de ce preset..."
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
                Annuler
              </button>
              <button
                type="button"
                onClick={handleSavePreset}
                className="px-4 py-2 rounded-lg bg-[#10B981] text-[#090D16] font-semibold text-xs"
              >
                Enregistrer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
