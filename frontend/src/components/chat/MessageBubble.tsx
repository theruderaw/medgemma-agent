import { useState } from 'react';
import type { ChatMessage } from '../../hooks/useConversation';
import PrescriptionCard from './PrescriptionCard';
import ClinicalNoteDialog from './ClinicalNoteDialog';
import Markdown from './Markdown';
import UrgencyBadge from './UrgencyBadge';
import { StreamCaret, WritingDots } from '../ui/StreamIndicators';

const ROLE_LABEL: Record<ChatMessage['role'], string> = {
  user: 'You',
  assistant: 'Assistant',
  error: 'Error',
};

function ThinkingRow({ text }: { text: string }) {
  return (
    <div className="flex animate-rise items-center gap-2 self-start py-1 pl-1 text-sm italic text-neutral-500">
      <span className="h-1.5 w-1.5 animate-breathe rounded-full bg-neutral-500 dark:bg-neutral-400" />
      {text}
    </div>
  );
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const [noteOpen, setNoteOpen] = useState(false);

  if (message.thinking) return <ThinkingRow text={message.text} />;

  const tone =
    message.role === 'user'
      ? 'bg-neutral-200/70 border-neutral-300/70 dark:bg-neutral-800 dark:border-neutral-700'
      : message.role === 'error'
        ? 'bg-neutral-100 border-neutral-400 dark:bg-neutral-950 dark:border-neutral-600'
        : 'bg-neutral-50 border-neutral-200 dark:bg-neutral-900 dark:border-neutral-800';

  return (
    <div
      className={`flex max-w-[85%] animate-rise flex-col break-words self-start rounded-xl border px-4 py-3 ${
        message.role === 'user' ? 'self-end' : ''
      } ${tone} ${message.role === 'error' ? 'max-w-[90%] self-center' : ''}`}
    >
      <span className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wider text-neutral-500">
        {ROLE_LABEL[message.role]}
        {message.role === 'assistant' && message.specialistStreaming && (
          <WritingDots />
        )}
      </span>

      {message.imagePreview &&
        (message.imagePreview.startsWith('data:application/pdf') ? (
          <div className="mb-2 flex items-center gap-2 self-start rounded-lg border border-neutral-300 bg-neutral-100 px-2.5 py-1.5 text-xs text-neutral-700 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
            <span aria-hidden>📄</span> PDF attached
          </div>
        ) : (
          <img
            src={message.imagePreview}
            alt="Attached symptom image"
            className="mb-2 max-h-48 rounded-lg object-cover"
          />
        ))}

      {message.role === 'assistant' && (
        <>
          <UrgencyBadge urgency={message.urgency} />
          {message.structured?.kind === 'prescription' && (
            <PrescriptionCard data={message.structured.data as unknown as import('../../types').PrescriptionData} />
          )}
          {message.specialistNote != null && (
            <button
              type="button"
              onClick={() => setNoteOpen(true)}
              aria-haspopup="dialog"
              className="mb-2 flex cursor-pointer items-center gap-1.5 self-start rounded-full border border-neutral-400 bg-neutral-100 px-2.5 py-1 text-[11px] uppercase tracking-wider text-neutral-700 transition-colors hover:border-neutral-600 hover:text-neutral-950 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:border-neutral-400 dark:hover:text-neutral-50"
            >
              Clinical note
              {message.specialistStreaming && <WritingDots />}
            </button>
          )}
        </>
      )}

      {message.streaming ? (
        <span className="whitespace-pre-wrap">
          {message.text}
          <StreamCaret />
        </span>
      ) : (
        <Markdown text={message.text} />
      )}

      {noteOpen && (
        <ClinicalNoteDialog
          note={message.specialistNote ?? ''}
          streaming={message.specialistStreaming ?? false}
          onClose={() => setNoteOpen(false)}
        />
      )}
    </div>
  );
}
