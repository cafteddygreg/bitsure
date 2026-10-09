import React, { useState, useMemo } from 'react';
import { CandlePoint } from '../types';
import { AppLang, tr } from '../i18n';

interface PriceChartProps {
  candles: CandlePoint[];
  symbol: string;
  timeframe: string;
  livePrice?: number | null;
  sl?: number | null;
  tp1?: number | null;
  tp2?: number | null;
  support?: number | null;
  resistance?: number | null;
  lang?: AppLang;
}

export const PriceChart: React.FC<PriceChartProps> = ({
  candles,
  symbol,
  timeframe,
  livePrice,
  sl,
  tp1,
  tp2,
  support,
  resistance,
  lang = 'fr',
}) => {
  const [showSMA, setShowSMA] = useState(true);
  const [showBB, setShowBB] = useState(true);
  const [showLevels, setShowLevels] = useState(true);
  const [subChart, setSubChart] = useState<'rsi' | 'macd'>('rsi');
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const visibleCandles = useMemo(() => {
    const base = candles.slice(-75);
    if (!base.length || !livePrice || livePrice <= 0) return base;
    const copy = [...base];
    const last = { ...copy[copy.length - 1] };
    last.close = livePrice;
    if (last.high === null || livePrice > last.high) last.high = livePrice;
    if (last.low === null || livePrice < last.low) last.low = livePrice;
    copy[copy.length - 1] = last;
    return copy;
  }, [candles, livePrice]);

  if (!visibleCandles.length) {
    return (
      <div className="h-[380px] flex items-center justify-center bg-[#090D16] border border-white/[0.07] rounded-lg text-[#64748B] text-sm">
        {tr(lang, 'Chargement des bougies OHLCV...', 'Loading OHLCV candles...')}
      </div>
    );
  }

  const width = 920;
  const mainHeight = 270;
  const subHeight = 95;
  const padLeft = 14;
  const padRight = 76;
  const padTop = 16;
  const padBottom = 18;
  const plotW = width - padLeft - padRight;
  const plotH = mainHeight - padTop - padBottom;

  const prices: number[] = [];
  visibleCandles.forEach((c) => {
    if (c.high !== null) prices.push(c.high);
    if (c.low !== null) prices.push(c.low);
    if (showBB && c.bb_upper !== null) prices.push(c.bb_upper);
    if (showBB && c.bb_lower !== null) prices.push(c.bb_lower);
  });
  if (showLevels) {
    if (sl) prices.push(sl);
    if (tp1) prices.push(tp1);
    if (support) prices.push(support);
    if (resistance) prices.push(resistance);
  }

  const minPrice = Math.min(...prices) * 0.9992;
  const maxPrice = Math.max(...prices) * 1.0008;
  const priceRange = Math.max(maxPrice - minPrice, 0.0001);

  const yForPrice = (p: number) => {
    const ratio = (p - minPrice) / priceRange;
    return padTop + plotH - ratio * plotH;
  };

  const stepX = plotW / Math.max(visibleCandles.length, 1);
  const xForIdx = (i: number) => padLeft + i * stepX + stepX / 2;

  const buildPolyline = (getter: (c: CandlePoint) => number | null) => {
    const pts: string[] = [];
    visibleCandles.forEach((c, idx) => {
      const val = getter(c);
      if (val !== null && val !== undefined) {
        pts.push(`${xForIdx(idx).toFixed(1)},${yForPrice(val).toFixed(1)}`);
      }
    });
    return pts.join(' ');
  };

  const sma20Points = showSMA ? buildPolyline((c) => c.sma20) : '';
  const sma50Points = showSMA ? buildPolyline((c) => c.sma50) : '';
  const bbUpPoints = showBB ? buildPolyline((c) => c.bb_upper) : '';
  const bbLowPoints = showBB ? buildPolyline((c) => c.bb_lower) : '';

  const activeCandle = hoverIdx !== null && visibleCandles[hoverIdx] ? visibleCandles[hoverIdx] : visibleCandles[visibleCandles.length - 1];

  const formatNum = (val: number | null | undefined) => {
    if (val === null || val === undefined) return '—';
    return val >= 100 ? val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : val.toFixed(4);
  };

  return (
    <div className="bg-[#0B101B] border border-white/[0.08] rounded-lg overflow-hidden">
      {/* Top Chart Controls & OHLCV Telemetry Bar */}
      <div className="px-4 py-2.5 border-b border-white/[0.07] flex flex-wrap items-center justify-between gap-3 bg-[#111827]/70">
        <div className="flex items-center gap-4 text-xs font-mono-tabular">
          <span className="font-semibold text-[#F1F5F9] tracking-tight">{symbol} • {timeframe.toUpperCase()}</span>
          <span className="text-[#94A3B8]">O <strong className="text-[#F1F5F9]">{formatNum(activeCandle?.open)}</strong></span>
          <span className="text-[#94A3B8]">H <strong className="text-[#10B981]">{formatNum(activeCandle?.high)}</strong></span>
          <span className="text-[#94A3B8]">L <strong className="text-[#F43F5E]">{formatNum(activeCandle?.low)}</strong></span>
          <span className="text-[#94A3B8]">C <strong className="text-[#F1F5F9]">{formatNum(activeCandle?.close)}</strong></span>
          {activeCandle?.rsi !== null && (
            <span className="text-[#94A3B8] hidden sm:inline">RSI(14) <strong className="text-[#F59E0B]">{activeCandle?.rsi?.toFixed(1)}</strong></span>
          )}
        </div>

        <div className="flex items-center gap-1.5 text-xs">
          <button
            onClick={() => setShowSMA(!showSMA)}
            className={`px-2 py-1 rounded border transition-colors ${
              showSMA ? 'bg-[#3B82F6]/15 border-[#3B82F6]/40 text-[#60A5FA]' : 'border-white/10 text-[#64748B]'
            }`}
          >
            SMA 20/50
          </button>
          <button
            onClick={() => setShowBB(!showBB)}
            className={`px-2 py-1 rounded border transition-colors ${
              showBB ? 'bg-[#8B5CF6]/15 border-[#8B5CF6]/40 text-[#A78BFA]' : 'border-white/10 text-[#64748B]'
            }`}
          >
            Bollinger
          </button>
          <button
            onClick={() => setShowLevels(!showLevels)}
            className={`px-2 py-1 rounded border transition-colors ${
              showLevels ? 'bg-[#10B981]/15 border-[#10B981]/40 text-[#34D399]' : 'border-white/10 text-[#64748B]'
            }`}
          >
            SL / TP / S-R
          </button>
          <div className="h-3.5 w-[1px] bg-white/10 mx-1" />
          <button
            onClick={() => setSubChart(subChart === 'rsi' ? 'macd' : 'rsi')}
            className="px-2 py-1 rounded border border-white/15 bg-white/[0.04] text-[#F1F5F9] hover:bg-white/[0.08] transition-colors font-mono-tabular"
          >
            Osc: {subChart.toUpperCase()}
          </button>
        </div>
      </div>

      {/* Main SVG Candlestick + Overlays Canvas */}
      <div className="relative select-none">
        <svg
          viewBox={`0 0 ${width} ${mainHeight + subHeight}`}
          className="w-full h-auto block"
          onMouseLeave={() => setHoverIdx(null)}
        >
          {/* Horizontal Price Grid Lines */}
          {[0.15, 0.38, 0.62, 0.85].map((ratio, idx) => {
            const p = maxPrice - ratio * priceRange;
            const y = yForPrice(p);
            return (
              <g key={idx}>
                <line x1={padLeft} y1={y} x2={width - padRight} y2={y} stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
                <text x={width - padRight + 6} y={y + 3} fill="#64748B" fontSize="10" fontFamily="JetBrains Mono, monospace">
                  {formatNum(p)}
                </text>
              </g>
            );
          })}

          {/* Support / Resistance / SL / TP Horizontal Lines */}
          {showLevels && support && support >= minPrice && support <= maxPrice && (
            <g>
              <line x1={padLeft} y1={yForPrice(support)} x2={width - padRight} y2={yForPrice(support)} stroke="#3B82F6" strokeWidth="1" strokeDasharray="4 4" opacity="0.7" />
              <text x={padLeft + 6} y={yForPrice(support) - 4} fill="#60A5FA" fontSize="9.5" fontFamily="JetBrains Mono, monospace">SUP {formatNum(support)}</text>
            </g>
          )}
          {showLevels && resistance && resistance >= minPrice && resistance <= maxPrice && (
            <g>
              <line x1={padLeft} y1={yForPrice(resistance)} x2={width - padRight} y2={yForPrice(resistance)} stroke="#F59E0B" strokeWidth="1" strokeDasharray="4 4" opacity="0.7" />
              <text x={padLeft + 6} y={yForPrice(resistance) - 4} fill="#FBBF24" fontSize="9.5" fontFamily="JetBrains Mono, monospace">RES {formatNum(resistance)}</text>
            </g>
          )}
          {showLevels && sl && sl >= minPrice && sl <= maxPrice && (
            <g>
              <line x1={padLeft} y1={yForPrice(sl)} x2={width - padRight} y2={yForPrice(sl)} stroke="#F43F5E" strokeWidth="1.2" strokeDasharray="2 2" />
              <text x={width - padRight - 72} y={yForPrice(sl) - 4} fill="#FB7185" fontSize="9.5" fontFamily="JetBrains Mono, monospace">SL {formatNum(sl)}</text>
            </g>
          )}
          {showLevels && tp1 && tp1 >= minPrice && tp1 <= maxPrice && (
            <g>
              <line x1={padLeft} y1={yForPrice(tp1)} x2={width - padRight} y2={yForPrice(tp1)} stroke="#10B981" strokeWidth="1.2" strokeDasharray="2 2" />
              <text x={width - padRight - 72} y={yForPrice(tp1) - 4} fill="#34D399" fontSize="9.5" fontFamily="JetBrains Mono, monospace">TP1 {formatNum(tp1)}</text>
            </g>
          )}
          {livePrice && livePrice >= minPrice && livePrice <= maxPrice && (
            <g>
              <line
                x1={padLeft}
                y1={yForPrice(livePrice)}
                x2={width - padRight}
                y2={yForPrice(livePrice)}
                stroke="#10B981"
                strokeWidth="1"
                strokeDasharray="2 2"
                opacity="0.85"
              />
              <rect
                x={width - padRight + 2}
                y={yForPrice(livePrice) - 8}
                width={padRight - 4}
                height={16}
                rx="3"
                fill="#10B981"
              />
              <text
                x={width - padRight + 6}
                y={yForPrice(livePrice) + 3.5}
                fill="#090D16"
                fontSize="9.5"
                fontWeight="bold"
                fontFamily="JetBrains Mono, monospace"
              >
                {formatNum(livePrice)}
              </text>
            </g>
          )}

          {/* Bollinger Bands */}
          {showBB && bbUpPoints && (
            <polyline fill="none" stroke="rgba(139, 92, 246, 0.45)" strokeWidth="1" points={bbUpPoints} />
          )}
          {showBB && bbLowPoints && (
            <polyline fill="none" stroke="rgba(139, 92, 246, 0.45)" strokeWidth="1" points={bbLowPoints} />
          )}

          {/* SMA 20 & SMA 50 */}
          {showSMA && sma20Points && (
            <polyline fill="none" stroke="#38BDF8" strokeWidth="1.5" points={sma20Points} />
          )}
          {showSMA && sma50Points && (
            <polyline fill="none" stroke="#F59E0B" strokeWidth="1.5" points={sma50Points} />
          )}

          {/* Candlesticks */}
          {visibleCandles.map((c, idx) => {
            if (c.open === null || c.close === null || c.high === null || c.low === null) return null;
            const x = xForIdx(idx);
            const isBull = c.close >= c.open;
            const color = isBull ? '#10B981' : '#F43F5E';
            const yHigh = yForPrice(c.high);
            const yLow = yForPrice(c.low);
            const yOpen = yForPrice(c.open);
            const yClose = yForPrice(c.close);
            const bodyTop = Math.min(yOpen, yClose);
            const bodyH = Math.max(Math.abs(yClose - yOpen), 1.5);
            const candleW = Math.max(stepX * 0.62, 2.5);

            return (
              <g key={idx} onMouseEnter={() => setHoverIdx(idx)} className="cursor-crosshair">
                <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth="1" />
                <rect
                  x={x - candleW / 2}
                  y={bodyTop}
                  width={candleW}
                  height={bodyH}
                  fill={color}
                  rx="0.5"
                />
                <rect
                  x={x - stepX / 2}
                  y={padTop}
                  width={stepX}
                  height={mainHeight + subHeight}
                  fill="transparent"
                />
              </g>
            );
          })}

          {/* Divider between Main Chart and Sub-Oscillator */}
          <line x1={0} y1={mainHeight} x2={width} y2={mainHeight} stroke="rgba(255,255,255,0.08)" />

          {/* Sub-Chart: RSI(14) or MACD(12,26,9) */}
          {subChart === 'rsi' ? (
            <g transform={`translate(0, ${mainHeight})`}>
              {/* RSI 30 / 70 Reference Band */}
              <rect
                x={padLeft}
                y={10 + (1 - 0.7) * (subHeight - 20)}
                width={plotW}
                height={(0.7 - 0.3) * (subHeight - 20)}
                fill="rgba(59, 130, 246, 0.04)"
              />
              <line
                x1={padLeft}
                y1={10 + (1 - 0.7) * (subHeight - 20)}
                x2={width - padRight}
                y2={10 + (1 - 0.7) * (subHeight - 20)}
                stroke="rgba(244, 63, 94, 0.35)"
                strokeDasharray="2 2"
              />
              <line
                x1={padLeft}
                y1={10 + (1 - 0.3) * (subHeight - 20)}
                x2={width - padRight}
                y2={10 + (1 - 0.3) * (subHeight - 20)}
                stroke="rgba(16, 185, 129, 0.35)"
                strokeDasharray="2 2"
              />
              <text x={width - padRight + 6} y={10 + (1 - 0.7) * (subHeight - 20) + 3} fill="#64748B" fontSize="9" fontFamily="JetBrains Mono">70</text>
              <text x={width - padRight + 6} y={10 + (1 - 0.3) * (subHeight - 20) + 3} fill="#64748B" fontSize="9" fontFamily="JetBrains Mono">30</text>
              <polyline
                fill="none"
                stroke="#F59E0B"
                strokeWidth="1.5"
                points={visibleCandles
                  .map((c, idx) => {
                    if (c.rsi === null) return null;
                    const ry = 10 + (1 - Math.min(100, Math.max(0, c.rsi)) / 100) * (subHeight - 20);
                    return `${xForIdx(idx).toFixed(1)},${ry.toFixed(1)}`;
                  })
                  .filter(Boolean)
                  .join(' ')}
              />
            </g>
          ) : (
            <g transform={`translate(0, ${mainHeight})`}>
              {(() => {
                const macdVals = visibleCandles
                  .flatMap((c) => [c.macd, c.macd_signal, c.macd_hist])
                  .filter((v): v is number => v !== null && v !== undefined);
                const maxAbs = Math.max(...macdVals.map((v) => Math.abs(v)), 0.0001);
                const zeroY = subHeight / 2;
                const yM = (v: number) => zeroY - (v / maxAbs) * ((subHeight - 24) / 2);

                return (
                  <>
                    <line x1={padLeft} y1={zeroY} x2={width - padRight} y2={zeroY} stroke="rgba(255,255,255,0.1)" />
                    {visibleCandles.map((c, idx) => {
                      if (c.macd_hist === null) return null;
                      const x = xForIdx(idx);
                      const yVal = yM(c.macd_hist);
                      const h = Math.max(Math.abs(yVal - zeroY), 1);
                      return (
                        <rect
                          key={idx}
                          x={x - Math.max(stepX * 0.45, 2) / 2}
                          y={Math.min(zeroY, yVal)}
                          width={Math.max(stepX * 0.45, 2)}
                          height={h}
                          fill={c.macd_hist >= 0 ? 'rgba(16, 185, 129, 0.55)' : 'rgba(244, 63, 94, 0.55)'}
                        />
                      );
                    })}
                    <polyline
                      fill="none"
                      stroke="#38BDF8"
                      strokeWidth="1.3"
                      points={visibleCandles
                        .map((c, idx) => (c.macd !== null ? `${xForIdx(idx).toFixed(1)},${yM(c.macd).toFixed(1)}` : null))
                        .filter(Boolean)
                        .join(' ')}
                    />
                    <polyline
                      fill="none"
                      stroke="#F59E0B"
                      strokeWidth="1.3"
                      points={visibleCandles
                        .map((c, idx) => (c.macd_signal !== null ? `${xForIdx(idx).toFixed(1)},${yM(c.macd_signal).toFixed(1)}` : null))
                        .filter(Boolean)
                        .join(' ')}
                    />
                  </>
                );
              })()}
            </g>
          )}
        </svg>
      </div>
    </div>
  );
};
