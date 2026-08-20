import { useState } from 'react';
import type { AuditEvent } from '../types';

const MODULE_ACCENT: Record<string, string> = {
  safety: 'border-red-500',
  triage: 'border-violet-400',
  router: 'border-sky-400',
  specialist: 'border-green-500',
  chat: 'border-slate-500',
};

function stepLabel(ev: AuditEvent): string {
  const p = ev.payload ?? {};
  switch (ev.event_type) {
    case 'safety_override':
      return 'Safety check';
    case 'triage_result':
      return 'Triage';
    case 'routing_decision':
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
  const raw = <pre className="mt-1 max-h-[120px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950 p-1.5 font-mono text-[11px] text-slate-400">{JSON.stringify(p, null, 2)}</pre>;
  switch (ev.event_type) {
    case 'safety_override':
      return kv('category', p.category);
    case 'triage_result':
      return kv('urgency', p.urgency);
    case 'routing_decision':
      return (
        <div className="flex flex-col gap-1">
          {kv('category', p.category)}
          {p.reason != null && kv('reason', p.reason)}
        </div>
      );
    case 'specialist_output':
      return (
        <div className="flex flex-col gap-1">
          {kv('model', p.model)}
          {p.note != null && (
            <pre className="mt-1 max-h-[120px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950 p-1.5 font-mono text-[11px] text-slate-400">
              {String(p.note)}
            </pre>
          )}
        </div>
      );
    default:
      return raw;
  }
}

function EventStep({ ev }: { ev: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const accent = MODULE_ACCENT[ev.module] ?? 'border-slate-500';
  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={`flex cursor-pointer items-center gap-2 self-start rounded-md border-l-2 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:bg-slate-800 ${accent}`}
      >
        <span className="text-[10px] uppercase tracking-wider text-slate-500">{ev.module}</span>
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
        <div className="mt-1.5 rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-300">
          <div className="mb-1 font-mono text-[10px] text-slate-500">{ev.event_type}</div>
          <EventPayload ev={ev} />
        </div>
      )}
    </div>
  );
}

export default function EventTimeline({ events }: { events: AuditEvent[] }) {
  if (!events?.length) return null;
  return (
    <div className="flex max-w-xl flex-col gap-2 self-start border-l border-slate-700 pl-3">
      {events.map((ev, i) => (
        <EventStep key={i} ev={ev} />
      ))}
    </div>
  );
}