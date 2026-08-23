import { useEffect, useRef, useState } from 'react';
import type { ChatMessage } from '../../hooks/useConversation';
import Modal from '../ui/Modal';
import Markdown from './Markdown';

// Deliberate friction: the user must type "accepted" plus any four letters.
const ACK_PATTERN = /^accepted[a-z]{4}$/;

interface Props {
  message: ChatMessage | null;
  onAcknowledge: () => void;
}

/**
 * Full-screen gate shown when a turn carries EMERGENCY urgency. Blocks the
 * whole app until the acknowledgment phrase is typed.
 */
export default function EmergencyGate({ message, onAcknowledge }: Props) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!message) return;
    setValue('');
    inputRef.current?.focus();
  }, [message]);

  useEffect(() => {
    if (message && ACK_PATTERN.test(value.trim().toLowerCase())) {
      setValue('');
      onAcknowledge();
    }
  }, [value, message, onAcknowledge]);

  if (!message) return null;

  return (
    <Modal tone="danger" labelledBy="urgent-title" onClose={onAcknowledge}>
      <div className="mb-4 flex items-center gap-3">
        <span className="h-3 w-3 animate-breathe rounded-full bg-red-500" />
        <h2
          id="urgent-title"
          className="m-0 text-lg font-bold uppercase tracking-widest text-red-400"
        >
          Urgency: Emergency
        </h2>
      </div>
      <div className="mb-5 max-h-[50vh] overflow-y-auto">
        <Markdown text={message.text} />
      </div>
      <label
        className="mb-1 block text-xs uppercase tracking-wider text-slate-400"
        htmlFor="ack-input"
      >
        Type accepted + 4 random letters to acknowledge
      </label>
      <input
        id="ack-input"
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="acceptedabcd"
        autoComplete="off"
        spellCheck={false}
        className="w-full border-b border-red-500/50 bg-transparent px-3 py-2 font-mono text-slate-200 placeholder:text-slate-600 focus:border-red-400 focus:outline-none"
      />
    </Modal>
  );
}
