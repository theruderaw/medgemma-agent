import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { fetchRecentChats } from '../../lib/api';
import type { RecentChat } from '../../types';
import ChatListItem from './ChatListItem';

interface Props {
    sessionId: string | null;
    onPick: (sessionId: string) => void;
}

export default function ChatList({ sessionId, onPick }: Props) {
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

    return (
        <>
            <div className="mt-4 flex items-center justify-between px-4 pb-1">
                <span className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                    All chats
                </span>
                <button
                    type="button"
                    onClick={refresh}
                    aria-label="Refresh chat list"
                    className="cursor-pointer rounded p-1 text-neutral-500 transition-colors hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
                >
                    <RefreshCw
                        className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`}
                        aria-hidden="true"
                    />
                </button>
            </div>

            <div className="px-3 pb-2">
                <input
                    type="search"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    placeholder="Filter chats…"
                    aria-label="Filter chats"
                    className="w-full rounded-lg border border-neutral-300 bg-white px-2.5 py-1.5 text-sm placeholder:text-neutral-500 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:placeholder:text-neutral-400 dark:focus:border-neutral-400"
                />
            </div>

            <nav className="flex-1 overflow-y-auto px-2 pb-4" aria-label="All chats">
                {!chats && (
                    <p className="m-0 px-2 py-2 text-xs text-neutral-500 dark:text-neutral-400">Loading…</p>
                )}
                {chats?.length === 0 && (
                    <p className="m-0 px-2 py-2 text-sm leading-relaxed text-neutral-500 dark:text-neutral-400">
                        No chats yet. Start one above — every conversation is kept here.
                    </p>
                )}
                {chats != null && chats.length > 0 && filtered.length === 0 && (
                    <p className="m-0 px-2 py-2 text-sm italic text-neutral-500 dark:text-neutral-400">
                        No chats match.
                    </p>
                )}
                {filtered.map((chat) => (
                    <ChatListItem
                        key={chat.session_id}
                        chat={chat}
                        active={chat.session_id === sessionId}
                        onClick={() => onPick(chat.session_id)}
                    />
                ))}
            </nav>
        </>
    );
}
