import { useState } from 'react';
import { Settings } from 'lucide-react';
import type { Online } from '../../hooks/useHealth';
import ThemeToggle from '../ui/ThemeToggle';
import SettingsDropdown from './SettingsDropdown';

function statusLabel(online: Online): string {
    return online === null ? 'checking…' : online ? 'online' : 'offline';
}

interface Props {
    sessionId: string | null;
    online: Online;
}

export default function StatusDisplay({ sessionId, online }: Props) {
    const [open, setOpen] = useState(false);

    return (
        <div className="relative flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400">
                <span className={`h-2 w-2 rounded-full ${online === false ? 'bg-neutral-400' : 'bg-neutral-800 dark:bg-neutral-200'}`} />
                {statusLabel(online)}
            </span>

            {sessionId && (
                <span
                    title={sessionId}
                    className="inline-flex shrink-0 items-center rounded-full border border-neutral-200 bg-transparent px-2 py-0.5 font-mono text-xs font-medium normal-case tracking-wider text-neutral-400 dark:border-neutral-800 dark:text-neutral-500"
                >
                    session {sessionId.slice(0, 8)}
                </span>
            )}

            <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                aria-expanded={open}
                aria-label="Add-on settings"
                className="cursor-pointer rounded-lg border border-neutral-300 p-1.5 text-neutral-500 transition-colors hover:text-neutral-800 dark:border-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
            >
                <Settings className="h-4 w-4" aria-hidden="true" />
            </button>
            <SettingsDropdown sessionId={sessionId} open={open} onClose={() => setOpen(false)} />

            <ThemeToggle />
        </div>
    );
}
