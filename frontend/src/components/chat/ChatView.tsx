import type { AttachedImage } from '../../types';
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
      <MessageList messages={messages} expandedSteps={expandedSteps} onToggleStep={onToggleStep} />
      <Composer busy={busy} onSend={onSend} />
    </div>
  );
}
