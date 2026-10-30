import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react';
import { apiFetch } from '../api';
import { tr } from '../i18n';

interface AuditCheck {
  id: string;
  category: string;
  status: 'pass' | 'fail' | 'warn' | 'info' | 'skip';
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  title_fr: string;
  title_en: string;
  detail_fr?: string;
  detail_en?: string;
  fix_fr?: string;
  fix_en?: string;
}

interface AuditReport {
  finished_at: number;
  duration_s: number;
  overall: 'ok' | 'attention' | 'degraded' | 'critical';
  counts: Record<string, number>;
  passed: number;
  total: number;
  checks: AuditCheck[];
  disclaimer_fr: string;
  disclaimer_en: string;
  actions?: { auto_lock?: { users: number; findings: string[] } };
}

interface AuditState {
  enabled: boolean;
  running: boolean;
  progress: { step: number; total: number; label_fr: string; label_en: string } | null;
  last: AuditReport | null;
  history: Array<{ finished_at: number; overall: AuditReport['overall'] }>;
  interval_hours: number;
  auto_lock: boolean;
}

const CATEGORY_LABELS: Record<string, [string, string]> = {
  services: ['Services', 'Services'],
  configuration: ['Configuration', 'Configuration'],
  headers: ['En-têtes HTTP et CORS', 'HTTP headers and CORS'],
  routes: ['Protection des routes', 'Route protection'],
  binance_keys: ['Clés Binance des utilisateurs', "Users' Binance keys"],
  code: ['Code et dépendances', 'Code and dependencies'],
  audit: ['Audit', 'Audit'],
};

const SEVERITY_STYLE: Record<string, string> = {
  critical: 'bg-[#F04438]/15 text-[#F04438] border-[#F04438]/40',
  high: 'bg-[#F79009]/15 text-[#F79009] border-[#F79009]/40',
  medium: 'bg-[#D6A84F]/15 text-[#D6A84F] border-[#D6A84F]/40',
  low: 'bg-[#8B98A4]/15 text-[#8B98A4] border-[#8B98A4]/40',
  info: 'bg-[#8B98A4]/10 text-[#8B98A4] border-white/10',
};
const SEVERITY_LABEL: Record<string, [string, string]> = {
  critical: ['Critique', 'Critical'],
  high: ['Élevée', 'High'],
  medium: ['Moyenne', 'Medium'],
  low: ['Faible', 'Low'],
  info: ['Info', 'Info'],
};
const OVERALL: Record<string, { fr: string; en: string; color: string }> = {
  ok: { fr: 'Contrôles réussis', en: 'Checks passed', color: 'text-[#20C997]' },
  attention: { fr: 'Points d’attention', en: 'Points of attention', color: 'text-[#D6A84F]' },
  degraded: { fr: 'Service dégradé', en: 'Degraded', color: 'text-[#F79009]' },
  critical: { fr: 'Problème critique', en: 'Critical issue', color: 'text-[#F04438]' },
};

export const SecurityAuditPanel: React.FC<{ lang: string; onToast: (text: string, type?: 'success' | 'error' | 'info') => void }> = ({
  lang,
  onToast,
}) => {
  const [state, setState] = useState<AuditState | null>(null);
  const [showPassed, setShowPassed] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const wasRunning = useRef(false);

  const load = useCallback(async () => {
    try {
      const res = await apiFetch('/api/admin/security-audit');
      setState(res as AuditState);
      setLoadError(null);
    } catch (err: any) {
      setLoadError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Rafraîchissement rapide pendant un audit, lent sinon.
  useEffect(() => {
    const timer = setInterval(load, state?.running ? 2000 : 30000);
    return () => clearInterval(timer);
  }, [load, state?.running]);

  useEffect(() => {
    if (wasRunning.current && state && !state.running && state.last) {
      onToast(tr(lang, 'Audit de sécurité terminé.', 'Security audit finished.'), 'success');
    }
    wasRunning.current = Boolean(state?.running);
  }, [state?.running]); // eslint-disable-line react-hooks/exhaustive-deps

  const runNow = async () => {
    try {
      const res = await apiFetch('/api/admin/security-audit/run', { method: 'POST', body: JSON.stringify({}) });
      onToast(res.message || '', res.started ? 'info' : 'info');
      await load();
    } catch (err: any) {
      onToast(err.message, 'error');
    }
  };

  const report = state?.last || null;
  const overall = report ? OVERALL[report.overall] : null;
  const grouped: Record<string, AuditCheck[]> = {};
  (report?.checks || [])
    .filter((c) => showPassed || (c.status !== 'pass' && c.status !== 'skip'))
    .forEach((c) => (grouped[c.category] = [...(grouped[c.category] || []), c]));
  const severityRank = ['critical', 'high', 'medium', 'low', 'info'];
  Object.values(grouped).forEach((list) => list.sort((a, b) => severityRank.indexOf(a.severity) - severityRank.indexOf(b.severity)));

  return (
    <div className="bg-[#0D1318] border border-white/[0.08] rounded-xl p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {report?.overall === 'ok' ? (
            <ShieldCheck className="w-6 h-6 text-[#20C997] shrink-0" />
          ) : report ? (
            <ShieldAlert className={`w-6 h-6 shrink-0 ${overall?.color}`} />
          ) : (
            <ShieldQuestion className="w-6 h-6 text-[#8B98A4] shrink-0" />
          )}
          <div>
            <h3 className="font-display font-semibold text-[#E8EEF2]">
              {tr(lang, 'Santé & sécurité des services (admin)', 'Service health & security (admin)')}
            </h3>
            <p className="text-[11px] text-[#8B98A4]">
              {report
                ? `${tr(lang, overall!.fr, overall!.en)} • ${new Date(report.finished_at * 1000).toLocaleString()} • ${report.duration_s}s • ${report.passed}/${report.total} ${tr(lang, 'contrôles réussis', 'checks passed')}`
                : tr(lang, 'Aucun audit terminé pour le moment.', 'No audit completed yet.')}
            </p>
          </div>
        </div>
        <button
          onClick={runNow}
          disabled={state?.running}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[#20C997]/40 text-[#20C997] text-xs font-semibold hover:bg-[#20C997]/10 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${state?.running ? 'animate-spin' : ''}`} />
          {state?.running ? tr(lang, 'Audit en cours…', 'Audit running…') : tr(lang, 'Relancer l’audit', 'Run audit now')}
        </button>
      </div>

      {state?.running && (
        <div className="p-3 rounded-lg bg-[#080C0F] border border-[#20C997]/30">
          <div className="text-xs text-[#E8EEF2] mb-2">
            {tr(
              lang,
              'Vérification de la sécurité des API et des services en cours — cela peut prendre quelques minutes.',
              'Verifying API and service security — this can take a few minutes.'
            )}
          </div>
          {state.progress && (
            <>
              <div className="h-1.5 bg-white/10 rounded overflow-hidden">
                <div
                  className="h-full bg-[#20C997] transition-all"
                  style={{ width: `${Math.round(((state.progress.step + 0.5) / state.progress.total) * 100)}%` }}
                />
              </div>
              <div className="mt-1 text-[11px] text-[#8B98A4]">
                {tr(lang, `Étape ${state.progress.step + 1}/${state.progress.total} : `, `Step ${state.progress.step + 1}/${state.progress.total}: `)}
                {tr(lang, state.progress.label_fr, state.progress.label_en)}
              </div>
            </>
          )}
        </div>
      )}

      {loadError && <div className="text-xs text-[#F04438]">{loadError}</div>}

      {report && (
        <>
          <div className="flex flex-wrap gap-2">
            {(['critical', 'high', 'medium', 'low'] as const).map((sev) => (
              <span key={sev} className={`px-2 py-0.5 rounded border text-[11px] font-mono-tabular ${SEVERITY_STYLE[sev]}`}>
                {tr(lang, SEVERITY_LABEL[sev][0], SEVERITY_LABEL[sev][1])} : {report.counts[sev] || 0}
              </span>
            ))}
            {state && state.history.length > 1 && (
              <span className="flex items-center gap-1 ml-auto text-[10px] text-[#6E7B88]">
                {tr(lang, 'Historique', 'History')}
                {state.history.slice(-12).map((h, i) => (
                  <span
                    key={i}
                    title={new Date(h.finished_at * 1000).toLocaleString()}
                    className={`w-2 h-2 rounded-full ${
                      h.overall === 'ok' ? 'bg-[#20C997]' : h.overall === 'attention' ? 'bg-[#D6A84F]' : h.overall === 'degraded' ? 'bg-[#F79009]' : 'bg-[#F04438]'
                    }`}
                  />
                ))}
              </span>
            )}
          </div>

          {report.actions?.auto_lock && (
            <div className="p-3 rounded-lg bg-[#F04438]/10 border border-[#F04438]/40 text-xs text-[#F04438]">
              {tr(
                lang,
                `Mesure automatique : AutoTrade désactivé (mode sécurité) pour ${report.actions.auto_lock.users} utilisateur(s) suite à un problème critique.`,
                `Automatic measure: AutoTrade disabled (safe mode) for ${report.actions.auto_lock.users} user(s) after a critical issue.`
              )}
            </div>
          )}

          <label className="flex items-center gap-2 text-[11px] text-[#8B98A4] cursor-pointer w-fit">
            <input type="checkbox" checked={showPassed} onChange={(e) => setShowPassed(e.target.checked)} />
            {tr(lang, 'Afficher aussi les contrôles réussis', 'Also show passed checks')}
          </label>

          {Object.keys(grouped).length === 0 && (
            <div className="text-xs text-[#20C997]">{tr(lang, 'Aucun problème détecté.', 'No issue detected.')}</div>
          )}
          {Object.entries(grouped).map(([cat, list]) => (
            <div key={cat} className="space-y-2">
              <div className="text-[11px] uppercase tracking-wider text-[#6E7B88]">
                {tr(lang, (CATEGORY_LABELS[cat] || [cat, cat])[0], (CATEGORY_LABELS[cat] || [cat, cat])[1])}
              </div>
              {list.map((c) => (
                <div key={c.id} className="p-3 rounded-lg bg-[#080C0F] border border-white/[0.06] space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono-tabular ${c.status === 'pass' ? 'bg-[#20C997]/15 text-[#20C997] border-[#20C997]/40' : SEVERITY_STYLE[c.severity]}`}>
                      {c.status === 'pass' ? 'OK' : c.status === 'skip' ? tr(lang, 'Ignoré', 'Skipped') : tr(lang, SEVERITY_LABEL[c.severity][0], SEVERITY_LABEL[c.severity][1])}
                    </span>
                    <span className="text-xs font-semibold text-[#E8EEF2]">{tr(lang, c.title_fr, c.title_en)}</span>
                  </div>
                  {(c.detail_fr || c.detail_en) && (
                    <div className="text-[11px] text-[#8B98A4] break-words">{tr(lang, c.detail_fr || '', c.detail_en || '')}</div>
                  )}
                  {c.status !== 'pass' && (c.fix_fr || c.fix_en) && (
                    <div className="text-[11px] text-[#20C997]">
                      {tr(lang, 'Correction : ', 'Fix: ')}
                      {tr(lang, c.fix_fr || '', c.fix_en || '')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}

          <p className="text-[10px] text-[#6E7B88] border-t border-white/[0.06] pt-2">{tr(lang, report.disclaimer_fr, report.disclaimer_en)}</p>
        </>
      )}
      <p className="text-[10px] text-[#6E7B88]">
        {tr(
          lang,
          `Audit automatique au démarrage puis toutes les ${state?.interval_hours ?? 6} h. Les utilisateurs ne voient qu'un résumé (opérationnel / dégradé).`,
          `Automatic audit at startup then every ${state?.interval_hours ?? 6} h. Users only see a summary (operational / degraded).`
        )}
      </p>
    </div>
  );
};
