import { Fragment, useEffect, useRef } from 'react';
import type { ChatMessage } from '../../hooks/useConversation';
import EventTimeline from './EventTimeline';
import MessageBubble from './MessageBubble';

interface Props {
  messages: ChatMessage[];
  /** Open event-timeline steps, keyed `${messageId}:${index}`. */
  expandedSteps: Record<string, boolean>;
  onToggleStep: (key: string) => void;
}

export default function MessageList({ messages, expandedSteps, onToggleStep }: Props) {
  const scrollRef = useRef<HTMLElement>(null);

  // Keep the newest turn in view; fires on every streamed token.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  if (!messages.length) {
    return (
      <main className="flex flex-1 items-center justify-center p-6">
        <div className="max-w-sm text-center">
          <p className="m-0 text-sm text-neutral-500 dark:text-neutral-400">
            Describe symptoms, attach a photo, or ask any health question.
          </p>
          <p className="m-0 mt-2 text-xs text-neutral-600 dark:text-neutral-300">
            Red-flag phrases bypass the models entirely and page you immediately.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main ref={scrollRef} aria-live="polite" className="flex flex-1 flex-col overflow-y-auto p-5">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
        {messages.map((m) => (
          <Fragment key={m.id}>
            {m.role === 'assistant' && m.events?.length ? (
              <div className="mx-auto w-full max-w-xl">
                <EventTimeline
                  events={m.events}
                  streaming={m.specialistStreaming}
                  idPrefix={`m${m.id}`}
                  expanded={expandedSteps}
                  onToggle={onToggleStep}
                />
              </div>
            ) : null}
            <MessageBubble message={m} />
          </Fragment>
        ))}
      </div>
    </main>
  );
}
