import { useCallback, useEffect, useState } from 'react';
import { fetchRecentChats } from '../../lib/api';
import type { RecentChat } from '../../types';

interface Props {
  sessionId: string | null;
  /** Mobile drawer visibility; ignored ≥ md where the rail is static. */
  open: boolean;
  onClose: () => void;
  onOpenChat: (sessionId: string) => void;
  onNewChat: () => void;
}

function timeAgo(ts: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/**
 * Persistent left rail: brand, New chat, and the most recently active
 * conversations (GET /v1/sessions/recent). Static column on desktop,
 * slide-over drawer on small screens.
 */
export default function Sidebar({ sessionId, open, onClose, onOpenChat, onNewChat }: Props) {
  const [chats, setChats] = useState<RecentChat[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(() => {
    setRefreshing(true);
    fetchRecentChats(30)
      .then(setChats)
      .catch(() => setChats([]))
      .finally(() => setRefreshing(false));
  }, []);

  // Initial load + reload whenever the active session changes (first turn of
  // a new chat registers it; a switched-away chat stays listed).
  useEffect(() => {
    refresh();
  }, [refresh, sessionId]);

  // Escape closes the mobile drawer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const pick = (id: string) => {
    onClose();
    onOpenChat(id);
  };

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden" onClick={onClose} />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-ink-800 bg-ink-950 transition-transform duration-200 md:static md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Conversations"
      >
        <div className="flex items-center gap-2 px-4 pb-2 pt-4">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-accent-400 shadow-[0_0_12px] shadow-accent-400/60" />
          <h1 className="m-0 text-base font-semibold tracking-tight">MedGemma Agent</h1>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="ml-auto cursor-pointer rounded p-1 text-slate-500 hover:text-slate-300 md:hidden"
          >
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
              <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <p className="m-0 px-4 pb-3 text-[11px] text-slate-600">
          Qwen router · MedGemma specialist · safety floor
        </p>

        <div className="px-3">
          <button
            type="button"
            onClick={() => {
              onClose();
              onNewChat();
            }}
            className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border border-accent-500/30 bg-accent-900/30 px-3 py-2 text-sm font-medium text-accent-300 transition-colors hover:border-accent-500/60 hover:bg-accent-900/50"
          >
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
              <path d="M10 4v12M4 10h12" strokeLinecap="round" />
            </svg>
            New chat
          </button>
        </div>

        <div className="mt-4 flex items-center justify-between px-4 pb-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">
            Recent
          </span>
          <button
            type="button"
            onClick={refresh}
            aria-label="Refresh recent chats"
            className="cursor-pointer rounded p-1 text-slate-600 transition-colors hover:text-slate-300"
          >
            <svg
              viewBox="0 0 20 20"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`}
              aria-hidden="true"
            >
              <path d="M16 10a6 6 0 1 1-1.76-4.24M16 3v3h-3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4" aria-label="Recent chats">
          {!chats && (
            <p className="m-0 px-2 py-2 text-xs text-slate-600">Loading…</p>
          )}
          {chats?.length === 0 && (
            <p className="m-0 px-2 py-2 text-xs leading-relaxed text-slate-600">
              No recent chats yet. Start one above — conversations appear here.
            </p>
          )}
          {chats?.map((chat) => (
            <button
              key={chat.session_id}
              type="button"
              onClick={() => pick(chat.session_id)}
              aria-current={chat.session_id === sessionId ? 'page' : undefined}
              title={chat.preview ?? undefined}
              className={`mb-0.5 block w-full cursor-pointer rounded-lg px-3 py-2 text-left transition-colors ${
                chat.session_id === sessionId
                  ? 'bg-accent-900/40 shadow-[inset_2px_0_0] shadow-accent-400'
                  : 'hover:bg-ink-850'
              }`}
            >
              <p className="m-0 line-clamp-2 break-words text-xs leading-snug text-slate-300">
                {chat.preview ?? '(no messages)'}
              </p>
              <p className="m-0 mt-1 flex items-center gap-1.5 text-[10px] text-slate-600">
                <span className="font-mono">{chat.session_id.slice(0, 8)}</span>
                <span>·</span>
                <span>{timeAgo(chat.last_activity)}</span>
                <span className="ml-auto">{chat.message_count} msg</span>
              </p>
            </button>
          ))}
        </nav>
      </aside>
    </>
  );
}
