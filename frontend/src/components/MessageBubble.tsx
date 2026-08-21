import type { Message } from '../types';
import Markdown from './Markdown';
import UrgencyBanner from './UrgencyBanner';

const ROLE_STYLES: Record<Message['role'], string> = {
  user: 'self-end max-w-[75%] rounded-2xl bg-blue-700 px-4 py-2.5',
  assistant: 'self-start max-w-[75%] rounded-2xl bg-slate-800 px-4 py-3',
  error: 'self-center max-w-[90%] rounded-2xl bg-red-500/90 px-4 py-2.5 text-sm',
};

const ROLE_LABEL: Record<Message['role'], string> = {
  user: 'You',
  assistant: 'Assistant',
  error: 'Error',
};

export default function MessageBubble({ message }: { message: Message }) {
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
          className="mb-2 max-h-48 rounded-xl border border-blue-500/40 object-cover"
        />
      )}
      {message.role === 'assistant' && (
        <>
          <UrgencyBanner urgency={message.urgency} />
          {message.specialistNote != null && (
            <div className="mb-2 rounded-lg border border-green-500/30 bg-green-500/5 px-2.5 py-2">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-green-300">
                Clinical note
                {message.specialistStreaming && (
                  <span className="flex gap-0.5" aria-label="MedGemma is writing">
                    <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:0ms]" />
                    <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:150ms]" />
                    <span className="h-1 w-1 animate-bounce rounded-full bg-green-400 [animation-delay:300ms]" />
                  </span>
                )}
              </div>
              <div className="whitespace-pre-wrap text-xs leading-relaxed text-slate-200">
                {message.specialistNote}
              </div>
            </div>
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
