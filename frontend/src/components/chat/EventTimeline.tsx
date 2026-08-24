import type { AuditEvent } from '../../types';
import Badge from '../ui/Badge';
import { WritingDots } from '../ui/StreamIndicators';

// ---------------------------------------------------------------------------
// Pipeline visualization: one expandable step per audit event, newest turn
// first, rendered as a vertical rail — a continuous line with one dot node
// per step. Dot hues are unique per module so steps can be told apart.

const MODULE_DOT: Record<string, string> = {
  safety: 'bg-red-600 dark:bg-red-400',
  triage: 'bg-amber-500 dark:bg-amber-400',
  router: 'bg-sky-600 dark:bg-sky-400',
  specialist: 'bg-violet-600 dark:bg-violet-400',
  image: 'bg-cyan-500 dark:bg-cyan-400',
  addon: 'bg-emerald-600 dark:bg-emerald-400',
  chat: 'bg-neutral-500 dark:bg-neutral-400',
};

function stepLabel(ev: AuditEvent): string {
  const p = ev.payload ?? {};
  switch (ev.event_type) {
    case 'safety_override':
      return 'Safety check';
    case 'image_received':
      return 'Image received';
    case 'triage_result':
      return p.source === 'vision' ? 'Triage (vision)' : 'Triage';
    case 'routing_decision':
      if (p.slash_override) return `Slash → ${p.slash_addon ?? 'addon'}`;
      if (p.image_override) return 'Image → specialist';
      if (p.keyword_override) return 'Keyword → addon';
      return p.category === 'symptom_related' ? 'Call specialist' : 'Routing';
    case 'specialist_output':
      return p.mode === 'deterministic' ? 'Addon (deterministic)' : 'Specialist note';
    case 'addon_failed':
      return `Addon failed (${p.addon ?? 'unknown'})`;
    case 'turn_completed':
      if (p.path === 'addon_unavailable') return 'Addon unavailable fallback';
      if (p.path === 'direct_tool') return 'Tool result';
      return 'Synthesis';
    default:
      return ev.event_type;
  }
}

function kv(key: string, value: unknown) {
  return (
    <div className="flex gap-1.5">
      <b className="font-semibold text-neutral-400">{key}</b>
      <span>{value == null ? '—' : String(value)}</span>
    </div>
  );
}

function EventPayload({ ev }: { ev: AuditEvent }) {
  const p = ev.payload ?? {};
  const raw = (
    <pre className="mt-1 max-h-[120px] overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-950/60 p-1.5 font-mono text-[11px] text-neutral-400">
      {JSON.stringify(p, null, 2)}
    </pre>
  );
  switch (ev.event_type) {
    case 'safety_override':
      return kv('category', p.category);
    case 'image_received':
      return (
        <div className="flex flex-col gap-1">
          {kv('mime', p.mime)}
          {p.size_bytes != null && kv('size', `${p.size_bytes} bytes`)}
        </div>
      );
    case 'triage_result': {
      const redFlags = Array.isArray(p.red_flags) ? (p.red_flags as unknown[]) : [];
      return (
        <div className="flex flex-col gap-1">
          {kv('urgency', p.urgency)}
          {redFlags.length > 0 && kv('red_flags', redFlags.join(', '))}
          {p.source != null && kv('source', p.source)}
        </div>
      );
    }
    case 'routing_decision':
      return (
        <div className="flex flex-col gap-1">
          {kv('category', p.category)}
          {p.reason != null && kv('reason', p.reason)}
          {Array.isArray(p.tools) && kv('tools', (p.tools as unknown[]).join(', '))}
          {p.slash_override != null && kv('slash_override', p.slash_override)}
          {p.slash_addon != null && kv('slash_addon', p.slash_addon)}
          {p.duration_ms != null && kv('duration_ms', p.duration_ms)}
          {p.image_override != null && kv('image_override', p.image_override)}
          {p.keyword_override != null && kv('keyword_override', p.keyword_override)}
        </div>
      );
    case 'specialist_output':
      return (
        <div className="flex flex-col gap-1">
          {kv('model', p.model)}
          {p.mode != null && kv('mode', p.mode)}
        </div>
      );
    case 'addon_failed':
      return (
        <div className="flex flex-col gap-1">
          {kv('addon', p.addon)}
          {kv('error', p.error)}
        </div>
      );
    case 'turn_completed':
      return kv('model', p.model);
    default:
      return raw;
  }
}

function EventStep({
  ev,
  open,
  onToggle,
  isLast,
}: {
  ev: AuditEvent;
  open: boolean;
  onToggle: () => void;
  /** Suppresses the connector below the node on the final row. */
  isLast: boolean;
}) {
  const dot = MODULE_DOT[ev.module] ?? 'bg-neutral-500 dark:bg-neutral-400';
  return (
    <div className="flex items-stretch gap-3">
      <div className="flex w-4 shrink-0 flex-col items-center">
        <span className={`mt-[7px] h-2 w-2 shrink-0 rounded-full ${dot}`} />
        {!isLast && <span className="w-px flex-1 bg-neutral-300 dark:bg-neutral-700" />}
      </div>
      <div className="min-w-0 pb-2">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex cursor-pointer items-center gap-2 py-1 text-left text-xs font-semibold text-neutral-600 transition-colors hover:text-neutral-900 dark:text-neutral-300 dark:hover:text-neutral-100"
        >
          <Badge tone="muted">{ev.module}</Badge>
          <span>{stepLabel(ev)}</span>
          <svg
            className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`}
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <path d="M5 8l5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {open && (
          <div className="mb-1 mt-1 text-xs text-neutral-600 dark:text-neutral-300">
            <div className="mb-1 font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
              {ev.event_type}
            </div>
            <EventPayload ev={ev} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function EventTimeline({
  events,
  streaming,
  idPrefix,
  expanded,
  onToggle,
}: {
  events: AuditEvent[];
  /** While the note streams live, hint that more steps are coming. */
  streaming?: boolean;
  /** Stable per-message prefix for expansion keys (state lives in the
   * conversation reducer so it survives view switches). */
  idPrefix: string;
  expanded: Record<string, boolean>;
  onToggle: (key: string) => void;
}) {
  if (!events?.length) return null;
  return (
    <div className="flex max-w-xl flex-col self-start">
      {events.map((ev, i) => {
        const key = `${idPrefix}:${i}`;
        return (
          <EventStep
            key={key}
            ev={ev}
            open={!!expanded[key]}
            onToggle={() => onToggle(key)}
            isLast={i === events.length - 1 && !streaming}
          />
        );
      })}
      {streaming && (
        <div className="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
          <div className="flex w-4 shrink-0 justify-center">
            <WritingDots className="text-neutral-500 dark:text-neutral-400" />
          </div>
          pipeline running
        </div>
      )}
    </div>
  );
}
