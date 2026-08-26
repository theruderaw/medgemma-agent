import type { AddonInfo } from '../../types';

interface Props {
    /** Add-ons matching the current `/query` token (already filtered). */
    matches: AddonInfo[];
    /** Index highlighted by keyboard navigation; hover syncs it back. */
    activeIndex: number;
    onPick: (name: string) => void;
    onHover: (index: number) => void;
}

/**
  * Slash-command popup: lists the registered tools (add-ons) while the
  * composer's caret sits on a `/token`. Keyboard-driven (arrows/Enter/Tab)
  * with click support; picking one appends its name to the message.
  */
export default function SlashMenu({ matches, activeIndex, onPick, onHover }: Props) {
    return (
        <div
            id="slash-menu"
            role="listbox"
            aria-label="Available tools"
            className="absolute inset-x-3 bottom-full z-20 mb-2 max-h-56 overflow-y-auto rounded-xl border border-neutral-200 bg-white shadow-xl shadow-black/10 dark:border-neutral-700 dark:bg-neutral-900 dark:shadow-black/50"
        >
            <p className="m-0 border-b border-neutral-100 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
                Tools — picking one pins this message to that tool
            </p>
            {matches.length === 0 && (
                <p className="m-0 px-3 py-2 text-xs italic text-neutral-500 dark:text-neutral-400">
                    No matching tools.
                </p>
            )}
            {matches.map((addon, i) => (
                <button
                    key={addon.name}
                    type="button"
                    role="option"
                    aria-selected={i === activeIndex}
                    onMouseEnter={() => onHover(i)}
                    onMouseDown={(e) => {
                        // mousedown (not click) so the textarea keeps focus.
                        e.preventDefault();
                        onPick(addon.name);
                    }}
                    className={`flex w-full cursor-pointer flex-col gap-0.5 px-3 py-2 text-left transition-colors ${
                        i === activeIndex
                            ? 'bg-neutral-100 dark:bg-neutral-800'
                            : 'hover:bg-neutral-50 dark:hover:bg-neutral-800/60'
                    }`}
                >
                    <span className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold text-neutral-800 dark:text-neutral-200">
                            /{addon.name}
                        </span>
                        <span
                            className={`text-xs uppercase tracking-wider ${
                                addon.enabled ? 'text-neutral-400 dark:text-neutral-500' : 'text-neutral-300 dark:text-neutral-600'
                            }`}
                        >
                            {addon.enabled ? 'enabled' : 'disabled'}
                        </span>
                    </span>
                    <span className="line-clamp-1 text-sm text-neutral-500 dark:text-neutral-400" title={addon.description}>
                        {addon.description}
                    </span>
                </button>
            ))}
        </div>
    );
}
