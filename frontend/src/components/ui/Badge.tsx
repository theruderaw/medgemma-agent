import type { ReactNode } from 'react';

type Tone = 'neutral' | 'accent' | 'active' | 'high' | 'safety' | 'muted';

const TONES: Record<Tone, string> = {
  neutral: 'border-ink-700 bg-ink-850 text-slate-300',
  accent: 'border-accent-500/40 bg-accent-900/50 text-accent-300',
  active: 'border-accent-400 bg-accent-900 text-accent-300',
  high: 'border-amber-700 bg-amber-950/60 text-amber-300',
  safety: 'border-red-800 bg-red-950/40 text-red-300',
  muted: 'border-ink-800 bg-transparent text-slate-500',
};

interface Props {
  tone?: Tone;
  className?: string;
  title?: string;
  children: ReactNode;
}

/** Small pill label used for module chips, states, and warnings. */
export default function Badge({ tone = 'neutral', className = '', title, children }: Props) {
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
