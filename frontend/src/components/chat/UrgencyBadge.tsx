import type { Urgency } from '../../types';
import { URGENCY } from '../../lib/format';

/** Inline urgency tag rendered above assistant replies. */
export default function UrgencyBadge({ urgency }: { urgency: Urgency | undefined }) {
  if (!urgency) return null;
  const meta = URGENCY[urgency];
  return (
    <div className="mb-2 inline-flex items-center gap-1.5">
      <span className={`h-2 w-2 animate-breathe rounded-full ${meta.dot}`} />
      <span className="text-[10px] uppercase tracking-widest text-neutral-500">Urgency:</span>
      <span className={`text-xs font-bold uppercase tracking-wide ${meta.text}`}>{meta.label}</span>
    </div>
  );
}
