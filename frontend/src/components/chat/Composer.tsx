import { useEffect, useMemo, useRef, useState } from 'react';
import type { AddonInfo, AttachedImage } from '../../types';
import { fetchAddons, fetchConfig } from '../../lib/api';
import SlashMenu from './SlashMenu';
import AttachButton from './AttachButton';
import AttachmentPreview from './AttachmentPreview';
import InputField from './InputField';
import SendButton from './SendButton';
import TriageButton from './TriageButton';

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
    onSend: (text: string, image?: AttachedImage, triage?: boolean, tool?: string) => void;
}

/**
 * Message composer orchestrator: owns the draft state, image attach,
 * per-message triage opt-in, and the slash menu (`/`) for tools. Rendering
 * is delegated to the small leaf components below.
 */
export default function Composer({ busy, sessionId = null, onSend }: Props) {
    const [value, setValue] = useState('');
    const [image, setImage] = useState<AttachedImage | null>(null);
    const [triage, setTriage] = useState(false);
    /** Tool picked from the slash menu — pinned out-of-band, never in the text. */
    const [pinnedTool, setPinnedTool] = useState<string | null>(null);
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
        // Remove the whole "/query" token from the draft — the pick is pinned
        // to the send request instead, so no tool name litters the message.
        const before = value.slice(0, caret - slashQuery.length - 1);
        const after = value.slice(caret);
        const nextCaret = before.length;
        setValue(`${before}${after}`);
        setPinnedTool(name);
        setDismissed(true);
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

    const detach = () => {
        setImage(null);
        setError(null);
    };

    const unpinTool = () => setPinnedTool(null);

    const submit = () => {
        const text = value.trim();
        if (!text || busy) return;
        onSend(text, image ?? undefined, triage, pinnedTool ?? undefined);
        setValue('');
        setTriage(false);
        setPinnedTool(null);
        setCaret(0);
        setDismissed(false);
        detach();
        resize();
        ref.current?.focus();
    };

    const menuOpen = slashQuery !== null;

    return (
        <footer className="px-5 pb-5">
            <div className="relative mx-auto flex w-full max-w-3xl flex-col gap-2 rounded-xl border border-neutral-200 bg-white/90 p-3 shadow-lg shadow-black/5 backdrop-blur dark:border-neutral-800 dark:bg-neutral-900/80 dark:shadow-black/40">
                {menuOpen && (
                    <SlashMenu
                        matches={matches}
                        activeIndex={active}
                        onPick={applyChoice}
                        onHover={setActive}
                    />
                )}
                {image && <AttachmentPreview image={image} busy={busy} onDetach={detach} />}
                {pinnedTool && (
                    <div className="flex items-center gap-2 self-start rounded-full border border-neutral-400 bg-neutral-100 px-2.5 py-1 dark:border-neutral-600 dark:bg-neutral-800">
                        <span className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                            Pinned tool
                        </span>
                        <span className="font-mono text-sm font-semibold text-neutral-800 dark:text-neutral-200">
                            /{pinnedTool}
                        </span>
                        <button
                            type="button"
                            onClick={unpinTool}
                            disabled={busy}
                            aria-label={`Unpin tool ${pinnedTool}`}
                            className="cursor-pointer rounded px-1 text-neutral-500 transition-colors hover:text-neutral-900 disabled:cursor-not-allowed disabled:opacity-50 dark:text-neutral-400 dark:hover:text-neutral-100"
                        >
                            ✕
                        </button>
                    </div>
                )}
                {error && <p className="text-sm text-neutral-700 dark:text-neutral-300">{error}</p>}

                <div className="flex items-end gap-2">
                    <AttachButton busy={busy} limits={limits} onAttach={setImage} onError={setError} />
                    <TriageButton busy={busy} triage={triage} onToggle={() => setTriage((t) => !t)} />

                    <InputField
                        ref={ref}
                        busy={busy}
                        value={value}
                        menuOpen={menuOpen}
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
                    />

                    <SendButton busy={busy} disabled={!value.trim()} onClick={submit} />
                </div>
            </div>
        </footer>
    );
}
