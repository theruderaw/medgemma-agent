/** Small pure formatting helpers shared across panels. */

import type { Urgency } from '../types';

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Size of a base64 payload once decoded (~3/4 of the string length). */
export function b64Bytes(b64: string): number {
  return Math.floor(b64.length * 0.75);
}

export function formatTime(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString();
}

export interface UrgencyMeta {
  label: string;
  text: string;
  dot: string;
  ring: string;
}

/** Semantic presentation for each backend urgency level. */
export const URGENCY: Record<Exclude<Urgency, null>, UrgencyMeta> = {
  emergency: {
    label: 'Emergency',
    text: 'text-neutral-900 dark:text-neutral-100',
    dot: 'bg-neutral-900 dark:bg-neutral-100',
    ring: 'ring-neutral-800/40 dark:ring-neutral-200/40',
  },
  urgent: {
    label: 'Urgent',
    text: 'text-neutral-700 dark:text-neutral-300',
    dot: 'bg-neutral-600 dark:bg-neutral-400',
    ring: 'ring-neutral-500/40',
  },
  routine: {
    label: 'Routine',
    text: 'text-neutral-500 dark:text-neutral-400',
    dot: 'bg-neutral-400 dark:bg-neutral-500',
    ring: 'ring-neutral-400/40',
  },
  self_care: {
    label: 'Self care',
    text: 'text-neutral-400 dark:text-neutral-500',
    dot: 'bg-neutral-300 dark:bg-neutral-600',
    ring: 'ring-neutral-300/40 dark:ring-neutral-600/40',
  },
};
