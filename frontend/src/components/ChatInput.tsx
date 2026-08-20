import { useRef, useState } from 'react';

interface Props {
  busy: boolean;
  onSend: (text: string) => void;
}

export default function ChatInput({ busy, onSend }: Props) {
  const [value, setValue] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);

  const resize = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    onSend(text);
    setValue('');
    resize();
    ref.current?.focus();
  };

  return (
    <footer className="flex gap-2.5 border-t border-slate-800 bg-slate-900 px-5 py-3">
      <textarea
        ref={ref}
        rows={1}
        placeholder="Describe your symptoms or ask a health question…"
        aria-label="Message"
        value={value}
        disabled={busy}
        onChange={(e) => {
          setValue(e.target.value);
          resize();
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        className="max-h-[120px] flex-1 resize-none rounded-lg border border-transparent bg-slate-800 px-2.5 py-2.5 text-inherit placeholder:text-slate-500 focus:border-sky-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
      />
      <button
        className="cursor-pointer rounded-lg bg-sky-400 px-5 font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
        type="button"
        onClick={submit}
        disabled={busy}
      >
        {busy ? '…' : 'Send'}
      </button>
    </footer>
  );
}