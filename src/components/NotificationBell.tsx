import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { apiFetch } from '../api';
import { tr, translateMessage } from '../i18n';

interface NotificationItem {
  id: number;
  created_at: number;
  kind: string;
  text: string;
  read: boolean;
}

/**
 * Cloche de notifications du site. Alimentée par le serveur (position fermée, alerte de prix, mode sécurité,
 * rapports...) que le bot Telegram tourne ou non : le site ne dépend pas de Telegram pour informer l'utilisateur.
 */
export const NotificationBell: React.FC<{ lang: string }> = ({ lang }) => {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await apiFetch('/api/notifications?limit=30');
      setItems(res.items || []);
      setUnread(res.unread || 0);
    } catch {
      // Erreur ponctuelle : on garde l'état précédent (pas de fausse alerte).
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(() => {
      if (!document.hidden) load();
    }, 60000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next) {
      await load();
      if (unread > 0) {
        try {
          await apiFetch('/api/notifications/read', { method: 'POST', body: JSON.stringify({}) });
          setUnread(0);
          setItems((prev) => prev.map((n) => ({ ...n, read: true })));
        } catch {
          // non bloquant
        }
      }
    }
  };

  return (
    <div className="relative" ref={box}>
      <button
        type="button"
        onClick={toggle}
        className="relative p-1.5 rounded-lg bg-[#080C0F] border border-white/10 text-[#8B98A4] hover:text-[#E8EEF2]"
        aria-label={tr(lang, 'Notifications', 'Notifications')}
        title={tr(lang, 'Notifications', 'Notifications')}
      >
        <Bell className="w-3.5 h-3.5" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[14px] h-[14px] px-1 rounded-full bg-[#F04438] text-[9px] leading-[14px] text-white text-center font-mono-tabular">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div
          className="absolute right-0 mt-2 w-[min(340px,90vw)] max-h-[60vh] overflow-y-auto z-50 rounded-xl bg-[#0D1318] border border-white/10 shadow-xl"
          role="dialog"
          aria-label={tr(lang, 'Notifications', 'Notifications')}
        >
          {items.length === 0 ? (
            <div className="p-4 text-xs text-[#8B98A4]">{tr(lang, 'Aucune notification pour le moment.', 'No notifications yet.')}</div>
          ) : (
            items.map((n) => (
              <div key={n.id} className={`px-3 py-2.5 border-b border-white/[0.05] ${n.read ? '' : 'bg-[#20C997]/5'}`}>
                <div className="text-xs text-[#E8EEF2] whitespace-pre-line break-words">{translateMessage(n.text)}</div>
                <div className="mt-1 text-[10px] text-[#6E7B88] font-mono-tabular">{new Date(n.created_at * 1000).toLocaleString()}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
