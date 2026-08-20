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
      {message.role === 'assistant' && <UrgencyBanner urgency={message.urgency} />}
      {message.streaming ? (
        <span className="whitespace-pre-wrap">{message.text}</span>
      ) : (
        <Markdown text={message.text} />
      )}
    </div>
  );
}