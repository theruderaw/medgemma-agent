import type { Urgency } from '../types';

const URGENCY_BANNER: Record<Exclude<Urgency, null>, { value: string; classes: string }> = {
  emergency: { value: 'URGENT', classes: 'border-red-500 bg-red-500/10 text-red-300' },
  medical: { value: 'MEDICAL', classes: 'border-amber-500 bg-amber-500/10 text-amber-300' },
  general: { value: 'GENERAL', classes: 'border-green-500 bg-green-500/10 text-green-300' },
};

export default function UrgencyBanner({ urgency }: { urgency: Urgency | undefined }) {
  if (!urgency) return null;
  const { value, classes } = URGENCY_BANNER[urgency];
  return (
    <div className={`mb-2 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 ${classes}`}>
      <span className="text-[10px] font-normal uppercase tracking-widest opacity-70">URGENCY:</span>
      <span className="text-sm font-bold tracking-wide">{value}</span>
    </div>
  );
}