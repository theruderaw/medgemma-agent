import { useCallback, useEffect, useMemo, useState } from 'react';
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
 * Persistent left rail: brand, New chat, and every past conversation
 * (GET /v1/sessions/recent) with a client-side filter. Static column on
 * desktop, slide-over drawer on small screens.
 */
export default function Sidebar({ sessionId, open, onClose, onOpenChat, onNewChat }: Props) {
  const [chats, setChats] = useState<RecentChat[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState('');

  const refresh = useCallback(() => {
    setRefreshing(true);
    fetchRecentChats(100)
      .then(setChats)
      .catch(() => setChats([]))
      .finally(() => setRefreshing(false));
  }, []);

  // Initial load + reload whenever the active session changes (first turn of
  // a new chat registers it; a switched-away chat stays listed).
  useEffect(() => {
    refresh();
  }, [refresh, sessionId]);

  /** Case-insensitive match on preview text or session id. */
  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!chats) return [];
    if (!q) return chats;
    return chats.filter(
      (c) => (c.preview ?? '').toLowerCase().includes(q) || c.session_id.includes(q),
    );
  }, [chats, filter]);

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
        className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col border-r border-neutral-200 bg-white transition-transform duration-200 md:static md:translate-x-0 dark:border-neutral-800 dark:bg-neutral-950 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Conversations"
      >
        <div className="flex items-center gap-2 px-4 pb-2 pt-4">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-neutral-900 shadow-[0_0_12px] shadow-neutral-400/70 dark:bg-neutral-100 dark:shadow-neutral-500/60" />
          <h1 className="m-0 text-base font-semibold tracking-tight">MedGemma Agent</h1>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="ml-auto cursor-pointer rounded p-1 text-neutral-500 hover:text-neutral-800 md:hidden dark:hover:text-neutral-200"
          >
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
              <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <p className="m-0 px-4 pb-3 text-[11px] text-neutral-500 dark:text-neutral-400">
          Qwen router · MedGemma specialist · safety floor
        </p>

        <div className="px-3">
          <button
            type="button"
            onClick={() => {
              onClose();
              onNewChat();
            }}
            className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border border-neutral-300 bg-neutral-100 px-3 py-2 text-sm font-medium text-neutral-800 transition-colors hover:border-neutral-400 hover:bg-neutral-200 dark:border-neutral-700 dark:bg-neutral-800/60 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
              <path d="M10 4v12M4 10h12" strokeLinecap="round" />
            </svg>
            New chat
          </button>
        </div>

        <div className="mt-4 flex items-center justify-between px-4 pb-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
            All chats
          </span>
          <button
            type="button"
            onClick={refresh}
            aria-label="Refresh chat list"
            className="cursor-pointer rounded p-1 text-neutral-500 transition-colors hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
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

        <div className="px-3 pb-2">
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter chats…"
            aria-label="Filter chats"
            className="w-full rounded-lg border border-neutral-300 bg-white px-2.5 py-1.5 text-xs placeholder:text-neutral-500 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:placeholder:text-neutral-400 dark:focus:border-neutral-400"
          />
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4" aria-label="All chats">
          {!chats && (
            <p className="m-0 px-2 py-2 text-xs text-neutral-500 dark:text-neutral-400">Loading…</p>
          )}
          {chats?.length === 0 && (
            <p className="m-0 px-2 py-2 text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">
              No chats yet. Start one above — every conversation is kept here.
            </p>
          )}
          {chats != null && chats.length > 0 && filtered.length === 0 && (
            <p className="m-0 px-2 py-2 text-xs italic text-neutral-500 dark:text-neutral-400">
              No chats match.
            </p>
          )}
          {filtered.map((chat) => (
            <button
              key={chat.session_id}
              type="button"
              onClick={() => pick(chat.session_id)}
              aria-current={chat.session_id === sessionId ? 'page' : undefined}
              title={chat.preview ?? undefined}
              className={`mb-0.5 block w-full cursor-pointer rounded-lg px-3 py-2 text-left transition-colors ${
                chat.session_id === sessionId
                  ? 'bg-neutral-100 shadow-[inset_2px_0_0] shadow-neutral-900 dark:bg-neutral-800/60 dark:shadow-neutral-300'
                  : 'hover:bg-neutral-100 dark:hover:bg-neutral-900'
              }`}
            >
              <p className="m-0 line-clamp-2 break-words text-xs leading-snug text-neutral-700 dark:text-neutral-300">
                {chat.preview ?? '(no messages)'}
              </p>
              <p className="m-0 mt-1 flex items-center gap-1.5 text-[10px] text-neutral-400 dark:text-neutral-500">
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
