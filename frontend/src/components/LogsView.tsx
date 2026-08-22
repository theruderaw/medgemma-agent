import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchAuditEvents } from '../lib/api';
import type { AuditRecord } from '../types';

const MODULE_STYLES: Record<string, string> = {
  safety: 'text-red-300 border-red-900',
  image: 'text-purple-300 border-purple-900',
  triage: 'text-amber-300 border-amber-900',
  router: 'text-sky-300 border-sky-900',
  specialist: 'text-green-300 border-green-900',
  chat: 'text-slate-200 border-slate-700',
  session: 'text-blue-300 border-blue-900',
  job: 'text-orange-300 border-orange-900',
};

function moduleStyle(module: string): string {
  return MODULE_STYLES[module] ?? 'text-slate-300 border-slate-700';
}

function formatTime(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString();
}

interface Props {
  /** Current chat session id — offered as a one-click filter. */
  sessionId: string | null;
}

export default function LogsView({ sessionId }: Props) {
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
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="m-0 text-sm uppercase tracking-widest text-slate-400">Audit trail</h2>
        <input
          type="search"
          placeholder="Filter by session id or event…"
          aria-label="Filter audit events"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-64 border-b border-slate-700 bg-transparent px-2 py-1 text-sm placeholder:text-slate-500 focus:border-sky-400 focus:outline-none"
        />
        {sessionId && (
          <button
            type="button"
            onClick={() => setQuery(sessionId)}
            className="cursor-pointer rounded-full border border-slate-700 px-2.5 py-0.5 text-xs text-slate-400 transition-colors hover:text-slate-200"
            title="Show only the current chat session"
          >
            current session
          </button>
        )}
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {modules.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setModuleFilter(m)}
            aria-pressed={moduleFilter === m}
            className={`cursor-pointer rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
              moduleFilter === m
                ? 'border-sky-400 bg-sky-950 text-sky-300'
                : 'border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            {m}
          </button>
        ))}
      </div>

      {loading && events.length === 0 && (
        <p className="px-1 text-sm italic text-slate-500">Loading audit trail…</p>
      )}
      {error && <p className="px-1 text-sm text-red-400">{error}</p>}
      {!loading && !error && filtered.length === 0 && (
        <p className="px-1 text-sm italic text-slate-500">No audit events match.</p>
      )}

      <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
        {filtered.map((e) => (
          <li key={e.id}>
            <details className="group rounded-lg border border-slate-800 bg-slate-900/60">
              <summary className="flex cursor-pointer flex-wrap items-center gap-2.5 px-3 py-2 text-sm marker:content-none">
                <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${moduleStyle(e.module)}`}>
                  {e.module}
                </span>
                <span className="font-mono text-xs text-slate-200">{e.event_type}</span>
                {e.session_id && (
                  <span className="font-mono text-[11px] text-slate-500" title={e.session_id}>
                    {e.session_id.slice(0, 8)}
                  </span>
                )}
                <span className="ml-auto text-[11px] text-slate-500">{formatTime(e.created_at)}</span>
              </summary>
              <pre className="m-0 overflow-x-auto border-t border-slate-800 px-3 py-2 text-xs leading-relaxed text-slate-300">
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
          className="mt-4 cursor-pointer self-center rounded-full border border-slate-700 px-4 py-1.5 text-sm text-slate-300 transition-colors hover:border-sky-400 hover:text-sky-300 disabled:opacity-50"
        >
          {loading ? '…' : `Load more (showing ${events.length})`}
        </button>
      )}
    </main>
  );
}
