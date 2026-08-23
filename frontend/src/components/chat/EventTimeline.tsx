import type { AuditEvent } from '../../types';
import Badge from '../ui/Badge';
import { WritingDots } from '../ui/StreamIndicators';

// ---------------------------------------------------------------------------
// Pipeline visualization: one expandable step per audit event, newest turn
// first. Module accents match the LogsPanel chips for cross-referencing.

const MODULE_ACCENT: Record<string, string> = {
  safety: 'border-red-500',
  triage: 'border-violet-400',
  router: 'border-accent-400',
  specialist: 'border-emerald-500',
  image: 'border-amber-400',
  chat: 'border-slate-500',
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
      if (p.image_override) return 'Image → specialist';
      return p.category === 'symptom_related' ? 'Call specialist' : 'Routing';
    case 'specialist_output':
      return 'Specialist note';
    case 'turn_completed':
      return 'Synthesis';
    default:
      return ev.event_type;
  }
}

function kv(key: string, value: unknown) {
  return (
    <div className="flex gap-1.5">
      <b className="font-semibold text-slate-400">{key}</b>
      <span>{value == null ? '—' : String(value)}</span>
    </div>
  );
}

function EventPayload({ ev }: { ev: AuditEvent }) {
  const p = ev.payload ?? {};
  const raw = (
    <pre className="mt-1 max-h-[120px] overflow-auto whitespace-pre-wrap break-words rounded bg-ink-950/60 p-1.5 font-mono text-[11px] text-slate-400">
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
          {p.duration_ms != null && kv('duration_ms', p.duration_ms)}
          {p.image_override != null && kv('image_override', p.image_override)}
        </div>
      );
    case 'specialist_output':
      return kv('model', p.model);
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
}: {
  ev: AuditEvent;
  open: boolean;
  onToggle: () => void;
}) {
  const accent = MODULE_ACCENT[ev.module] ?? 'border-slate-500';
  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={`flex cursor-pointer items-center gap-2 self-start border-l-2 px-3 py-1 text-left text-xs font-semibold text-slate-300 transition-colors hover:text-slate-100 ${accent}`}
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
        <div className="mb-1 ml-px mt-1 border-l-2 border-ink-800 px-3 py-2 text-xs text-slate-300">
          <div className="mb-1 font-mono text-[10px] text-slate-500">{ev.event_type}</div>
          <EventPayload ev={ev} />
        </div>
      )}
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
    <div className="flex max-w-xl flex-col gap-0.5 self-start border-l border-ink-800 pl-2">
      {events.map((ev, i) => {
        const key = `${idPrefix}:${i}`;
        return (
          <EventStep
            key={key}
            ev={ev}
            open={!!expanded[key]}
            onToggle={() => onToggle(key)}
          />
        );
      })}
      {streaming && (
        <div className="flex items-center gap-2 py-1 pl-3 text-xs text-slate-500">
          <WritingDots className="text-accent-400" /> pipeline running
        </div>
      )}
    </div>
  );
}
