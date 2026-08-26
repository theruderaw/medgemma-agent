import { useState } from 'react';
import type { AttachedImage } from '../../types';
import type { ChatMessage } from '../../hooks/useConversation';
import type { Online } from '../../hooks/useHealth';
import Header from './Header';
import StatusDisplay from './StatusDisplay';
import ChatView from '../chat/ChatView';
import LogsPanel from '../logs/LogsPanel';

export type View = 'chat' | 'logs';

const TABS: { id: View; label: string }[] = [
    { id: 'chat', label: 'Chat' },
    { id: 'logs', label: 'Logs' },
];

interface Props {
    sessionId: string | null;
    online: Online;
    messages: ChatMessage[];
    busy: boolean;
    expandedSteps: Record<string, boolean>;
    onSend: (text: string, image?: AttachedImage, triage?: boolean, tool?: string) => void;
    onToggleStep: (key: string) => void;
    onMenu: () => void;
    onOpenChat: (id: string) => void;
    onNewChat: () => void;
}

export default function Layout({
    sessionId,
    online,
    messages,
    busy,
    expandedSteps,
    onSend,
    onToggleStep,
    onMenu,
}: Props) {
    const [view, setView] = useState<View>('chat');

    return (
        <div className="flex min-w-0 flex-1 flex-col">
            <Header onMenu={onMenu} />
            <div className="flex items-center justify-between border-b border-neutral-200 bg-white/70 px-5 py-2 backdrop-blur dark:border-neutral-800 dark:bg-neutral-900/70">
                <nav className="flex rounded-full border border-neutral-300 p-0.5 dark:border-neutral-700" aria-label="Views">
                    {TABS.map((t) => (
                        <button
                            key={t.id}
                            type="button"
                            onClick={() => setView(t.id)}
                            aria-current={view === t.id ? 'page' : undefined}
                            className={`cursor-pointer rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                                view === t.id
                                    ? 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900'
                                    : 'text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200'
                            }`}
                        >
                            {t.label}
                        </button>
                    ))}
                </nav>
                <StatusDisplay sessionId={sessionId} online={online} />
            </div>
            {view === 'chat' && (
                <ChatView
                    messages={messages}
                    busy={busy}
                    sessionId={sessionId}
                    onSend={onSend}
                    expandedSteps={expandedSteps}
                    onToggleStep={onToggleStep}
                />
            )}
            {view === 'logs' && <LogsPanel sessionId={sessionId} />}
        </div>
    );
}
