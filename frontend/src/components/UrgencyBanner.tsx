import type { Urgency } from '../types';

const URGENCY_BANNER: Record<Exclude<Urgency, null>, { value: string; classes: string }> = {
  emergency: { value: 'EMERGENCY', classes: 'text-red-400' },
  urgent: { value: 'URGENT', classes: 'text-amber-400' },
  routine: { value: 'ROUTINE', classes: 'text-sky-400' },
  self_care: { value: 'SELF CARE', classes: 'text-green-400' },
};

export default function UrgencyBanner({ urgency }: { urgency: Urgency | undefined }) {
  if (!urgency) return null;
  const { value, classes } = URGENCY_BANNER[urgency];
  return (
    <div className={`mb-2 inline-flex items-center gap-1.5 ${classes}`}>
      <span className="text-[10px] font-normal uppercase tracking-widest opacity-70">URGENCY:</span>
      <span className="text-sm font-bold tracking-wide">{value}</span>
    </div>
  );
}