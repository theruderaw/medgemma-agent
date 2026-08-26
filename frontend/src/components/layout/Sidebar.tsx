import { useEffect } from 'react';
import { X } from 'lucide-react';
import NewButton from '../sidebar/NewButton';
import ChatList from '../sidebar/ChatList';

interface Props {
    sessionId: string | null;
    /** Mobile drawer visibility; ignored ≥ md where the rail is static. */
    open: boolean;
    onClose: () => void;
    onOpenChat: (sessionId: string) => void;
    onNewChat: () => void;
}

/**
 * Persistent left rail: brand, New chat, and every past conversation.
 * Static column on desktop, slide-over drawer on small screens. All list
 * state lives in ChatList.
 */
export default function Sidebar({ sessionId, open, onClose, onOpenChat, onNewChat }: Props) {
    // Escape closes the mobile drawer.
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [open, onClose]);

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
                    <h1 className="m-0 text-lg font-semibold tracking-tight">MedGemma Agent</h1>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close menu"
                        className="ml-auto cursor-pointer rounded p-1 text-neutral-500 hover:text-neutral-800 md:hidden dark:hover:text-neutral-200"
                    >
                        <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                </div>
                <p className="m-0 px-4 pb-3 text-xs text-neutral-500 dark:text-neutral-400">
                    Qwen router · MedGemma specialist · safety floor
                </p>

                <NewButton onClick={() => { onClose(); onNewChat(); }} />
                <ChatList sessionId={sessionId} onPick={(id) => { onClose(); onOpenChat(id); }} />
            </aside>
        </>
    );
}
