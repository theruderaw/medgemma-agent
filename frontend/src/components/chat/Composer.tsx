import { useEffect, useMemo, useRef, useState } from 'react';
import type { AddonInfo, AttachedImage } from '../../types';
import { fetchAddons, fetchConfig } from '../../lib/api';
import { b64Bytes, formatBytes } from '../../lib/format';
import SlashMenu from './SlashMenu';

// Backend defaults (see .env.example), in force only until GET /v1/config
// responds with the server's actual limits; a failed fetch keeps these and
// the backend still re-validates every upload.
const DEFAULT_MAX_BYTES = 5 * 1024 * 1024;
const DEFAULT_MIME_OK = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

/** Matches a trailing `/token` at the caret: start-of-text or whitespace,
 * then `/` and any tool-name characters (the partial query). */
const SLASH_TOKEN = /(?:^|\s)\/([\w-]*)$/;

interface Props {
  busy: boolean;
  /** Active conversation — scopes the add-ons' enabled flags. */
  sessionId?: string | null;
  onSend: (text: string, image?: AttachedImage, triage?: boolean) => void;
}

/**
 * Message composer: autosizing textarea, image attach (validated client-side
 * against the backend's limits), per-message triage opt-in, and a slash menu
 * (`/`) listing the available tools for appending to the message.
 */
export default function Composer({ busy, sessionId = null, onSend }: Props) {
  const [value, setValue] = useState('');
  const [image, setImage] = useState<AttachedImage | null>(null);
  const [triage, setTriage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limits, setLimits] = useState({
    maxBytes: DEFAULT_MAX_BYTES,
    mimes: DEFAULT_MIME_OK,
  });
  const [addons, setAddons] = useState<AddonInfo[] | null>(null);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const addonsLoaded = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then((cfg) => {
        if (!cancelled) {
          setLimits({ maxBytes: cfg.image_max_bytes, mimes: cfg.image_allowed_mime });
        }
      })
      .catch(() => {}); // pre-check is best-effort; backend re-validates
    return () => {
      cancelled = true;
    };
  }, []);

  // Slash-menu state: the caret's trailing /token drives everything.
  const slashQuery = !busy && !dismissed ? SLASH_TOKEN.exec(value.slice(0, caret))?.[1] ?? null : null;
  const matches = useMemo(() => {
    if (!addons || slashQuery === null) return [];
    return addons.filter((a) => a.name.toLowerCase().includes(slashQuery.toLowerCase()));
  }, [addons, slashQuery]);

  // Fetch the tool list once, when the menu first opens.
  useEffect(() => {
    if (slashQuery === null || addonsLoaded.current) return;
    addonsLoaded.current = true;
    fetchAddons(sessionId)
      .then(setAddons)
      .catch(() => setAddons([]));
  }, [slashQuery, sessionId]);

  // Keyboard highlight follows the filtered list.
  useEffect(() => {
    setActive(0);
  }, [slashQuery]);

  const applyChoice = (name: string) => {
    if (slashQuery === null) return;
    const before = value.slice(0, caret - slashQuery.length);
    const after = value.slice(caret);
    const nextCaret = before.length + name.length + 1;
    setValue(`${before}${name} ${after}`);
    setDismissed(false);
    setCaret(nextCaret);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(nextCaret, nextCaret);
    });
  };

  const resize = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  const attach = (file: File | undefined | null) => {
    if (!file) return;
    setError(null);
    const mime = file.type || (file.name.toLowerCase().endsWith('.pdf') ? 'application/pdf' : '');
    if (!limits.mimes.includes(mime)) {
      setError('Only JPEG, PNG, WebP images or PDF documents are supported.');
      return;
    }
    if (file.size > limits.maxBytes) {
      setError(`File exceeds the ${formatBytes(limits.maxBytes)} limit.`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result);
      setImage({
        b64: dataUrl.slice(dataUrl.indexOf(',') + 1),
        mime,
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
    setCaret(0);
    setDismissed(false);
    detach();
    resize();
    ref.current?.focus();
  };

  const menuOpen = slashQuery !== null;

  return (
    <footer className="px-5 pb-4">
      <div className="relative mx-auto flex w-full max-w-3xl flex-col gap-2 rounded-xl border border-neutral-200 bg-white/90 p-3 shadow-lg shadow-black/5 backdrop-blur dark:border-neutral-800 dark:bg-neutral-900/80 dark:shadow-black/40">
        {menuOpen && (
          <SlashMenu
            matches={matches}
            activeIndex={active}
            onPick={applyChoice}
            onHover={setActive}
          />
        )}
        {image && (
          <div className="flex items-center gap-2 self-start rounded-lg border border-neutral-300 bg-neutral-100 px-2 py-1.5 dark:border-neutral-700 dark:bg-neutral-800">
            {image.mime === 'application/pdf' ? (
              <span aria-hidden className="flex h-10 w-10 items-center justify-center rounded bg-white text-lg dark:bg-neutral-900">
                📄
              </span>
            ) : (
              <img src={image.previewUrl} alt="" className="h-10 w-10 rounded object-cover" />
            )}
            <span className="max-w-[180px] truncate text-xs text-neutral-700 dark:text-neutral-300">
              {image.mime.replace('application/', '').replace('image/', '').toUpperCase()} ·{' '}
              {formatBytes(b64Bytes(image.b64))}
            </span>
            <button
              type="button"
              onClick={detach}
              disabled={busy}
              aria-label="Remove image"
              className="cursor-pointer rounded px-1.5 text-neutral-500 transition-colors hover:text-neutral-900 disabled:cursor-not-allowed disabled:opacity-50 dark:text-neutral-400 dark:hover:text-neutral-100"
            >
              ✕
            </button>
          </div>
        )}
        {error && <p className="text-xs text-neutral-700 dark:text-neutral-300">{error}</p>}

        <div className="flex items-end gap-2">
          <input
            ref={fileRef}
            type="file"
            accept={limits.mimes.join(',')}
            className="hidden"
            onChange={(e) => attach(e.target.files?.[0])}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            aria-label="Attach image or PDF"
            title={`Attach a symptom photo or a prescription (image/PDF, max ${formatBytes(limits.maxBytes)})`}
            className="cursor-pointer rounded-lg border border-neutral-300 px-2.5 py-2 text-sm text-neutral-600 transition-colors hover:border-neutral-500 hover:text-neutral-900 disabled:cursor-not-allowed disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:text-neutral-100"
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
                ? 'border-neutral-900 bg-neutral-100 text-neutral-900 dark:border-neutral-100 dark:bg-neutral-800 dark:text-neutral-100'
                : 'border-neutral-300 text-neutral-500 hover:text-neutral-800 dark:border-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200'
            }`}
          >
            Triage
          </button>

          <textarea
            ref={ref}
            rows={1}
            placeholder="Describe your symptoms, ask a health question, or attach a prescription…  ( / for tools )"
            aria-label="Message"
            aria-expanded={menuOpen}
            aria-controls={menuOpen ? 'slash-menu' : undefined}
            value={value}
            disabled={busy}
            onSelect={(e) => setCaret(e.currentTarget.selectionStart ?? 0)}
            onChange={(e) => {
              setValue(e.target.value);
              setCaret(e.target.selectionStart ?? e.target.value.length);
              setDismissed(false);
              resize();
            }}
            onKeyDown={(e) => {
              if (menuOpen && matches.length > 0) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setActive((i) => (i + 1) % matches.length);
                  return;
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setActive((i) => (i - 1 + matches.length) % matches.length);
                  return;
                }
                if ((e.key === 'Enter' || e.key === 'Tab') && !e.shiftKey) {
                  e.preventDefault();
                  applyChoice(matches[active].name);
                  return;
                }
              }
              if (e.key === 'Escape' && menuOpen) {
                e.preventDefault();
                setDismissed(true);
                return;
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            className="max-h-[120px] flex-1 resize-none bg-transparent px-2 py-2 text-inherit placeholder:text-neutral-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:placeholder:text-neutral-500"
          />

          <button
            type="button"
            onClick={submit}
            disabled={busy || !value.trim()}
            className="cursor-pointer rounded-lg bg-neutral-900 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-200 disabled:text-neutral-400 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300 dark:disabled:bg-neutral-800 dark:disabled:text-neutral-500"
          >
            {busy ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </footer>
  );
}
