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
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
            role="dialog"
            aria-modal="true"
            aria-label={title}
            aria-labelledby={labelledBy}
            onClick={requestClose}
        >
            <div
                className={`w-full max-w-lg rounded-xl border bg-white p-6 shadow-2xl shadow-black/20 dark:bg-neutral-900 dark:shadow-black/60 ${
                    tone === 'danger'
                        ? 'border-neutral-900 dark:border-neutral-400'
                        : 'border-neutral-200 dark:border-neutral-800'
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
                danger
                    ? 'text-neutral-500 hover:text-neutral-950 dark:text-neutral-400 dark:hover:text-neutral-50'
                    : 'text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
            }`}
        >
            ✕
        </button>
    );
}
