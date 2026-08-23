import type { AttachedImage } from '../../types';
import ErrorBoundary from '../ErrorBoundary';
import type { ChatMessage } from '../../hooks/useConversation';
import Composer from './Composer';
import MessageList from './MessageList';

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  onSend: (text: string, image?: AttachedImage, triage?: boolean) => void;
  expandedSteps: Record<string, boolean>;
  onToggleStep: (key: string) => void;
}

/** The chat surface: scrollable turn history over a floating composer. */
export default function ChatView({ messages, busy, onSend, expandedSteps, onToggleStep }: Props) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* One malformed message must not take the composer down with it. */}
      <ErrorBoundary
        fallback={(_message, reset) => (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
            <p className="text-sm text-slate-400">
              This conversation could not be displayed — start a new chat to continue.
            </p>
            <button
              type="button"
              onClick={reset}
              className="cursor-pointer rounded-lg border border-ink-700 px-4 py-2 text-sm text-slate-300 transition-colors hover:border-accent-500/50 hover:text-accent-300"
            >
              Try again
            </button>
          </div>
        )}
      >
        <MessageList messages={messages} expandedSteps={expandedSteps} onToggleStep={onToggleStep} />
      </ErrorBoundary>
      <Composer busy={busy} onSend={onSend} />
    </div>
  );
}
