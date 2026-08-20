import { useEffect, useRef, useState } from 'react';
import type { Message } from '../types';
import Markdown from './Markdown';

const ACK_PATTERN = /^accepted[a-z]{4}$/;

interface Props {
  message: Message | null;
  onAcknowledge: () => void;
}

export default function UrgencyModal({ message, onAcknowledge }: Props) {
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="urgent-title"
    >
      <div className="w-full max-w-lg rounded-xl border-2 border-red-500 bg-slate-900 p-6 shadow-2xl">
        <div className="mb-4 flex items-center gap-3">
          <span className="h-3 w-3 rounded-full bg-red-500" />
          <h2 id="urgent-title" className="m-0 text-lg font-bold uppercase tracking-widest text-red-400">
            Urgency: Urgent
          </h2>
        </div>
        <div className="mb-5 max-h-[50vh] overflow-y-auto">
          <Markdown text={message.text} />
        </div>
        <label className="mb-1 block text-xs uppercase tracking-wider text-slate-400" htmlFor="ack-input">
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
          className="w-full rounded-lg border border-red-500/50 bg-slate-800 px-3 py-2 font-mono text-slate-200 placeholder:text-slate-500 focus:border-red-400 focus:outline-none"
        />
      </div>
    </div>
  );
}