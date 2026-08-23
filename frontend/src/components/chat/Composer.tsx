import { useRef, useState } from 'react';
import type { AttachedImage } from '../../types';
import { b64Bytes, formatBytes } from '../../lib/format';

const MAX_BYTES = 5 * 1024 * 1024;
const MIME_OK = ['image/jpeg', 'image/png', 'image/webp'];

interface Props {
  busy: boolean;
  onSend: (text: string, image?: AttachedImage, triage?: boolean) => void;
}

/**
 * Message composer: autosizing textarea, image attach (validated client-side
 * against the backend's limits), and the per-message triage opt-in.
 */
export default function Composer({ busy, onSend }: Props) {
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
      setError(`Image exceeds the ${formatBytes(MAX_BYTES)} limit.`);
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
    <footer className="px-5 pb-4">
      <div className="panel mx-auto flex w-full max-w-3xl flex-col gap-2 p-3 shadow-lg shadow-black/40">
        {image && (
          <div className="flex items-center gap-2 self-start rounded-lg border border-ink-700 bg-ink-850 px-2 py-1.5">
            <img src={image.previewUrl} alt="" className="h-10 w-10 rounded object-cover" />
            <span className="max-w-[180px] truncate text-xs text-slate-300">
              {image.mime.replace('image/', '').toUpperCase()} · {formatBytes(b64Bytes(image.b64))}
            </span>
            <button
              type="button"
              onClick={detach}
              disabled={busy}
              aria-label="Remove image"
              className="cursor-pointer rounded px-1.5 text-slate-400 transition-colors hover:text-accent-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              ✕
            </button>
          </div>
        )}
        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex items-end gap-2">
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
            className="cursor-pointer rounded-lg border border-ink-700 px-2.5 py-2 text-sm text-slate-300 transition-colors hover:border-accent-500/50 hover:text-accent-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            📎
          </button>
          <button
            type="button"
            onClick={() => setTriage((t) => !t)}
            disabled={busy}
            aria-pressed={triage}
            title="Classify this message's urgency before the specialist sees it (?triage=true)"
            className={`cursor-pointer rounded-full border px-3 py-1.5 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              triage
                ? 'border-accent-400 bg-accent-900 text-accent-300'
                : 'border-ink-700 text-slate-400 hover:text-slate-200'
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
            className="max-h-[120px] flex-1 resize-none bg-transparent px-2 py-2 text-inherit placeholder:text-slate-600 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          />

          <button
            type="button"
            onClick={submit}
            disabled={busy || !value.trim()}
            className="cursor-pointer rounded-lg bg-accent-500/90 px-5 py-2 text-sm font-semibold text-ink-950 transition-colors hover:bg-accent-400 disabled:cursor-not-allowed disabled:bg-ink-800 disabled:text-slate-500"
          >
            {busy ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </footer>
  );
}
