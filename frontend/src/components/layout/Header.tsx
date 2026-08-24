import type { Online } from '../../hooks/useHealth';
import Badge from '../ui/Badge';
import ThemeToggle from '../ui/ThemeToggle';

export type View = 'chat' | 'addons' | 'logs';

interface Props {
  sessionId: string | null;
  online: Online;
  view: View;
  onView: (view: View) => void;
  /** Opens the sidebar drawer (small screens only). */
  onMenu: () => void;
}

function statusLabel(online: Online): string {
  return online === null ? 'checking…' : online ? 'online' : 'offline';
}

const TABS: { id: View; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'addons', label: 'Add-ons' },
  { id: 'logs', label: 'Logs' },
];

export default function Header({ sessionId, online, view, onView, onMenu }: Props) {
  return (
    <header className="flex items-center justify-end gap-3 border-b border-neutral-200 bg-white/70 px-5 py-3 backdrop-blur dark:border-neutral-800 dark:bg-neutral-900/70">
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open conversations menu"
        className="mr-auto cursor-pointer rounded-lg border border-neutral-300 p-1.5 text-neutral-500 transition-colors hover:text-neutral-800 md:hidden dark:border-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
      >
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
          <path d="M3 6h14M3 10h14M3 14h14" strokeLinecap="round" />
        </svg>
      </button>

      <nav className="flex rounded-full border border-neutral-300 p-0.5 dark:border-neutral-700" aria-label="Views">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onView(t.id)}
            aria-current={view === t.id ? 'page' : undefined}
            className={`cursor-pointer rounded-full px-3 py-1 text-xs transition-colors ${
              view === t.id
                ? 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900'
                : 'text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {sessionId && (
        <Badge tone="muted" title={sessionId} className="font-mono normal-case">
          session {sessionId.slice(0, 8)}
        </Badge>
      )}

      <span className="inline-flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
        <span className={`h-2 w-2 rounded-full ${online === false ? 'bg-neutral-400' : 'bg-neutral-800 dark:bg-neutral-200'}`} />
        {statusLabel(online)}
      </span>

      <ThemeToggle />
    </header>
  );
}
