import type { RecentChat } from '../../types';

interface Props {
    chat: RecentChat;
    active: boolean;
    onClick: () => void;
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

export default function ChatListItem({ chat, active, onClick }: Props) {
    return (
        <button
            type="button"
            onClick={onClick}
            aria-current={active ? 'page' : undefined}
            title={chat.preview ?? undefined}
            className={`mb-0.5 block w-full cursor-pointer rounded-lg px-3 py-2 text-left transition-colors ${
                active
                    ? 'bg-neutral-100 shadow-[inset_2px_0_0] shadow-neutral-900 dark:bg-neutral-800/60 dark:shadow-neutral-300'
                    : 'hover:bg-neutral-100 dark:hover:bg-neutral-900'
            }`}
        >
            <p className="m-0 line-clamp-2 break-words text-sm leading-snug text-neutral-700 dark:text-neutral-300">
                {chat.preview ?? '(no messages)'}
            </p>
            <p className="m-0 mt-1 flex items-center gap-1.5 text-xs text-neutral-400 dark:text-neutral-500">
                <span className="font-mono">{chat.session_id.slice(0, 8)}</span>
                <span>·</span>
                <span>{timeAgo(chat.last_activity)}</span>
                <span className="ml-auto">{chat.message_count} msg</span>
            </p>
        </button>
    );
}
