import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchAuditEvents } from '../../lib/api';
import { formatTime } from '../../lib/format';
import type { AuditRecord } from '../../types';
import Badge from '../ui/Badge';

const MODULE_TONES: Record<string, 'accent' | 'safety' | 'high' | 'neutral'> = {
  router: 'accent',
  safety: 'safety',
  triage: 'high',
  specialist: 'neutral',
  image: 'high',
  addon: 'high',
  session: 'accent',
  job: 'neutral',
  addons: 'accent',
};

function moduleTone(module: string): 'accent' | 'safety' | 'high' | 'neutral' {
  return MODULE_TONES[module] ?? 'neutral';
}

interface Props {
  /** Current chat session id — offered as a one-click filter. */
  sessionId: string | null;
}

/** Read-only view of the Postgres audit trail (GET /v1/audit). */
export default function LogsPanel({ sessionId }: Props) {
  const [events, setEvents] = useState<AuditRecord[]>([]);
  const [limit, setLimit] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [moduleFilter, setModuleFilter] = useState<string>('all');
  const [query, setQuery] = useState('');

  const load = useCallback(async (n: number) => {
    setLoading(true);
    setError(null);
    try {
      setEvents(await fetchAuditEvents({ limit: n }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load the audit trail.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(limit);
  }, [load, limit]);

  const modules = useMemo(() => {
    const known = new Set(events.map((e) => e.module));
    return ['all', ...[...known].sort()];
  }, [events]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return events.filter(
      (e) =>
        (moduleFilter === 'all' || e.module === moduleFilter) &&
        (!q || (e.session_id ?? '').includes(q) || e.event_type.includes(q)),
    );
  }, [events, moduleFilter, query]);

  return (
    <main className="flex flex-1 flex-col overflow-y-auto p-5">
      <div className="mx-auto flex w-full max-w-3xl flex-col">
        <header className="mb-4 flex flex-wrap items-center gap-3">
          <h2 className="m-0 text-base font-semibold uppercase tracking-widest text-neutral-400">
            Audit trail
          </h2>
          <input
            type="search"
            placeholder="Filter by session id or event…"
            aria-label="Filter audit events"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-64 rounded-lg border border-neutral-300 bg-white px-2.5 py-1.5 text-base placeholder:text-neutral-500 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:placeholder:text-neutral-400 dark:focus:border-neutral-400"
          />
          {sessionId && (
            <button
              type="button"
              onClick={() => setQuery(sessionId)}
              title="Show only the current chat session"
              className="cursor-pointer rounded-full border border-neutral-300 px-2.5 py-1 text-sm text-neutral-500 transition-colors hover:border-neutral-500 hover:text-neutral-900 dark:border-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-100"
            >
              current session
            </button>
          )}
        </header>

        <div className="mb-3 flex flex-wrap gap-1.5">
          {modules.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setModuleFilter(m)}
              aria-pressed={moduleFilter === m}
              className={`cursor-pointer rounded-full border px-2.5 py-1 text-sm transition-colors ${
                moduleFilter === m
                  ? 'border-neutral-900 bg-neutral-900 text-neutral-100 dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900'
                  : 'border-neutral-300 text-neutral-500 hover:text-neutral-900 dark:border-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-100'
              }`}
            >
              {m}
            </button>
          ))}
        </div>

        {loading && events.length === 0 && (
          <p className="px-1 text-sm italic text-neutral-500">Loading audit trail…</p>
        )}
        {error && <p className="px-1 text-sm text-neutral-800 dark:text-neutral-200">{error}</p>}
        {!loading && !error && filtered.length === 0 && (
          <p className="px-1 text-sm italic text-neutral-500">No audit events match.</p>
        )}

        <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
          {filtered.map((e) => (
            <li key={e.id}>
              <details className="group rounded-lg border border-neutral-200 bg-neutral-50 open:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-900/70 dark:open:border-neutral-700">
                <summary className="flex cursor-pointer flex-wrap items-center gap-2.5 px-3 py-2 text-base marker:content-none">
                  <Badge tone={moduleTone(e.module)}>{e.module}</Badge>
                  <span className="font-mono text-sm text-neutral-700 dark:text-neutral-200">{e.event_type}</span>
                  {e.session_id && (
                    <span className="font-mono text-xs text-neutral-500 dark:text-neutral-400" title={e.session_id}>
                      {e.session_id.slice(0, 8)}
                    </span>
                  )}
                  <span className="ml-auto text-xs text-neutral-500 dark:text-neutral-400">{formatTime(e.created_at)}</span>
                </summary>
                <pre className="m-0 overflow-x-auto border-t border-neutral-200 px-3 py-2 text-sm leading-relaxed text-neutral-600 dark:border-neutral-800 dark:text-neutral-300">
                  {JSON.stringify(e.payload, null, 2)}
                </pre>
              </details>
            </li>
          ))}
        </ul>

        {events.length >= limit && limit < 500 && (
          <button
            type="button"
            onClick={() => setLimit((n) => Math.min(n + 100, 500))}
            disabled={loading}
            className="mt-4 cursor-pointer self-center rounded-full border border-neutral-300 px-4 py-1.5 text-sm text-neutral-600 transition-colors hover:border-neutral-500 hover:text-neutral-900 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:text-neutral-100"
          >
            {loading ? '…' : `Load more (showing ${events.length})`}
          </button>
        )}
      </div>
    </main>
  );
}
