import type { Online } from '../../hooks/useHealth';
import Badge from '../ui/Badge';

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
    <header className="flex items-center justify-end gap-3 border-b border-ink-800 bg-ink-900/70 px-5 py-3 backdrop-blur">
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open conversations menu"
        className="mr-auto cursor-pointer rounded-lg border border-ink-700 p-1.5 text-slate-400 transition-colors hover:text-slate-200 md:hidden"
      >
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
          <path d="M3 6h14M3 10h14M3 14h14" strokeLinecap="round" />
        </svg>
      </button>

      <nav className="flex rounded-full border border-ink-700 p-0.5" aria-label="Views">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onView(t.id)}
            aria-current={view === t.id ? 'page' : undefined}
            className={`cursor-pointer rounded-full px-3 py-1 text-xs transition-colors ${
              view === t.id
                ? 'bg-accent-900/80 text-accent-300'
                : 'text-slate-400 hover:text-slate-200'
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

      <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
        <span
          className={`h-2 w-2 rounded-full ${
            online === false ? 'bg-red-500' : 'animate-breathe bg-emerald-400'
          }`}
        />
        {statusLabel(online)}
      </span>
    </header>
  );
}
