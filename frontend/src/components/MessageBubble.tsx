import { useState } from 'react';
import type { Message } from '../types';
import ClinicalNoteModal from './ClinicalNoteModal';
import Markdown from './Markdown';
import UrgencyBanner from './UrgencyBanner';

const ROLE_STYLES: Record<Message['role'], string> = {
  user: 'self-end max-w-[75%] px-4 py-2.5 text-blue-300',
  assistant: 'self-start max-w-[75%] px-4 py-3',
  error: 'self-center max-w-[90%] px-4 py-2.5 text-sm text-red-400',
};

const ROLE_LABEL: Record<Message['role'], string> = {
  user: 'You',
  assistant: 'Assistant',
  error: 'Error',
};

export default function MessageBubble({ message }: { message: Message }) {
  const [noteOpen, setNoteOpen] = useState(false);

  if (message.thinking) {
    return <div className="self-start px-1 text-sm italic text-slate-500">{message.text}</div>;
  }

  return (
    <div className={`break-words ${ROLE_STYLES[message.role]}`}>
      <span
        className={`mb-1 block text-[11px] uppercase tracking-wider ${
          message.role === 'user' ? 'text-blue-200' : 'text-slate-400'
        }`}
      >
        {ROLE_LABEL[message.role]}
      </span>
      {message.imagePreview && (
        <img
          src={message.imagePreview}
          alt="Attached symptom image"
          className="mb-2 max-h-48 rounded-xl object-cover"
        />
      )}
      {message.role === 'assistant' && (
        <>
          <UrgencyBanner urgency={message.urgency} />
          {message.specialistNote != null && (
            <>
              <button
                type="button"
                onClick={() => setNoteOpen(true)}
                aria-haspopup="dialog"
                className="mb-2 flex cursor-pointer items-center gap-1.5 text-[11px] uppercase tracking-wider text-green-300 transition-colors hover:text-green-200"
              >
                Clinical note
                {message.specialistStreaming && (
                  <span className="flex gap-0.5" aria-label="MedGemma is writing">
                    <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:0ms]" />
                    <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:150ms]" />
                    <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:300ms]" />
                  </span>
                )}
              </button>
              {noteOpen && (
                <ClinicalNoteModal
                  note={message.specialistNote}
                  streaming={message.specialistStreaming ?? false}
                  onClose={() => setNoteOpen(false)}
                />
              )}
            </>
          )}
        </>
      )}
      {message.streaming ? (
        <span className="whitespace-pre-wrap">
          {message.text}
          <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-slate-400 align-text-bottom" />
        </span>
      ) : (
        <Markdown text={message.text} />
      )}
    </div>
  );
}
