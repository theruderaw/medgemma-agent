import Modal, { ModalClose } from '../ui/Modal';
import { WritingDots } from '../ui/StreamIndicators';

interface Props {
  note: string;
  streaming: boolean;
  onClose: () => void;
}

/** The raw MedGemma clinical note for one turn, in a scrollable dialog. */
export default function ClinicalNoteDialog({ note, streaming, onClose }: Props) {
  return (
    <Modal title="Clinical note" onClose={onClose}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-neutral-600 dark:text-neutral-300">
          Clinical note
          {streaming && <WritingDots />}
        </div>
        <ModalClose onClose={onClose} />
      </div>
      <div className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-neutral-800 dark:text-neutral-200">
        {note}
      </div>
    </Modal>
  );
}
