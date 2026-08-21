import { useEffect } from 'react';

interface Props {
  note: string;
  streaming: boolean;
  onClose: () => void;
}

export default function ClinicalNoteModal({ note, streaming, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Clinical note"
      onClick={onClose}
    >
      <div className="w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-widest text-green-300">
            Clinical note
            {streaming && (
              <span className="flex gap-0.5" aria-label="MedGemma is writing">
                <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:0ms]" />
                <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:150ms]" />
                <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:300ms]" />
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close clinical note"
            className="cursor-pointer px-1.5 text-slate-400 transition-colors hover:text-slate-100"
          >
            ✕
          </button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
          {note}
        </div>
      </div>
    </div>
  );
}
