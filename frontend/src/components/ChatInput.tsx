import { useRef, useState } from 'react';
import type { AttachedImage } from '../types';

const MAX_BYTES = 5 * 1024 * 1024;
const MIME_OK = ['image/jpeg', 'image/png', 'image/webp'];

interface Props {
  busy: boolean;
  onSend: (text: string, image?: AttachedImage, triage?: boolean) => void;
}

export default function ChatInput({ busy, onSend }: Props) {
  const [value, setValue] = useState('');
  const [image, setImage] = useState<AttachedImage | null>(null);
  const [triage, setTriage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const resize = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  const attach = (file: File | undefined | null) => {
    if (!file) return;
    setError(null);
    if (!MIME_OK.includes(file.type)) {
      setError('Only JPEG, PNG or WebP images are supported.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('Image exceeds the 5 MB limit.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result);
      setImage({
        b64: dataUrl.slice(dataUrl.indexOf(',') + 1),
        mime: file.type,
        previewUrl: dataUrl,
      });
    };
    reader.readAsDataURL(file);
  };

  const detach = () => {
    setImage(null);
    setError(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    onSend(text, image ?? undefined, triage);
    setValue('');
    setTriage(false);
    detach();
    resize();
    ref.current?.focus();
  };

  return (
    <footer className="flex flex-col gap-2 border-t border-slate-800 bg-slate-900 px-5 py-3">
      {image && (
        <div className="flex items-center gap-2 self-start px-2 py-1.5">
          <img src={image.previewUrl} alt="" className="h-10 w-10 rounded object-cover" />
          <span className="max-w-[180px] truncate text-xs text-slate-300">
            {image.mime.replace('image/', '').toUpperCase()} · {(image.b64.length * 0.75 / 1024).toFixed(0)} KB
          </span>
          <button
            type="button"
            onClick={detach}
            disabled={busy}
            aria-label="Remove image"
            className="cursor-pointer rounded px-1.5 text-slate-400 transition-colors hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            ✕
          </button>
        </div>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="flex gap-2.5">
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => attach(e.target.files?.[0])}
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          aria-label="Attach image"
          title="Attach an image of a visual symptom (JPEG/PNG/WebP, max 5 MB)"
          className="cursor-pointer px-3 text-slate-300 transition-colors hover:text-sky-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          📎
        </button>
        <button
          type="button"
          onClick={() => setTriage((t) => !t)}
          disabled={busy}
          aria-pressed={triage}
          title="Classify this message's urgency before the specialist sees it (?triage=true)"
          className={`cursor-pointer rounded-full border px-2.5 py-0.5 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
            triage
              ? 'border-sky-400 bg-sky-950 text-sky-300'
              : 'border-slate-700 text-slate-400 hover:text-slate-200'
          }`}
        >
          Triage
        </button>
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
          className="max-h-[120px] flex-1 resize-none border-b border-slate-700 bg-transparent px-2.5 py-2.5 text-inherit placeholder:text-slate-500 focus:border-sky-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        />
        <button
          className="cursor-pointer px-5 font-semibold text-sky-400 transition-colors hover:text-sky-300 disabled:cursor-not-allowed disabled:opacity-50"
          type="button"
          onClick={submit}
          disabled={busy}
        >
          {busy ? '…' : 'Send'}
        </button>
      </div>
    </footer>
  );
}
