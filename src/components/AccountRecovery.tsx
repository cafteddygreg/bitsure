import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, ShieldCheck } from 'lucide-react';
import { apiFetch, ApiError } from '../api';
import { tr } from '../i18n';
import {
  AuthShell,
  ErrorBox,
  SuccessBox,
  PasswordField,
  PasswordRules,
  checkPassword,
  isPasswordValid,
  friendlyError,
  relativeTime,
  inputCls,
  primaryBtn,
  secondaryBtn,
  linkBtn,
} from './AuthFlows';

/**
 * Récupération de compte interne à Bitsure (sans email ni service externe) :
 * demande -> examen administrateur -> mot de passe temporaire -> changement obligatoire.
 * Les signaux affichés à l'administrateur sont des indices de cohérence, jamais une preuve d'identité.
 */

type Lang = string;
const TOKEN_KEY = 'bitsure_recovery_token';
const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/;

const STATUS_LABELS: Record<string, [string, string]> = {
  pending: ['En attente', 'Pending'],
  under_review: ['En cours d’examen', 'Under review'],
  needs_info: ['Informations supplémentaires requises', 'More information required'],
  approved: ['Approuvée', 'Approved'],
  rejected: ['Refusée', 'Rejected'],
  expired: ['Expirée', 'Expired'],
  completed: ['Terminée', 'Completed'],
};
const statusLabel = (lang: Lang, st: string) => {
  const l = STATUS_LABELS[st];
  return l ? tr(lang, l[0], l[1]) : st;
};
const statusTone = (st: string) =>
  st === 'approved' || st === 'completed'
    ? 'bg-[#20C997]/15 border-[#20C997]/40 text-[#32D583]'
    : st === 'rejected' || st === 'expired'
    ? 'bg-[#F04438]/15 border-[#F04438]/40 text-[#F97066]'
    : st === 'needs_info'
    ? 'bg-[#F79009]/15 border-[#F79009]/40 text-[#FEC84B]'
    : 'bg-[#172129] border-white/15 text-[#B6C0C9]';

const StatusBadge: React.FC<{ lang: Lang; status: string }> = ({ lang, status }) => (
  <span className={`inline-block px-2 py-0.5 rounded border text-[11px] font-semibold ${statusTone(status)}`}>
    {statusLabel(lang, status)}
  </span>
);

const fmt = (ts: number) => (ts ? new Date(ts * 1000).toLocaleString() : '—');

interface Msg {
  author: 'user' | 'admin';
  body: string;
  created_at: number;
}

const MessageThread: React.FC<{ lang: Lang; messages: Msg[]; youAre: 'user' | 'admin' }> = ({ lang, messages, youAre }) => {
  if (!messages.length) return null;
  return (
    <ul className="space-y-2">
      {messages.map((m, i) => (
        <li
          key={i}
          className={`p-2.5 rounded-lg text-xs leading-relaxed border ${
            m.author === youAre ? 'bg-[#172129] border-white/10 ml-6' : 'bg-[#080C0F] border-[#20C997]/25 mr-6'
          }`}
        >
          <div className="text-[10px] text-[#6E7B88] mb-0.5">
            {m.author === 'admin' ? tr(lang, 'Administration', 'Administration') : tr(lang, 'Vous', 'You')} · {fmt(m.created_at)}
          </div>
          <div className="text-[#E8EEF2] whitespace-pre-wrap break-words">{m.body}</div>
        </li>
      ))}
    </ul>
  );
};

/* ------------------------------------------------------------------ Utilisateur : demande + suivi */

interface PublicRequest {
  request_id: string;
  status: string;
  created_at: number;
  temp_expires_at: number;
  rejection_reason?: string | null;
  messages: Msg[];
}

export const AccountRecoveryView: React.FC<{
  lang: Lang;
  initialEmail?: string;
  onBackToLogin: () => void;
  embedded?: boolean;
}> = ({ lang, initialEmail = '', onBackToLogin, embedded }) => {
  const [token, setToken] = useState<string>(() => {
    try {
      return localStorage.getItem(TOKEN_KEY) || '';
    } catch {
      return '';
    }
  });
  const [email, setEmail] = useState(initialEmail);
  const [note, setNote] = useState('');
  const [req, setReq] = useState<PublicRequest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reply, setReply] = useState('');
  const [replying, setReplying] = useState(false);
  const [replyInfo, setReplyInfo] = useState<string | null>(null);

  const persistToken = (t: string) => {
    setToken(t);
    try {
      if (t) localStorage.setItem(TOKEN_KEY, t);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* stockage indisponible : le suivi reste possible tant que la page est ouverte */
    }
  };

  const refresh = useCallback(
    async (t: string) => {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch('/api/auth/recovery/status', { method: 'POST', body: JSON.stringify({ token: t }) });
        setReq(res.request);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          persistToken('');
          setReq(null);
        } else {
          setError(friendlyError(lang, err, 'Impossible de récupérer le statut pour le moment.', 'Unable to fetch the status right now.'));
        }
      } finally {
        setLoading(false);
      }
    },
    [lang]
  );

  useEffect(() => {
    if (token) refresh(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const emailValid = EMAIL_RE.test(email.trim());

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!emailValid || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch('/api/auth/recovery/request', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), note: note.trim() }),
      });
      persistToken(res.tracking_token);
      await refresh(res.tracking_token);
    } catch (err) {
      setError(
        friendlyError(
          lang,
          err,
          'Impossible d’envoyer la demande pour le moment. Réessayez dans quelques instants.',
          'Unable to send the request right now. Please try again shortly.'
        )
      );
      setLoading(false);
    }
  };

  const sendReply = async () => {
    if (!reply.trim() || replying) return;
    setReplying(true);
    setReplyInfo(null);
    try {
      await apiFetch('/api/auth/recovery/message', { method: 'POST', body: JSON.stringify({ token, body: reply.trim() }) });
      setReply('');
      setReplyInfo(tr(lang, 'Message envoyé à l’administration.', 'Message sent to the administration.'));
      await refresh(token);
    } catch (err) {
      setReplyInfo(null);
      setError(friendlyError(lang, err, 'Impossible d’envoyer le message.', 'Unable to send the message.'));
    } finally {
      setReplying(false);
    }
  };

  const open = req && ['pending', 'under_review', 'needs_info'].includes(req.status);

  /* ----- Suivi ----- */
  if (token && req) {
    const info: Record<string, [string, string]> = {
      pending: [
        'Votre demande de récupération a été transmise à l’administration de Bitsure. Vous pouvez suivre son statut depuis cette page.',
        'Your recovery request has been sent to the Bitsure administration. You can follow its status from this page.',
      ],
      under_review: ['Votre demande est en cours d’examen par l’administration.', 'Your request is being reviewed by the administration.'],
      needs_info: [
        'L’administration a besoin d’informations supplémentaires. Répondez ci-dessous.',
        'The administration needs more information. Reply below.',
      ],
      approved: [
        'Votre demande a été approuvée. Un mot de passe temporaire a été généré : l’administration vous le transmettra. Utilisez-le pour vous connecter, puis choisissez immédiatement un nouveau mot de passe.',
        'Your request was approved. A temporary password was generated: the administration will give it to you. Use it to sign in, then choose a new password immediately.',
      ],
      rejected: ['Votre demande a été refusée.', 'Your request was rejected.'],
      expired: ['Cette demande a expiré. Vous pouvez en créer une nouvelle.', 'This request has expired. You can create a new one.'],
      completed: ['Votre mot de passe a été modifié. Vous pouvez vous connecter.', 'Your password was changed. You can sign in.'],
    };
    const finished = ['rejected', 'expired', 'completed'].includes(req.status);
    return (
      <AuthShell lang={lang} embedded={embedded} title={tr(lang, 'Demande envoyée', 'Request sent')} subtitle={`#${req.request_id}`}>
        <div className="flex items-center justify-between gap-3">
          <StatusBadge lang={lang} status={req.status} />
          <button
            type="button"
            onClick={() => refresh(token)}
            disabled={loading}
            className="text-xs text-[#8B98A4] hover:text-[#E8EEF2] flex items-center gap-1.5 py-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            {tr(lang, 'Actualiser', 'Refresh')}
          </button>
        </div>
        <p className="text-sm text-[#B6C0C9] leading-relaxed">{tr(lang, info[req.status]?.[0] || '', info[req.status]?.[1] || '')}</p>
        {req.status === 'approved' && req.temp_expires_at > 0 && (
          <p className="text-[11px] text-[#8B98A4]">
            {tr(lang, 'Le mot de passe temporaire expire le ', 'The temporary password expires on ')}
            {fmt(req.temp_expires_at)}.
          </p>
        )}
        {req.status === 'rejected' && req.rejection_reason && (
          <p className="text-xs text-[#8B98A4]">
            {tr(lang, 'Motif : ', 'Reason: ')}
            {req.rejection_reason}
          </p>
        )}
        {error && <ErrorBox>{error}</ErrorBox>}
        <MessageThread lang={lang} messages={req.messages} youAre="user" />
        {open && (
          <div className="space-y-2">
            <textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              maxLength={1000}
              rows={3}
              disabled={replying}
              placeholder={tr(lang, 'Ajouter un message pour l’administration…', 'Add a message for the administration…')}
              className={inputCls}
            />
            {replyInfo && <SuccessBox>{replyInfo}</SuccessBox>}
            <button type="button" onClick={sendReply} disabled={!reply.trim() || replying} className={secondaryBtn}>
              {replying ? tr(lang, 'Envoi…', 'Sending…') : tr(lang, 'Envoyer le message', 'Send message')}
            </button>
            <p className="text-[11px] text-[#6E7B88]">
              {tr(lang, 'N’écrivez jamais de mot de passe dans un message.', 'Never write a password in a message.')}
            </p>
          </div>
        )}
        {(req.status === 'approved' || req.status === 'completed') && (
          <button type="button" onClick={onBackToLogin} className={primaryBtn}>
            {tr(lang, 'Se connecter', 'Sign in')}
          </button>
        )}
        {finished && req.status !== 'completed' && (
          <button
            type="button"
            onClick={() => {
              persistToken('');
              setReq(null);
            }}
            className={secondaryBtn}
          >
            {tr(lang, 'Nouvelle demande', 'New request')}
          </button>
        )}
        <button type="button" onClick={onBackToLogin} className={linkBtn}>
          ← {tr(lang, 'Retour à la connexion', 'Back to sign in')}
        </button>
      </AuthShell>
    );
  }

  /* ----- Formulaire ----- */
  return (
    <AuthShell lang={lang} embedded={embedded} title={tr(lang, 'Récupération de compte', 'Account recovery')}>
      <div className="space-y-2">
        <p className="text-sm text-[#E8EEF2] font-semibold">{tr(lang, 'Vous avez oublié votre mot de passe ?', 'Did you forget your password?')}</p>
        <p className="text-sm text-[#B6C0C9] leading-relaxed">
          {tr(
            lang,
            'Vous pouvez envoyer une demande de récupération à l’administration de Bitsure.',
            'You can send a recovery request to the Bitsure administration.'
          )}
        </p>
        <p className="text-[11px] text-[#6E7B88] leading-relaxed">
          {tr(
            lang,
            'Certaines informations liées à vos sessions précédentes pourront être utilisées pour évaluer la légitimité de la demande.',
            'Some information linked to your previous sessions may be used to assess the legitimacy of the request.'
          )}
        </p>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="rec-email" className="block text-xs text-[#8B98A4] mb-1">
            {tr(lang, 'Adresse email du compte', 'Account email address')}
          </label>
          <input
            id="rec-email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            className={inputCls}
            placeholder={tr(lang, 'votre@email.com', 'you@email.com')}
          />
          {email.length > 0 && !emailValid && (
            <p className="mt-1 text-[11px] text-[#F97066]">{tr(lang, 'Adresse email invalide.', 'Invalid email address.')}</p>
          )}
        </div>
        <div>
          <label htmlFor="rec-note" className="block text-xs text-[#8B98A4] mb-1">
            {tr(lang, 'Message pour l’administration (facultatif)', 'Message for the administration (optional)')}
          </label>
          <textarea
            id="rec-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
            rows={3}
            disabled={loading}
            className={inputCls}
            placeholder={tr(lang, 'Ex. : appareil habituel, dernière utilisation…', 'E.g. usual device, last time you used it…')}
          />
        </div>
        <button type="submit" disabled={!emailValid || loading} className={primaryBtn}>
          {loading ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              {tr(lang, 'Envoi…', 'Sending…')}
            </>
          ) : (
            tr(lang, 'Envoyer la demande', 'Send request')
          )}
        </button>
      </form>
      <button type="button" onClick={onBackToLogin} className={linkBtn}>
        ← {tr(lang, 'Retour à la connexion', 'Back to sign in')}
      </button>
    </AuthShell>
  );
};

/* ------------------------------------------------------------------ Changement obligatoire */

export const ForcePasswordChangeView: React.FC<{
  lang: Lang;
  onDone: () => void;
  onLogout: () => void;
}> = ({ lang, onDone, onLogout }) => {
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const checks = useMemo(() => checkPassword(pw), [pw]);
  const mismatch = confirm.length > 0 && confirm !== pw;
  const canSubmit = isPasswordValid(checks) && pw === confirm && !busy;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch('/api/auth/password/force-change', {
        method: 'POST',
        body: JSON.stringify({ new_password: pw, confirm_password: confirm }),
      });
      setPw('');
      setConfirm('');
      onDone();
    } catch (err) {
      setError(friendlyError(lang, err, 'Impossible de modifier le mot de passe pour le moment.', 'Unable to change the password right now.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell lang={lang} title={tr(lang, 'Nouveau mot de passe requis', 'New password required')}>
      <p className="text-sm text-[#B6C0C9] leading-relaxed">
        {tr(
          lang,
          'Pour protéger votre compte, vous devez choisir un nouveau mot de passe avant de continuer.',
          'To protect your account, you must choose a new password before continuing.'
        )}
      </p>
      {error && <ErrorBox>{error}</ErrorBox>}
      <form onSubmit={submit} className="space-y-4" noValidate>
        <PasswordField
          lang={lang}
          id="fc-new"
          label={tr(lang, 'Nouveau mot de passe', 'New password')}
          value={pw}
          onChange={setPw}
          show={show}
          onToggleShow={() => setShow((s) => !s)}
          autoComplete="new-password"
          disabled={busy}
        />
        <PasswordRules lang={lang} checks={checks} touched={pw.length > 0} />
        <PasswordField
          lang={lang}
          id="fc-confirm"
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
            tr(lang, 'Valider le nouveau mot de passe', 'Confirm new password')
          )}
        </button>
      </form>
      <button type="button" onClick={onLogout} className={linkBtn}>
        {tr(lang, 'Me déconnecter', 'Sign out')}
      </button>
    </AuthShell>
  );
};

/* ------------------------------------------------------------------ Administration */

interface AdminListItem {
  id: string;
  email: string;
  status: string;
  created_at: number;
  trust_level: 'high' | 'medium' | 'low';
  signals: Array<{ key: string; state: string }>;
}
interface AdminDetail {
  id: string;
  status: string;
  created_at: number;
  reviewed_at: number;
  rejection_reason?: string | null;
  temp_expires_at: number;
  trust_level: 'high' | 'medium' | 'low';
  signals: Array<{ key: string; state: string }>;
  user: { user_id: number; email: string | null; last_login_at: number };
  sessions: Array<{ device: string; browser: string; last_activity_at: number; type: string; locked: boolean; known: boolean }>;
  messages: Msg[];
}

const SIGNAL_LABELS: Record<string, [string, string]> = {
  session: ['Session connue', 'Known session'],
  device: ['Appareil connu', 'Known device'],
  browser: ['Navigateur similaire', 'Similar browser'],
  history: ['Historique cohérent', 'Consistent history'],
  network: ['Réseau / IP similaire', 'Similar network / IP'],
  new_device: ['Nouvel appareil inconnu', 'New unknown device'],
};
const signalMark = (state: string) =>
  state === 'match'
    ? { sym: '✓', cls: 'text-[#32D583]' }
    : state === 'partial'
    ? { sym: '~', cls: 'text-[#FEC84B]' }
    : state === 'negative'
    ? { sym: '✗', cls: 'text-[#F97066]' }
    : { sym: '–', cls: 'text-[#6E7B88]' };

const TRUST_TEXT: Record<string, [string, string, string]> = {
  high: ['Confiance élevée', 'High confidence', 'Signaux cohérents avec l’historique du compte.'],
  medium: ['Confiance moyenne', 'Medium confidence', 'Certains éléments correspondent, pas suffisamment.'],
  low: ['Confiance faible', 'Low confidence', 'Nouvel appareil ou informations incohérentes.'],
};
const trustCls = (l: string) =>
  l === 'high' ? 'text-[#32D583] border-[#20C997]/40 bg-[#20C997]/10' : l === 'medium' ? 'text-[#FEC84B] border-[#F79009]/40 bg-[#F79009]/10' : 'text-[#F97066] border-[#F04438]/40 bg-[#F04438]/10';

const SignalList: React.FC<{ lang: Lang; signals: Array<{ key: string; state: string }> }> = ({ lang, signals }) => (
  <ul className="space-y-0.5 text-xs">
    {signals.map((s) => {
      const m = signalMark(s.state);
      const l = SIGNAL_LABELS[s.key] || [s.key, s.key];
      return (
        <li key={s.key} className="flex items-center gap-2">
          <span className={`w-4 text-center font-bold ${m.cls}`} aria-hidden="true">
            {m.sym}
          </span>
          <span className="text-[#B6C0C9]">{tr(lang, l[0], l[1])}</span>
        </li>
      );
    })}
  </ul>
);

type AdminAction = 'approve' | 'reject' | 'info' | 'revoke' | null;

export const AdminRecoveryPanel: React.FC<{
  lang: Lang;
  onToast: (text: string, type: 'success' | 'error' | 'info') => void;
}> = ({ lang, onToast }) => {
  const [filter, setFilter] = useState('');
  const [items, setItems] = useState<AdminListItem[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [action, setAction] = useState<AdminAction>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionOk, setActionOk] = useState<string | null>(null);
  const [revokeOthers, setRevokeOthers] = useState(true);
  const [reason, setReason] = useState('');
  const [infoMsg, setInfoMsg] = useState('');
  const [adminMsg, setAdminMsg] = useState('');
  // Affiché UNE seule fois, jamais conservé après fermeture ou changement de demande.
  const [tempReveal, setTempReveal] = useState<{ password: string; expires_at: number; request: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const res = await apiFetch(`/api/admin/recovery/requests${filter ? `?status=${encodeURIComponent(filter)}` : ''}`);
      setItems(res.requests || []);
    } catch (err) {
      setListError(friendlyError(lang, err, 'Impossible de charger les demandes.', 'Unable to load requests.'));
    } finally {
      setLoading(false);
    }
  }, [filter, lang]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const loadDetail = useCallback(
    async (id: string) => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const res = await apiFetch(`/api/admin/recovery/request?id=${encodeURIComponent(id)}`);
        setDetail(res.request);
      } catch (err) {
        setDetailError(friendlyError(lang, err, 'Impossible de charger cette demande.', 'Unable to load this request.'));
      } finally {
        setDetailLoading(false);
      }
    },
    [lang]
  );

  const openRequest = async (id: string) => {
    setSelected(id);
    setDetail(null);
    setAction(null);
    setActionError(null);
    setActionOk(null);
    setTempReveal(null);
    setCopied(false);
    await loadDetail(id);
    // Passer en « en cours d'examen » (sans effet si déjà traitée).
    apiFetch('/api/admin/recovery/review', { method: 'POST', body: JSON.stringify({ id }) })
      .then(() => {
        loadDetail(id);
        loadList();
      })
      .catch(() => undefined);
  };

  const run = async (path: string, body: Record<string, unknown>, okMsg: string) => {
    if (!selected) return null;
    setBusy(true);
    setActionError(null);
    setActionOk(null);
    try {
      const res = await apiFetch(`/api/admin/recovery/${path}`, { method: 'POST', body: JSON.stringify({ id: selected, ...body }) });
      setActionOk(okMsg);
      onToast(okMsg, 'success');
      setAction(null);
      await Promise.all([loadDetail(selected), loadList()]);
      return res;
    } catch (err) {
      setActionError(friendlyError(lang, err, 'Action impossible pour le moment. Rien n’a été modifié.', 'Action not possible right now. Nothing was changed.'));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    const res = await run('approve', { confirm: true, revoke_sessions: revokeOthers }, tr(lang, 'Récupération approuvée.', 'Recovery approved.'));
    if (res?.temp_password) setTempReveal({ password: res.temp_password, expires_at: res.expires_at, request: selected || '' });
  };

  const copyTemp = async () => {
    if (!tempReveal) return;
    try {
      await navigator.clipboard.writeText(tempReveal.password);
      setCopied(true);
    } catch {
      setCopied(false);
      onToast(tr(lang, 'Copie impossible : recopiez le mot de passe manuellement.', 'Copy failed: copy the password manually.'), 'error');
    }
  };

  const sendAdminMessage = async () => {
    if (!adminMsg.trim()) return;
    const ok = await run('message', { body: adminMsg.trim() }, tr(lang, 'Message envoyé.', 'Message sent.'));
    if (ok) setAdminMsg('');
  };

  const closed = detail ? ['approved', 'rejected', 'expired', 'completed'].includes(detail.status) : true;
  const actionBox = 'p-3 rounded-lg bg-[#080C0F] border border-white/15 space-y-3';

  return (
    <div className="bg-[#0D1318] border border-white/[0.07] rounded-xl p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display font-semibold text-base text-[#E8EEF2] flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-[#20C997]" />
            {tr(lang, 'Récupération de comptes', 'Account recovery')}
          </h3>
          <p className="text-[11px] text-[#6E7B88] mt-0.5">
            {tr(lang, 'Demandes de mot de passe oublié à examiner. Vous gardez la décision finale.', 'Forgotten-password requests to review. You make the final decision.')}
          </p>
        </div>
        <button
          type="button"
          onClick={loadList}
          disabled={loading}
          aria-label={tr(lang, 'Actualiser', 'Refresh')}
          className="p-2 rounded-lg bg-[#080C0F] border border-white/10 text-[#8B98A4] hover:text-[#E8EEF2] disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <select
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        aria-label={tr(lang, 'Filtrer par statut', 'Filter by status')}
        className="w-full sm:w-auto px-3 py-2 text-sm bg-[#080C0F] border border-white/10 rounded-lg text-[#E8EEF2]"
      >
        <option value="">{tr(lang, 'Tous les statuts', 'All statuses')}</option>
        {Object.keys(STATUS_LABELS).map((k) => (
          <option key={k} value={k}>
            {statusLabel(lang, k)}
          </option>
        ))}
      </select>

      {listError && <ErrorBox>{listError}</ErrorBox>}
      {items && items.length === 0 && <p className="text-xs text-[#8B98A4]">{tr(lang, 'Aucune demande.', 'No requests.')}</p>}

      <ul className="space-y-2">
        {(items || []).map((it) => {
          const tt = TRUST_TEXT[it.trust_level] || TRUST_TEXT.low;
          return (
            <li key={it.id}>
              <button
                type="button"
                onClick={() => openRequest(it.id)}
                className={`w-full text-left p-3 rounded-lg border transition-colors ${
                  selected === it.id ? 'bg-[#172129] border-[#20C997]/50' : 'bg-[#080C0F] border-white/10 hover:border-white/25'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-[#E8EEF2]">#{it.id}</span>
                  <StatusBadge lang={lang} status={it.status} />
                </div>
                <div className="text-xs text-[#B6C0C9] mt-1 break-all">{it.email}</div>
                <div className="text-[11px] text-[#6E7B88] mt-0.5 flex flex-wrap gap-x-2">
                  <span>{relativeTime(lang, it.created_at)}</span>
                  <span className={`px-1.5 rounded border ${trustCls(it.trust_level)}`}>{tr(lang, tt[0], tt[1])}</span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>

      {selected && (
        <div className="border-t border-white/10 pt-4 space-y-4" aria-live="polite">
          {detailLoading && !detail && (
            <div className="text-xs text-[#8B98A4] flex items-center gap-2" role="status">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" /> {tr(lang, 'Chargement…', 'Loading…')}
            </div>
          )}
          {detailError && <ErrorBox>{detailError}</ErrorBox>}
          {detail && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="font-display font-semibold text-sm text-[#E8EEF2]">#{detail.id}</h4>
                <StatusBadge lang={lang} status={detail.status} />
              </div>

              <div className="text-xs text-[#B6C0C9] space-y-0.5">
                <div className="break-all">
                  {tr(lang, 'Compte : ', 'Account: ')}
                  <span className="text-[#E8EEF2]">{detail.user.email}</span> (ID {detail.user.user_id})
                </div>
                <div>
                  {tr(lang, 'Créée : ', 'Created: ')}
                  {fmt(detail.created_at)} · {tr(lang, 'Dernière connexion : ', 'Last sign-in: ')}
                  {detail.user.last_login_at ? relativeTime(lang, detail.user.last_login_at) : '—'}
                </div>
              </div>

              <div className={`p-3 rounded-lg border ${trustCls(detail.trust_level)}`}>
                <div className="text-xs font-semibold">{tr(lang, TRUST_TEXT[detail.trust_level][0], TRUST_TEXT[detail.trust_level][1])}</div>
                <div className="text-[11px] opacity-90">{TRUST_TEXT[detail.trust_level][2]}</div>
              </div>
              <SignalList lang={lang} signals={detail.signals} />
              <p className="text-[11px] text-[#6E7B88] leading-relaxed">
                {tr(
                  lang,
                  'Ces signaux sont des indices de cohérence, pas une preuve d’identité : une IP, un navigateur ou un appareil peuvent être partagés ou imités.',
                  'These signals are consistency hints, not proof of identity: an IP, browser or device can be shared or imitated.'
                )}
              </p>

              <div>
                <div className="text-xs font-semibold text-[#E8EEF2] mb-1.5">{tr(lang, 'Sessions connues', 'Known sessions')}</div>
                {detail.sessions.length === 0 && <p className="text-xs text-[#8B98A4]">{tr(lang, 'Aucune session enregistrée.', 'No recorded session.')}</p>}
                <ul className="space-y-1.5">
                  {detail.sessions.map((s, i) => (
                    <li key={i} className="text-xs p-2 rounded-lg bg-[#080C0F] border border-white/10">
                      <div className="text-[#E8EEF2]">
                        {/iPhone|iPad|Android/i.test(s.device) ? '📱' : '💻'} {s.device} • {s.browser}
                      </div>
                      <div className="text-[11px] text-[#8B98A4]">
                        {tr(lang, 'Dernière activité : ', 'Last activity: ')}
                        {relativeTime(lang, s.last_activity_at)} · {tr(lang, 'Même appareil que la demande : ', 'Same device as the request: ')}
                        {s.known ? '✓' : '–'}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold text-[#E8EEF2]">{tr(lang, 'Échanges', 'Messages')}</div>
                <MessageThread lang={lang} messages={detail.messages.map((m) => ({ ...m }))} youAre="admin" />
                {!closed && (
                  <div className="space-y-2">
                    <textarea
                      value={adminMsg}
                      onChange={(e) => setAdminMsg(e.target.value)}
                      rows={2}
                      maxLength={1000}
                      disabled={busy}
                      placeholder={tr(lang, 'Message à l’utilisateur…', 'Message to the user…')}
                      className={inputCls}
                    />
                    <button type="button" onClick={sendAdminMessage} disabled={busy || !adminMsg.trim()} className={secondaryBtn}>
                      {tr(lang, 'Envoyer', 'Send')}
                    </button>
                    <p className="text-[11px] text-[#6E7B88]">
                      {tr(lang, 'Ne jamais écrire le mot de passe temporaire dans ces échanges.', 'Never write the temporary password in these messages.')}
                    </p>
                  </div>
                )}
              </div>

              {/* Actions, avec feedback à proximité */}
              <div className="space-y-3">
                {actionError && <ErrorBox>{actionError}</ErrorBox>}
                {actionOk && !tempReveal && <SuccessBox>{actionOk}</SuccessBox>}

                {tempReveal && tempReveal.request === detail.id && (
                  <div className="p-4 rounded-lg bg-[#20C997]/10 border border-[#20C997]/50 space-y-3" role="alert">
                    <div className="text-xs font-semibold text-[#32D583]">
                      {tr(lang, 'Mot de passe temporaire — affiché une seule fois', 'Temporary password — shown only once')}
                    </div>
                    <div className="font-mono text-lg tracking-wider text-[#E8EEF2] break-all select-all">{tempReveal.password}</div>
                    <div className="text-[11px] text-[#B6C0C9]">
                      {tr(lang, 'Valable jusqu’au ', 'Valid until ')}
                      {fmt(tempReveal.expires_at)}. {tr(lang, 'Transmettez-le à l’utilisateur par un canal de votre choix : il ne sera plus récupérable.', 'Give it to the user through a channel of your choice: it can no longer be retrieved.')}
                    </div>
                    <div className="flex gap-2">
                      <button type="button" onClick={copyTemp} className={secondaryBtn}>
                        {copied ? tr(lang, 'Copié ✓', 'Copied ✓') : tr(lang, 'Copier', 'Copy')}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setTempReveal(null);
                          setCopied(false);
                        }}
                        className={primaryBtn}
                      >
                        {tr(lang, 'J’ai noté le mot de passe', 'I have noted the password')}
                      </button>
                    </div>
                  </div>
                )}

                {!closed && action === null && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <button type="button" onClick={() => { setAction('approve'); setActionOk(null); setActionError(null); }} className="py-3 sm:py-2.5 text-sm font-semibold rounded-lg bg-[#20C997] text-[#080C0F] hover:bg-[#1AA67D]">
                      ✅ {tr(lang, 'Approuver', 'Approve')}
                    </button>
                    <button type="button" onClick={() => { setAction('reject'); setActionOk(null); setActionError(null); }} className="py-3 sm:py-2.5 text-sm font-semibold rounded-lg border border-[#F04438]/50 text-[#F97066] hover:bg-[#F04438]/10">
                      ❌ {tr(lang, 'Refuser', 'Reject')}
                    </button>
                    <button type="button" onClick={() => { setAction('info'); setActionOk(null); setActionError(null); }} className="py-3 sm:py-2.5 text-sm font-semibold rounded-lg border border-[#F79009]/50 text-[#FEC84B] hover:bg-[#F79009]/10">
                      ⚠️ {tr(lang, 'Vérification', 'More verification')}
                    </button>
                  </div>
                )}

                {action === 'approve' && (
                  <div className={actionBox}>
                    <p className="text-sm text-[#E8EEF2] font-semibold">{tr(lang, 'Approuver cette demande ?', 'Approve this request?')}</p>
                    <p className="text-xs text-[#B6C0C9] leading-relaxed">
                      {tr(lang, 'Un mot de passe temporaire sera généré et toutes les protections prévues seront appliquées (expiration courte, changement obligatoire).', 'A temporary password will be generated and all planned protections will apply (short expiry, mandatory change).')}
                    </p>
                    <label className="flex items-start gap-2 text-xs text-[#B6C0C9]">
                      <input type="checkbox" checked={revokeOthers} onChange={(e) => setRevokeOthers(e.target.checked)} disabled={busy} className="mt-0.5" />
                      {tr(lang, 'Déconnecter toutes les autres sessions une fois le nouveau mot de passe choisi', 'Sign out all other sessions once the new password is chosen')}
                    </label>
                    <div className="flex gap-2">
                      <button type="button" onClick={approve} disabled={busy} className={primaryBtn}>
                        {busy ? tr(lang, 'Génération…', 'Generating…') : tr(lang, 'Confirmer l’approbation', 'Confirm approval')}
                      </button>
                      <button type="button" onClick={() => setAction(null)} disabled={busy} className={secondaryBtn}>
                        {tr(lang, 'Annuler', 'Cancel')}
                      </button>
                    </div>
                  </div>
                )}

                {action === 'reject' && (
                  <div className={actionBox}>
                    <p className="text-sm text-[#E8EEF2] font-semibold">{tr(lang, 'Refuser cette demande ?', 'Reject this request?')}</p>
                    <input
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      maxLength={300}
                      disabled={busy}
                      placeholder={tr(lang, 'Motif (visible par l’utilisateur, facultatif)', 'Reason (visible to the user, optional)')}
                      className={inputCls}
                    />
                    <div className="flex gap-2">
                      <button type="button" onClick={() => run('reject', { confirm: true, reason }, tr(lang, 'Demande refusée.', 'Request rejected.'))} disabled={busy} className="w-full py-3 sm:py-2.5 text-sm font-semibold rounded-lg bg-[#F04438] text-white disabled:opacity-50">
                        {busy ? '…' : tr(lang, 'Confirmer le refus', 'Confirm rejection')}
                      </button>
                      <button type="button" onClick={() => setAction(null)} disabled={busy} className={secondaryBtn}>
                        {tr(lang, 'Annuler', 'Cancel')}
                      </button>
                    </div>
                  </div>
                )}

                {action === 'info' && (
                  <div className={actionBox}>
                    <p className="text-sm text-[#E8EEF2] font-semibold">{tr(lang, 'Demander une vérification supplémentaire ?', 'Ask for additional verification?')}</p>
                    <textarea
                      value={infoMsg}
                      onChange={(e) => setInfoMsg(e.target.value)}
                      rows={3}
                      maxLength={1000}
                      disabled={busy}
                      placeholder={tr(lang, 'Que doit préciser l’utilisateur ?', 'What should the user clarify?')}
                      className={inputCls}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={async () => {
                          const ok = await run('request-info', { confirm: true, message: infoMsg.trim() }, tr(lang, 'Vérification demandée.', 'Verification requested.'));
                          if (ok) setInfoMsg('');
                        }}
                        disabled={busy || !infoMsg.trim()}
                        className={primaryBtn}
                      >
                        {busy ? '…' : tr(lang, 'Envoyer la demande', 'Send request')}
                      </button>
                      <button type="button" onClick={() => setAction(null)} disabled={busy} className={secondaryBtn}>
                        {tr(lang, 'Annuler', 'Cancel')}
                      </button>
                    </div>
                  </div>
                )}

                {action === 'revoke' ? (
                  <div className={actionBox}>
                    <p className="text-sm text-[#E8EEF2] font-semibold">{tr(lang, 'Déconnecter toutes les sessions de ce compte ?', 'Sign out all sessions of this account?')}</p>
                    <div className="flex gap-2">
                      <button type="button" onClick={() => run('revoke-sessions', { confirm: true }, tr(lang, 'Sessions révoquées.', 'Sessions revoked.'))} disabled={busy} className="w-full py-3 sm:py-2.5 text-sm font-semibold rounded-lg bg-[#F04438] text-white disabled:opacity-50">
                        {busy ? '…' : tr(lang, 'Oui, déconnecter', 'Yes, sign out')}
                      </button>
                      <button type="button" onClick={() => setAction(null)} disabled={busy} className={secondaryBtn}>
                        {tr(lang, 'Annuler', 'Cancel')}
                      </button>
                    </div>
                  </div>
                ) : (
                  action === null && (
                    <button type="button" onClick={() => { setAction('revoke'); setActionOk(null); setActionError(null); }} className="w-full py-2.5 text-xs font-semibold rounded-lg border border-white/15 text-[#B6C0C9] hover:bg-white/5">
                      {tr(lang, 'Déconnecter toutes les sessions du compte', 'Sign out all sessions of the account')}
                    </button>
                  )
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
