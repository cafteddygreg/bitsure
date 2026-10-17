import React, { useEffect, useRef, useState } from 'react';
import { GLOSSARY, GlossaryKey } from './glossary';

/** Primitives du design system Bitsure (styles : classes `bs-*` dans src/index.css). */

const cx = (...parts: Array<string | false | null | undefined>): string => parts.filter(Boolean).join(' ');

export type Tone = 'neutral' | 'positive' | 'negative' | 'warning' | 'info';

/* ---------- Panel ---------- */
interface PanelProps {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}
export const Panel: React.FC<PanelProps> = ({ title, actions, className, bodyClassName, children }) => (
  <section className={cx('bs-panel', className)}>
    {(title || actions) && (
      <div className="bs-panel-head">
        <h3 className="bs-panel-title">{title}</h3>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    )}
    <div className={cx('bs-panel-body', bodyClassName)}>{children}</div>
  </section>
);

/* ---------- PageHeader : où suis-je / que fait cet outil / que puis-je faire ---------- */
interface PageHeaderProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  status?: React.ReactNode;
  actions?: React.ReactNode;
}
export const PageHeader: React.FC<PageHeaderProps> = ({ icon, title, description, status, actions }) => (
  <header className="bs-page-head">
    <div className="min-w-0">
      <h1 className="bs-page-title">
        {icon}
        <span className="truncate">{title}</span>
        {status}
      </h1>
      {description && <p className="bs-page-desc">{description}</p>}
    </div>
    {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
  </header>
);

/* ---------- Button ---------- */
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'danger' | 'ghost';
  loading?: boolean;
}
export const Button: React.FC<ButtonProps> = ({ variant = 'default', loading, disabled, className, children, ...rest }) => (
  <button
    type="button"
    {...rest}
    disabled={disabled || loading}
    aria-busy={loading || undefined}
    className={cx(
      'bs-btn',
      variant === 'primary' && 'bs-btn-primary',
      variant === 'danger' && 'bs-btn-danger',
      variant === 'ghost' && 'bs-btn-ghost',
      className
    )}
  >
    {children}
  </button>
);

/* ---------- StatusBadge : texte explicite, jamais la couleur seule ---------- */
interface StatusBadgeProps {
  tone?: Tone;
  dot?: boolean;
  children: React.ReactNode;
  className?: string;
}
export const StatusBadge: React.FC<StatusBadgeProps> = ({ tone = 'neutral', dot, children, className }) => (
  <span className={cx('bs-badge', tone !== 'neutral' && `bs-badge-${tone}`, className)}>
    {dot && <span className={cx('bs-dot', tone !== 'neutral' && `bs-dot-${tone}`)} aria-hidden="true" />}
    {children}
  </span>
);

/* ---------- InfoTip : ⓘ cliquable, définition issue du glossaire ---------- */
interface InfoTipProps {
  term: GlossaryKey;
  lang?: string;
}
export const InfoTip: React.FC<InfoTipProps> = ({ term, lang }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const entry = GLOSSARY[term];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!entry) return null;
  return (
    <span ref={ref} className="relative inline-flex">
      <button
        type="button"
        className="bs-info-btn"
        aria-expanded={open}
        aria-label={`${lang === 'en' ? 'Definition' : 'Définition'} : ${entry.term}`}
        onClick={() => setOpen((v) => !v)}
      >
        i
      </button>
      {open && (
        <span role="tooltip" className="bs-info-pop">
          <strong>{entry.term}</strong>
          {lang === 'en' ? entry.en : entry.fr}
        </span>
      )}
    </span>
  );
};

/* ---------- MetricRow : libellé + valeur tabulaire alignée ---------- */
interface MetricRowProps {
  label: string;
  value: React.ReactNode;
  tone?: 'neutral' | 'positive' | 'negative';
  info?: GlossaryKey;
  lang?: string;
}
export const MetricRow: React.FC<MetricRowProps> = ({ label, value, tone = 'neutral', info, lang }) => (
  <div className="bs-metric-row">
    <span className="bs-metric-label">
      {label}
      {info && <InfoTip term={info} lang={lang} />}
    </span>
    <span className={cx('bs-metric-value', tone === 'positive' && 'bs-pos', tone === 'negative' && 'bs-neg')}>{value}</span>
  </div>
);

/* ---------- Skeleton / EmptyState ---------- */
export const Skeleton: React.FC<{ className?: string }> = ({ className }) => (
  <div className={cx('bs-skeleton', className || 'h-4 w-full')} aria-hidden="true" />
);

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}
export const EmptyState: React.FC<EmptyStateProps> = ({ title, description, action }) => (
  <div className="bs-empty" role="status">
    <span className="bs-empty-title">{title}</span>
    {description && <span>{description}</span>}
    {action}
  </div>
);

/* ---------- Sparkline : SVG minimal, uniquement à partir de valeurs réelles fournies ---------- */
interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  tone?: 'positive' | 'negative' | 'neutral';
  label?: string;
}
export const Sparkline: React.FC<SparklineProps> = ({ values, width = 64, height = 20, tone = 'neutral', label }) => {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(height - 1 - ((v - min) / span) * (height - 2)).toFixed(1)}`).join(' ');
  const color = tone === 'positive' ? '#32D583' : tone === 'negative' ? '#F04438' : '#8B98A4';
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label || 'sparkline'} className="shrink-0">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.25" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
};

export { GLOSSARY };
export type { GlossaryKey };
