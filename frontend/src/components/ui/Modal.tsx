import { useEffect, type ReactNode } from 'react';

interface Props {
  title?: string;
  labelledBy?: string;
  /** Accent color for the close affordance. */
  tone?: 'neutral' | 'danger';
  /**
   * Whether Escape and a backdrop click may close the dialog (default true).
   * Safety gates pass false so closing requires an explicit in-dialog action.
   */
  dismissible?: boolean;
  /** Dismissal handler; only invoked when dismissible is true. */
  onClose?: () => void;
  children: ReactNode;
}

/**
 * Shared dialog chrome: fixed overlay, Escape to close, backdrop click,
 * focus-trap-lite (autofocus handled by callers via autoFocus attr).
 */
export default function Modal({
  title,
  labelledBy,
  tone = 'neutral',
  dismissible = true,
  onClose,
  children,
}: Props) {
  useEffect(() => {
    if (!dismissible || !onClose) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [dismissible, onClose]);

  const requestClose = dismissible ? onClose : undefined;

  return (
    <div
      className="fixed inset-0 z-50 flex animate-rise items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      aria-labelledby={labelledBy}
      onClick={requestClose}
    >
      <div
        className={`panel w-full max-w-lg p-6 shadow-2xl shadow-black/60 ${
          tone === 'danger' ? 'border-red-900/60' : ''
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export function ModalClose({ onClose, danger }: { onClose: () => void; danger?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close dialog"
      className={`cursor-pointer rounded px-1.5 text-lg leading-none transition-colors ${
        danger ? 'text-slate-400 hover:text-red-300' : 'text-slate-400 hover:text-accent-300'
      }`}
    >
      ✕
    </button>
  );
}
