import { Fragment, useEffect, useRef } from 'react';
import type { Message } from '../types';
import EventTimeline from './EventTimeline';
import MessageBubble from './MessageBubble';

export default function MessageList({ messages }: { messages: Message[] }) {
  const scrollRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  return (
    <main ref={scrollRef} aria-live="polite" className="flex flex-1 flex-col gap-3 overflow-y-auto p-5">
      {messages.map((m) => (
        <Fragment key={m.id}>
          {m.role === 'assistant' && m.events?.length ? <EventTimeline events={m.events} /> : null}
          <MessageBubble message={m} />
        </Fragment>
      ))}
    </main>
  );
}