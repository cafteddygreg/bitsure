import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Eye, EyeOff, LogOut, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiFetch, ApiError } from '../api';
import { tr } from '../i18n';

/**
 * Parcours d'authentification complémentaires : mot de passe oublié, réinitialisation,
 * choix d'appareil (personnel / partagé), session verrouillée, sessions actives et changement de mot de passe.
 * Les styles reprennent ceux de la modale de connexion existante (mêmes couleurs, bordures, boutons).
 * Toute validation affichée ici est une aide : le backend valide systématiquement.
 */

type Lang = string;

const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/;

const inputCls =
  'w-full px-3 py-3 sm:py-2 text-base sm:text-sm bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2] focus:outline-none focus:border-[#20C997]/60';
const primaryBtn =
  'w-full py-3 sm:py-2.5 bg-[#20C997] hover:bg-[#1AA67D] disabled:opacity-50 disabled:cursor-not-allowed text-[#080C0F] font-semibold rounded-lg transition-colors flex items-center justify-center gap-2';
const secondaryBtn =
  'w-full py-3 sm:py-2.5 bg-[#172129] hover:bg-[#202A32] disabled:opacity-50 disabled:cursor-not-allowed border border-white/15 text-[#E8EEF2] text-sm font-semibold rounded-lg transition-colors';
const linkBtn = 'text-xs text-[#8B98A4] hover:text-[#E8EEF2] underline-offset-2 hover:underline';

/** Message utilisateur sûr à partir d'une erreur d'API (jamais de détails internes). */
function friendlyError(lang: Lang, err: unknown, fallbackFr: string, fallbackEn: string): string {
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

const AuthShell: React.FC<{
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

const ErrorBox: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    role="alert"
    className="p-3 rounded-lg bg-[#F04438]/15 border border-[#F04438]/40 text-xs text-[#F97066] flex items-start gap-2"
  >
    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
    <span>{children}</span>
  </div>
);

const SuccessBox: React.FC<{ children: React.ReactNode }> = ({ children }) => (
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

const isPasswordValid = (c: PasswordChecks) => c.length && c.letter && c.digit && !c.tooLong;

const PasswordRules: React.FC<{ lang: Lang; checks: PasswordChecks; touched: boolean }> = ({ lang, checks, touched }) => {
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

const PasswordField: React.FC<{
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

/* ------------------------------------------------------------------ 1. Mot de passe oublié */

export const ForgotPasswordView: React.FC<{
  lang: Lang;
  initialEmail?: string;
  onBackToLogin: () => void;
  embedded?: boolean;
}> = ({ lang, initialEmail = '', onBackToLogin, embedded }) => {
  const [email, setEmail] = useState(initialEmail);
  const [step, setStep] = useState<'form' | 'sent'>('form');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const [sentTo, setSentTo] = useState('');

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const emailValid = EMAIL_RE.test(email.trim());

  const submit = useCallback(
    async (target: string) => {
      setError(null);
      setLoading(true);
      try {
        const res = await apiFetch('/api/auth/forgot-password', {
          method: 'POST',
          body: JSON.stringify({ email: target.trim(), lang: String(lang).startsWith('en') ? 'en' : 'fr' }),
        });
        setSentTo(target.trim());
        setStep('sent');
        setCooldown(Number(res?.cooldown_seconds) || 60);
      } catch (err) {
        if (err instanceof ApiError && err.code === 'RATE_LIMITED') {
          setCooldown(Number(err.payload?.retry_after) || 60);
        }
        setError(
          friendlyError(
            lang,
            err,
            "Impossible d'envoyer la demande pour le moment. Réessayez dans quelques instants.",
            'Unable to send the request right now. Please try again in a moment.'
          )
        );
      } finally {
        setLoading(false);
      }
    },
    [lang]
  );

  if (step === 'sent') {
    return (
      <AuthShell lang={lang} embedded={embedded} title={tr(lang, 'Vérifiez votre boîte mail', 'Check your inbox')}>
        <p className="text-sm text-[#B6C0C9] leading-relaxed">
          {tr(
            lang,
            'Si un compte correspond à l’adresse fournie, un email de récupération vient d’être envoyé. Pensez à vérifier vos courriers indésirables.',
            'If an account matches the address you provided, a recovery email has just been sent. Remember to check your spam folder.'
          )}
        </p>
        <p className="text-[11px] text-[#6E7B88]">
          {tr(lang, 'Adresse saisie : ', 'Address entered: ')}
          <span className="text-[#8B98A4] break-all">{sentTo}</span>
        </p>
        {error && <ErrorBox>{error}</ErrorBox>}
        <button type="button" onClick={() => submit(sentTo)} disabled={loading || cooldown > 0} className={secondaryBtn}>
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              {tr(lang, 'Envoi…', 'Sending…')}
            </span>
          ) : cooldown > 0 ? (
            tr(lang, `Renvoyer l’email (${cooldown} s)`, `Resend email (${cooldown} s)`)
          ) : (
            tr(lang, 'Renvoyer l’email', 'Resend email')
          )}
        </button>
        <div className="flex items-center justify-between gap-3">
          <button type="button" onClick={() => { setStep('form'); setError(null); }} className={linkBtn}>
            {tr(lang, 'Changer d’adresse', 'Use another address')}
          </button>
          <button type="button" onClick={onBackToLogin} className={linkBtn}>
            ← {tr(lang, 'Retour à la connexion', 'Back to sign in')}
          </button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell lang={lang} embedded={embedded} title={tr(lang, 'Réinitialiser votre mot de passe', 'Reset your password')}>
      <p className="text-sm text-[#B6C0C9] leading-relaxed">
        {tr(
          lang,
          'Saisissez l’adresse email de votre compte Bitsure. Nous vous enverrons un lien sécurisé pour choisir un nouveau mot de passe.',
          'Enter the email address of your Bitsure account. We will send you a secure link to choose a new password.'
        )}
      </p>
      {error && <ErrorBox>{error}</ErrorBox>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (emailValid && !loading) submit(email);
        }}
        className="space-y-4"
        noValidate
      >
        <div>
          <label htmlFor="forgot-email" className="block text-xs text-[#8B98A4] mb-1">
            {tr(lang, 'Adresse email', 'Email address')}
          </label>
          <input
            id="forgot-email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={tr(lang, 'votre@email.com', 'you@email.com')}
            className={inputCls}
            disabled={loading}
          />
          {email.length > 0 && !emailValid && (
            <p className="mt-1 text-[11px] text-[#F97066]">{tr(lang, 'Adresse email invalide.', 'Invalid email address.')}</p>
          )}
        </div>
        <button type="submit" disabled={!emailValid || loading} className={primaryBtn}>
          {loading ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              {tr(lang, 'Envoi…', 'Sending…')}
            </>
          ) : (
            tr(lang, 'Envoyer le lien', 'Send link')
          )}
        </button>
      </form>
      <button type="button" onClick={onBackToLogin} className={linkBtn}>
        ← {tr(lang, 'Retour à la connexion', 'Back to sign in')}
      </button>
    </AuthShell>
  );
};

/* ------------------------------------------------------------------ 2. Nouveau mot de passe */

type ResetPhase = 'checking' | 'form' | 'invalid' | 'expired' | 'used' | 'success' | 'failure';

export const ResetPasswordView: React.FC<{
  lang: Lang;
  token: string;
  onGoLogin: () => void;
  onRequestNewLink: () => void;
}> = ({ lang, token, onGoLogin, onRequestNewLink }) => {
  const [phase, setPhase] = useState<ResetPhase>(token ? 'checking' : 'invalid');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverRules, setServerRules] = useState<string[]>([]);
  const [attempt, setAttempt] = useState(0);

  // Vérification du lien à l'ouverture (et au rechargement de la page).
  useEffect(() => {
    if (!token) {
      setPhase('invalid');
      return;
    }
    let cancelled = false;
    setPhase('checking');
    apiFetch('/api/auth/reset-password/validate', { method: 'POST', body: JSON.stringify({ token }) })
      .then(() => {
        if (!cancelled) setPhase('form');
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.code === 'TOKEN_EXPIRED') setPhase('expired');
        else if (err instanceof ApiError && err.code === 'TOKEN_USED') setPhase('used');
        else if (err instanceof ApiError && err.code === 'TOKEN_INVALID') setPhase('invalid');
        else {
          setError(
            friendlyError(
              lang,
              err,
              'Impossible de vérifier le lien pour le moment.',
              'Unable to verify the link right now.'
            )
          );
          setPhase('failure');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, lang, attempt]);

  const checks = useMemo(() => checkPassword(password), [password]);
  const mismatch = confirm.length > 0 && confirm !== password;
  const canSubmit = isPasswordValid(checks) && confirm === password && !submitting;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    setServerRules([]);
    try {
      await apiFetch('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ token, password, confirm_password: confirm }),
      });
      setPassword('');
      setConfirm('');
      setPhase('success');
    } catch (err) {
      if (err instanceof ApiError && err.code === 'TOKEN_EXPIRED') setPhase('expired');
      else if (err instanceof ApiError && err.code === 'TOKEN_USED') setPhase('used');
      else if (err instanceof ApiError && err.code === 'TOKEN_INVALID') setPhase('invalid');
      else {
        const rules = err instanceof ApiError ? err.payload?.rule_messages : undefined;
        if (err instanceof ApiError && err.code === 'PASSWORD_WEAK') {
          setError(tr(lang, 'Ce mot de passe ne respecte pas les règles de sécurité.', 'This password does not meet the security rules.'));
        } else if (err instanceof ApiError && err.code === 'PASSWORD_MISMATCH') {
          setError(tr(lang, 'Les deux mots de passe ne correspondent pas.', 'The two passwords do not match.'));
        } else {
          setError(
            friendlyError(
              lang,
              err,
              'Une erreur est survenue. Votre mot de passe n’a pas été modifié, vous pouvez réessayer.',
              'Something went wrong. Your password was not changed, you can try again.'
            )
          );
        }
        if (Array.isArray(rules)) setServerRules(rules);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (phase === 'checking') {
    return (
      <AuthShell lang={lang} title={tr(lang, 'Vérification du lien…', 'Checking your link…')}>
        <div className="flex items-center gap-3 text-sm text-[#8B98A4]" role="status">
          <RefreshCw className="w-4 h-4 animate-spin text-[#20C997]" />
          {tr(lang, 'Un instant, nous vérifions votre lien sécurisé.', 'One moment, we are verifying your secure link.')}
        </div>
      </AuthShell>
    );
  }

  if (phase === 'expired' || phase === 'invalid' || phase === 'used') {
    const content = {
      expired: {
        title: tr(lang, 'Ce lien a expiré', 'This link has expired'),
        text: tr(lang, 'Pour votre sécurité, les liens de réinitialisation ne sont valables que peu de temps.', 'For your security, reset links are only valid for a short time.'),
      },
      invalid: {
        title: tr(lang, 'Lien de réinitialisation invalide', 'Invalid reset link'),
        text: tr(lang, 'Ce lien est incorrect ou a été remplacé par un lien plus récent.', 'This link is incorrect or has been replaced by a more recent one.'),
      },
      used: {
        title: tr(lang, 'Ce lien a déjà été utilisé', 'This link has already been used'),
        text: tr(lang, 'Chaque lien ne peut servir qu’une seule fois. Si besoin, demandez-en un nouveau.', 'Each link can only be used once. If needed, request a new one.'),
      },
    }[phase];
    return (
      <AuthShell lang={lang} title={content.title}>
        <p className="text-sm text-[#B6C0C9] leading-relaxed">{content.text}</p>
        <button type="button" onClick={onRequestNewLink} className={primaryBtn}>
          {tr(lang, 'Demander un nouveau lien', 'Request a new link')}
        </button>
        <button type="button" onClick={onGoLogin} className={linkBtn}>
          ← {tr(lang, 'Retour à la connexion', 'Back to sign in')}
        </button>
      </AuthShell>
    );
  }

  if (phase === 'failure') {
    return (
      <AuthShell lang={lang} title={tr(lang, 'Un problème est survenu', 'Something went wrong')}>
        {error && <ErrorBox>{error}</ErrorBox>}
        <button type="button" onClick={() => setAttempt((n) => n + 1)} className={primaryBtn}>
          <RefreshCw className="w-4 h-4" />
          {tr(lang, 'Réessayer', 'Try again')}
        </button>
        <button type="button" onClick={onGoLogin} className={linkBtn}>
          ← {tr(lang, 'Retour à la connexion', 'Back to sign in')}
        </button>
      </AuthShell>
    );
  }

  if (phase === 'success') {
    return (
      <AuthShell lang={lang} title={tr(lang, 'Mot de passe réinitialisé', 'Password reset')}>
        <SuccessBox>
          {tr(
            lang,
            'Votre mot de passe a été modifié avec succès. Vous pouvez maintenant vous connecter à votre compte Bitsure.',
            'Your password was changed successfully. You can now sign in to your Bitsure account.'
          )}
        </SuccessBox>
        <button type="button" onClick={onGoLogin} className={primaryBtn}>
          {tr(lang, 'Se connecter', 'Sign in')}
        </button>
      </AuthShell>
    );
  }

  return (
    <AuthShell lang={lang} title={tr(lang, 'Créer un nouveau mot de passe', 'Create a new password')}>
      {error && <ErrorBox>{error}</ErrorBox>}
      <form onSubmit={submit} className="space-y-4" noValidate>
        <PasswordField
          lang={lang}
          id="reset-password"
          label={tr(lang, 'Nouveau mot de passe', 'New password')}
          value={password}
          onChange={setPassword}
          show={show}
          onToggleShow={() => setShow((s) => !s)}
          autoComplete="new-password"
          disabled={submitting}
        />
        <PasswordRules lang={lang} checks={checks} touched={password.length > 0} />
        <PasswordField
          lang={lang}
          id="reset-confirm"
          label={tr(lang, 'Confirmer le nouveau mot de passe', 'Confirm new password')}
          value={confirm}
          onChange={setConfirm}
          show={show}
          onToggleShow={() => setShow((s) => !s)}
          autoComplete="new-password"
          disabled={submitting}
          invalid={mismatch}
        />
        {mismatch && (
          <p className="text-[11px] text-[#F97066]" role="alert">
            {tr(lang, 'Les deux mots de passe ne correspondent pas.', 'The two passwords do not match.')}
          </p>
        )}
        {serverRules.length > 0 && (
          <ul className="text-[11px] text-[#F97066] list-disc pl-4 space-y-0.5">
            {serverRules.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
        <button type="submit" disabled={!canSubmit} className={primaryBtn}>
          {submitting ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              {tr(lang, 'Enregistrement…', 'Saving…')}
            </>
          ) : (
            tr(lang, 'Réinitialiser le mot de passe', 'Reset password')
          )}
        </button>
      </form>
    </AuthShell>
  );
};

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

function relativeTime(lang: Lang, tsSeconds: number): string {
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
