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
    text: 'text-red-400',
    dot: 'bg-red-500',
    ring: 'ring-red-500/40',
  },
  urgent: {
    label: 'Urgent',
    text: 'text-amber-400',
    dot: 'bg-amber-400',
    ring: 'ring-amber-400/40',
  },
  routine: {
    label: 'Routine',
    text: 'text-accent-300',
    dot: 'bg-accent-400',
    ring: 'ring-accent-400/40',
  },
  self_care: {
    label: 'Self care',
    text: 'text-emerald-400',
    dot: 'bg-emerald-400',
    ring: 'ring-emerald-400/40',
  },
};
