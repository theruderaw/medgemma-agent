import { useState } from 'react';
import type { ChatMessage } from '../../hooks/useConversation';
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
    <div className="flex animate-rise items-center gap-2 self-start py-1 pl-1 text-sm italic text-slate-500">
      <span className="h-1.5 w-1.5 animate-breathe rounded-full bg-accent-400" />
      {text}
    </div>
  );
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const [noteOpen, setNoteOpen] = useState(false);

  if (message.thinking) return <ThinkingRow text={message.text} />;

  const tone =
    message.role === 'user'
      ? 'bg-accent-900/40 border-accent-500/30'
      : message.role === 'error'
        ? 'bg-red-950/40 border-red-900/60'
        : 'bg-ink-850 border-ink-800';

  return (
    <div
      className={`flex max-w-[85%] animate-rise flex-col break-words self-start rounded-xl border px-4 py-3 ${
        message.role === 'user' ? 'self-end' : ''
      } ${tone} ${message.role === 'error' ? 'max-w-[90%] self-center' : ''}`}
    >
      <span className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        {ROLE_LABEL[message.role]}
        {message.role === 'assistant' && message.specialistStreaming && (
          <WritingDots />
        )}
      </span>

      {message.imagePreview && (
        <img
          src={message.imagePreview}
          alt="Attached symptom image"
          className="mb-2 max-h-48 rounded-lg object-cover"
        />
      )}

      {message.role === 'assistant' && (
        <>
          <UrgencyBadge urgency={message.urgency} />
          {message.specialistNote != null && (
            <button
              type="button"
              onClick={() => setNoteOpen(true)}
              aria-haspopup="dialog"
              className="mb-2 flex cursor-pointer items-center gap-1.5 self-start rounded-full border border-emerald-800 bg-emerald-950/50 px-2.5 py-1 text-[11px] uppercase tracking-wider text-emerald-300 transition-colors hover:border-emerald-600 hover:text-emerald-200"
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
