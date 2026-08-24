import type { ReactNode } from 'react';

type Tone = 'neutral' | 'accent' | 'active' | 'high' | 'safety' | 'muted';

const TONES: Record<Tone, string> = {
  neutral:
    'border-neutral-300 bg-neutral-100 text-neutral-600 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300',
  accent:
    'border-neutral-500/40 bg-neutral-100 text-neutral-700 dark:border-neutral-400/40 dark:bg-neutral-800/60 dark:text-neutral-300',
  active:
    'border-neutral-500 bg-neutral-200 text-neutral-900 dark:border-neutral-400 dark:bg-neutral-700 dark:text-neutral-100',
  high: 'border-neutral-500/60 bg-neutral-200 text-neutral-800 dark:border-neutral-500/40 dark:bg-neutral-800 dark:text-neutral-300',
  safety:
    'border-neutral-900/60 bg-neutral-900 text-neutral-100 dark:border-neutral-100/60 dark:bg-neutral-100 dark:text-neutral-900',
  muted:
    'border-neutral-200 bg-transparent text-neutral-400 dark:border-neutral-800 dark:text-neutral-500',
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
