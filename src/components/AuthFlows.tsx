import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Eye, EyeOff, LogOut, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiFetch, ApiError } from '../api';
import { tr } from '../i18n';

/**
 * Parcours d'authentification complémentaires : choix d'appareil (personnel / partagé), session verrouillée, sessions actives et changement de mot de passe.
 * Les styles reprennent ceux de la modale de connexion existante (mêmes couleurs, bordures, boutons).
 * Toute validation affichée ici est une aide : le backend valide systématiquement.
 */

type Lang = string;

const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/;

export const inputCls =
  'w-full px-3 py-3 sm:py-2 text-base sm:text-sm bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2] focus:outline-none focus:border-[#20C997]/60';
export const primaryBtn =
  'w-full py-3 sm:py-2.5 bg-[#20C997] hover:bg-[#1AA67D] disabled:opacity-50 disabled:cursor-not-allowed text-[#080C0F] font-semibold rounded-lg transition-colors flex items-center justify-center gap-2';
export const secondaryBtn =
  'w-full py-3 sm:py-2.5 bg-[#172129] hover:bg-[#202A32] disabled:opacity-50 disabled:cursor-not-allowed border border-white/15 text-[#E8EEF2] text-sm font-semibold rounded-lg transition-colors';
export const linkBtn = 'text-xs text-[#8B98A4] hover:text-[#E8EEF2] underline-offset-2 hover:underline';

/** Message utilisateur sûr à partir d'une erreur d'API (jamais de détails internes). */
export function friendlyError(lang: Lang, err: unknown, fallbackFr: string, fallbackEn: string): string {
  if (err instanceof ApiError) {
    if (err.code === 'NETWORK_ERROR' || err.code === 'TIMEOUT') {
      return tr(
        lang,
        'Connexion impossible. Vérifiez votre réseau puis réessayez.',
        'Unable to connect. Check your network and try again.'
      );
    }
    if (err.status >= 500 && err.code === 'SERVER_ERROR') {
      return tr(lang, fallbackFr, fallbackEn);
    }
    if (err.status >= 500) return tr(lang, fallbackFr, fallbackEn);
    return err.message || tr(lang, fallbackFr, fallbackEn);
  }
  return tr(lang, fallbackFr, fallbackEn);
}

/* ------------------------------------------------------------------ Enveloppe commune */

export const AuthShell: React.FC<{
  lang: Lang;
  title: string;
  subtitle?: string;
  embedded?: boolean;
  children: React.ReactNode;
}> = ({ lang: _lang, title, subtitle, embedded, children }) => (
  <div className={embedded ? 'w-full' : 'min-h-screen bg-[#080C0F] text-[#E8EEF2] flex items-center justify-center p-4'}>
    <div className="bg-[#0D1318] border border-white/15 rounded-xl max-w-md w-full mx-auto p-5 sm:p-8 space-y-5">
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 shrink-0 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 flex items-center justify-center text-[#20C997] font-display font-bold">
          B
        </div>
        <div className="min-w-0">
          <h1 className="font-display text-base sm:text-lg font-bold text-[#E8EEF2] leading-tight">{title}</h1>
          {subtitle && <p className="text-[11px] text-[#6E7B88]">{subtitle}</p>}
        </div>
      </div>
      {children}
    </div>
  </div>
);

export const ErrorBox: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    role="alert"
    className="p-3 rounded-lg bg-[#F04438]/15 border border-[#F04438]/40 text-xs text-[#F97066] flex items-start gap-2"
  >
    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
    <span>{children}</span>
  </div>
);

export const SuccessBox: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    role="status"
    className="p-3 rounded-lg bg-[#20C997]/15 border border-[#20C997]/40 text-xs text-[#32D583] flex items-start gap-2"
  >
    <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-[#20C997]" />
    <span>{children}</span>
  </div>
);

/* ------------------------------------------------------------------ Mot de passe : règles + champ */

export interface PasswordChecks {
  length: boolean;
  letter: boolean;
  digit: boolean;
  tooLong: boolean;
}

export function checkPassword(pw: string): PasswordChecks {
  return {
    length: pw.length >= 8,
    letter: /[A-Za-z]/.test(pw),
    digit: /\d/.test(pw),
    tooLong: pw.length > 128,
  };
}

export const isPasswordValid = (c: PasswordChecks) => c.length && c.letter && c.digit && !c.tooLong;

export const PasswordRules: React.FC<{ lang: Lang; checks: PasswordChecks; touched: boolean }> = ({ lang, checks, touched }) => {
  const rules: Array<[boolean, string, string]> = [
    [checks.length, 'Au moins 8 caractères', 'At least 8 characters'],
    [checks.letter, 'Au moins une lettre', 'At least one letter'],
    [checks.digit, 'Au moins un chiffre', 'At least one digit'],
  ];
  return (
    <ul className="space-y-1 text-[11px]" aria-live="polite">
      {rules.map(([ok, fr, en]) => (
        <li key={fr} className={ok ? 'text-[#32D583]' : touched ? 'text-[#F97066]' : 'text-[#6E7B88]'}>
          <span aria-hidden="true">{ok ? '✓' : '•'}</span> {tr(lang, fr, en)}
          <span className="sr-only">{ok ? tr(lang, ' (respecté)', ' (met)') : tr(lang, ' (non respecté)', ' (not met)')}</span>
        </li>
      ))}
    </ul>
  );
};

export const PasswordField: React.FC<{
  lang: Lang;
  label: string;
  value: string;
  onChange: (v: string) => void;
  show: boolean;
  onToggleShow: () => void;
  autoComplete: string;
  id: string;
  disabled?: boolean;
  invalid?: boolean;
}> = ({ lang, label, value, onChange, show, onToggleShow, autoComplete, id, disabled, invalid }) => (
  <div>
    <label htmlFor={id} className="block text-xs text-[#8B98A4] mb-1">
      {label}
    </label>
    <div className="relative">
      <input
        id={id}
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        className={`${inputCls} pr-11 ${invalid ? 'border-[#F04438]/60' : ''}`}
        placeholder="••••••••"
      />
      <button
        type="button"
        onClick={onToggleShow}
        aria-label={show ? tr(lang, 'Masquer le mot de passe', 'Hide password') : tr(lang, 'Afficher le mot de passe', 'Show password')}
        className="absolute inset-y-0 right-0 w-11 flex items-center justify-center text-[#6E7B88] hover:text-[#E8EEF2]"
      >
        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  </div>
);

/* ------------------------------------------------------------------ 3. Appareil personnel ou partagé */

export const DeviceChoiceView: React.FC<{
  lang: Lang;
  onChosen: (kind: 'personal' | 'public', idleTimeoutSeconds: number) => void;
  onLogout: () => void;
}> = ({ lang, onChosen, onLogout }) => {
  const [busy, setBusy] = useState<'personal' | 'public' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const choose = async (kind: 'personal' | 'public') => {
    setBusy(kind);
    setError(null);
    try {
      const res = await apiFetch('/api/auth/session/device', { method: 'POST', body: JSON.stringify({ kind }) });
      onChosen(kind, Number(res?.idle_timeout_seconds) || 0);
    } catch (err) {
      setError(
        friendlyError(lang, err, 'Impossible d’enregistrer votre choix. Réessayez.', 'Unable to save your choice. Please try again.')
      );
    } finally {
      setBusy(null);
    }
  };

  const optionCls =
    'w-full text-left p-4 rounded-xl bg-[#080C0F] border border-white/10 hover:border-[#20C997]/60 disabled:opacity-60 disabled:cursor-not-allowed transition-colors';

  return (
    <AuthShell lang={lang} title={tr(lang, 'Cet appareil est-il personnel ?', 'Is this device personal?')}>
      {error && <ErrorBox>{error}</ErrorBox>}
      <button type="button" disabled={busy !== null} onClick={() => choose('personal')} className={optionCls}>
        <div className="font-semibold text-sm text-[#E8EEF2]">
          🏠 {tr(lang, 'Appareil personnel', 'Personal device')}
          {busy === 'personal' && <RefreshCw className="inline w-3.5 h-3.5 ml-2 animate-spin text-[#20C997]" />}
        </div>
        <div className="text-xs text-[#8B98A4] mt-1">
          {tr(lang, 'Utiliser Bitsure normalement sur cet appareil.', 'Use Bitsure normally on this device.')}
        </div>
      </button>
      <button type="button" disabled={busy !== null} onClick={() => choose('public')} className={optionCls}>
        <div className="font-semibold text-sm text-[#E8EEF2]">
          🌐 {tr(lang, 'Appareil partagé ou public', 'Shared or public device')}
          {busy === 'public' && <RefreshCw className="inline w-3.5 h-3.5 ml-2 animate-spin text-[#20C997]" />}
        </div>
        <div className="text-xs text-[#8B98A4] mt-1">
          {tr(
            lang,
            'Pour votre sécurité, cette session sera automatiquement verrouillée après une période d’inactivité.',
            'For your security, this session will be automatically locked after a period of inactivity.'
          )}
        </div>
      </button>
      <button type="button" onClick={onLogout} className={linkBtn}>
        {tr(lang, 'Me déconnecter', 'Sign out')}
      </button>
    </AuthShell>
  );
};

/* ------------------------------------------------------------------ 4. Session verrouillée */

export const SessionLockedView: React.FC<{ lang: Lang; onRelogin: () => void }> = ({ lang, onRelogin }) => (
  <AuthShell lang={lang} title={`🔒 ${tr(lang, 'Session verrouillée', 'Session locked')}`}>
    <p className="text-sm text-[#B6C0C9] leading-relaxed">
      {tr(
        lang,
        'Votre session a été verrouillée après une période d’inactivité.',
        'Your session was locked after a period of inactivity.'
      )}
    </p>
    <button type="button" onClick={onRelogin} className={primaryBtn}>
      {tr(lang, 'Se reconnecter', 'Sign in again')}
    </button>
  </AuthShell>
);

/* ------------------------------------------------------------------ 5. Sécurité : sessions actives + mot de passe */

interface SessionItem {
  id: string;
  device: string;
  browser: string;
  type: 'personal' | 'public' | 'pending';
  last_activity_at: number;
  current: boolean;
  locked: boolean;
}

export function relativeTime(lang: Lang, tsSeconds: number): string {
  const diff = Math.max(0, Math.floor(Date.now() / 1000 - tsSeconds));
  if (diff < 120) return tr(lang, 'Actif maintenant', 'Active now');
  const min = Math.floor(diff / 60);
  if (min < 60) return tr(lang, `Il y a ${min} min`, `${min} min ago`);
  const h = Math.floor(min / 60);
  if (h < 24) return tr(lang, `Il y a ${h} h`, `${h} h ago`);
  const d = Math.floor(h / 24);
  return tr(lang, `Il y a ${d} j`, `${d} d ago`);
}

const deviceIcon = (device: string) => (/iPhone|iPad|Android/i.test(device) ? '📱' : '💻');

export const SecuritySessionsPanel: React.FC<{
  lang: Lang;
  onToast: (text: string, type: 'success' | 'error' | 'info') => void;
}> = ({ lang, onToast }) => {
  const [sessions, setSessions] = useState<SessionItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const [revokingAll, setRevokingAll] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await apiFetch('/api/auth/sessions');
      setSessions(res.sessions || []);
    } catch (err) {
      setLoadError(friendlyError(lang, err, 'Impossible de charger vos sessions.', 'Unable to load your sessions.'));
    } finally {
      setLoading(false);
    }
  }, [lang]);

  useEffect(() => {
    load();
  }, [load]);

  const revoke = async (id: string) => {
    setRevokingId(id);
    setActionError(null);
    try {
      await apiFetch('/api/auth/sessions/revoke', { method: 'POST', body: JSON.stringify({ id }) });
      onToast(tr(lang, 'Session révoquée.', 'Session revoked.'), 'success');
      setConfirmRevokeId(null);
      await load();
    } catch (err) {
      setActionError(friendlyError(lang, err, 'Impossible de révoquer cette session.', 'Unable to revoke this session.'));
    } finally {
      setRevokingId(null);
    }
  };

  const revokeOthers = async () => {
    setRevokingAll(true);
    setActionError(null);
    try {
      const res = await apiFetch('/api/auth/sessions/revoke-others', { method: 'POST', body: JSON.stringify({}) });
      const n = Number(res?.revoked_sessions) || 0;
      onToast(
        n > 0
          ? tr(lang, `${n} appareil(s) déconnecté(s).`, `${n} device(s) signed out.`)
          : tr(lang, 'Aucun autre appareil n’était connecté.', 'No other device was signed in.'),
        'success'
      );
      setConfirmAll(false);
      await load();
    } catch (err) {
      setActionError(friendlyError(lang, err, 'Impossible de déconnecter les autres appareils.', 'Unable to sign out other devices.'));
    } finally {
      setRevokingAll(false);
    }
  };

  const typeLabel = (t: SessionItem['type']) =>
    t === 'public'
      ? tr(lang, 'Partagé / public', 'Shared / public')
      : t === 'pending'
      ? tr(lang, 'Non confirmé', 'Unconfirmed')
      : tr(lang, 'Personnel', 'Personal');

  const others = (sessions || []).filter((s) => !s.current).length;

  return (
    <div className="space-y-6">
      <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-display font-semibold text-base text-[#E8EEF2] flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-[#20C997]" />
              {tr(lang, 'Sessions actives', 'Active sessions')}
            </h3>
            <p className="text-[11px] text-[#6E7B88] mt-0.5">
              {tr(lang, 'Les appareils actuellement connectés à votre compte.', 'Devices currently signed in to your account.')}
            </p>
          </div>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            aria-label={tr(lang, 'Actualiser', 'Refresh')}
            className="p-2 rounded-lg bg-[#080C0F] border border-white/10 text-[#8B98A4] hover:text-[#E8EEF2] disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {loadError && (
          <ErrorBox>
            {loadError}{' '}
            <button type="button" onClick={load} className="underline font-semibold">
              {tr(lang, 'Réessayer', 'Retry')}
            </button>
          </ErrorBox>
        )}
        {actionError && <ErrorBox>{actionError}</ErrorBox>}

        {sessions === null && loading && (
          <div className="text-xs text-[#8B98A4] flex items-center gap-2" role="status">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> {tr(lang, 'Chargement…', 'Loading…')}
          </div>
        )}
        {sessions && sessions.length === 0 && (
          <p className="text-xs text-[#8B98A4]">{tr(lang, 'Aucune session active.', 'No active session.')}</p>
        )}

        <ul className="space-y-2">
          {(sessions || []).map((s) => (
            <li key={s.id} className="p-3 rounded-lg bg-[#080C0F] border border-white/10 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm text-[#E8EEF2] font-semibold truncate">
                  <span aria-hidden="true">{deviceIcon(s.device)}</span> {s.device} — {s.browser}
                </div>
                <div className="text-[11px] text-[#8B98A4] mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span>{s.locked ? tr(lang, 'Verrouillée', 'Locked') : s.current ? tr(lang, 'Actif maintenant', 'Active now') : relativeTime(lang, s.last_activity_at)}</span>
                  <span aria-hidden="true">·</span>
                  <span>{typeLabel(s.type)}</span>
                  {s.current && (
                    <span className="px-1.5 py-0.5 rounded bg-[#20C997]/15 border border-[#20C997]/30 text-[#20C997] text-[10px] font-semibold">
                      {tr(lang, 'Cet appareil', 'This device')}
                    </span>
                  )}
                </div>
              </div>
              {!s.current &&
                (confirmRevokeId === s.id ? (
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => revoke(s.id)}
                      disabled={revokingId === s.id}
                      className="px-3 py-2 text-xs font-semibold rounded-lg bg-[#F04438]/15 border border-[#F04438]/50 text-[#F97066] disabled:opacity-50"
                    >
                      {revokingId === s.id ? '…' : tr(lang, 'Confirmer', 'Confirm')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmRevokeId(null)}
                      className="px-3 py-2 text-xs rounded-lg bg-[#172129] border border-white/10 text-[#8B98A4]"
                    >
                      {tr(lang, 'Annuler', 'Cancel')}
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setConfirmRevokeId(s.id);
                      setConfirmAll(false);
                    }}
                    className="px-3 py-2 text-xs font-semibold rounded-lg bg-transparent border border-[#F04438]/50 text-[#F97066] hover:bg-[#F04438]/10 shrink-0"
                  >
                    {tr(lang, 'Révoquer', 'Revoke')}
                  </button>
                ))}
            </li>
          ))}
        </ul>

        {others > 0 && !confirmAll && (
          <button
            type="button"
            onClick={() => {
              setConfirmAll(true);
              setConfirmRevokeId(null);
            }}
            className="w-full py-2.5 text-xs font-semibold rounded-lg bg-transparent border border-[#F04438]/50 text-[#F97066] hover:bg-[#F04438]/10 flex items-center justify-center gap-2"
          >
            <LogOut className="w-4 h-4" />
            {tr(lang, 'Déconnecter tous les appareils', 'Sign out all devices')}
          </button>
        )}
        {confirmAll && (
          <div className="p-3 rounded-lg bg-[#F04438]/10 border border-[#F04438]/40 space-y-3">
            <p className="text-xs text-[#E8EEF2] leading-relaxed">
              {tr(
                lang,
                'Tous les autres appareils seront déconnectés. Vous resterez connecté sur cet appareil. Continuer ?',
                'All other devices will be signed out. You will stay signed in on this device. Continue?'
              )}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={revokeOthers}
                disabled={revokingAll}
                className="flex-1 py-2.5 text-xs font-semibold rounded-lg bg-[#F04438] text-white disabled:opacity-50"
              >
                {revokingAll ? tr(lang, 'Déconnexion…', 'Signing out…') : tr(lang, 'Oui, déconnecter', 'Yes, sign out')}
              </button>
              <button
                type="button"
                onClick={() => setConfirmAll(false)}
                disabled={revokingAll}
                className="flex-1 py-2.5 text-xs rounded-lg bg-[#172129] border border-white/10 text-[#E8EEF2]"
              >
                {tr(lang, 'Annuler', 'Cancel')}
              </button>
            </div>
          </div>
        )}
      </div>

      <ChangePasswordCard lang={lang} onToast={onToast} onChanged={load} />
    </div>
  );
};

const ChangePasswordCard: React.FC<{
  lang: Lang;
  onToast: (text: string, type: 'success' | 'error' | 'info') => void;
  onChanged: () => void;
}> = ({ lang, onToast, onChanged }) => {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const checks = useMemo(() => checkPassword(next), [next]);
  const mismatch = confirm.length > 0 && confirm !== next;
  const canSubmit = current.length > 0 && isPasswordValid(checks) && confirm === next && !busy;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await apiFetch('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next, confirm_password: confirm }),
      });
      setCurrent('');
      setNext('');
      setConfirm('');
      const msg = res?.message || tr(lang, 'Mot de passe modifié.', 'Password changed.');
      setSuccess(msg);
      onToast(msg, 'success');
      onChanged();
    } catch (err) {
      setError(friendlyError(lang, err, 'Impossible de modifier le mot de passe pour le moment.', 'Unable to change the password right now.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
      <div>
        <h3 className="font-display font-semibold text-base text-[#E8EEF2]">{tr(lang, 'Changer le mot de passe', 'Change password')}</h3>
        <p className="text-[11px] text-[#6E7B88] mt-0.5">
          {tr(lang, 'Vos autres appareils seront déconnectés après le changement.', 'Your other devices will be signed out after the change.')}
        </p>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {success && <SuccessBox>{success}</SuccessBox>}
      <form onSubmit={submit} className="space-y-3" noValidate>
        <PasswordField
          lang={lang}
          id="cp-current"
          label={tr(lang, 'Mot de passe actuel', 'Current password')}
          value={current}
          onChange={setCurrent}
          show={show}
          onToggleShow={() => setShow((s) => !s)}
          autoComplete="current-password"
          disabled={busy}
        />
        <PasswordField
          lang={lang}
          id="cp-new"
          label={tr(lang, 'Nouveau mot de passe', 'New password')}
          value={next}
          onChange={setNext}
          show={show}
          onToggleShow={() => setShow((s) => !s)}
          autoComplete="new-password"
          disabled={busy}
        />
        <PasswordRules lang={lang} checks={checks} touched={next.length > 0} />
        <PasswordField
          lang={lang}
          id="cp-confirm"
          label={tr(lang, 'Confirmer le nouveau mot de passe', 'Confirm new password')}
          value={confirm}
          onChange={setConfirm}
          show={show}
          onToggleShow={() => setShow((s) => !s)}
          autoComplete="new-password"
          disabled={busy}
          invalid={mismatch}
        />
        {mismatch && (
          <p className="text-[11px] text-[#F97066]" role="alert">
            {tr(lang, 'Les deux mots de passe ne correspondent pas.', 'The two passwords do not match.')}
          </p>
        )}
        <button type="submit" disabled={!canSubmit} className={primaryBtn}>
          {busy ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              {tr(lang, 'Enregistrement…', 'Saving…')}
            </>
          ) : (
            tr(lang, 'Modifier le mot de passe', 'Change password')
          )}
        </button>
      </form>
    </div>
  );
};
