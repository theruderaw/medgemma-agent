import { useEffect } from 'react';
import { useAddons } from '../../hooks/useAddons';
import Badge from '../ui/Badge';
import ToggleSwitch from '../ui/ToggleSwitch';

interface Props {
    sessionId: string | null;
    open: boolean;
    onClose: () => void;
}

export default function SettingsDropdown({ sessionId, open, onClose }: Props) {
    const { addons, loading, error, pending, toggle } = useAddons(sessionId);

    useEffect(() => {
        if (!open) return;
        const onMouseDown = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            if (!target.closest('[data-settings-dropdown]')) onClose();
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('mousedown', onMouseDown);
        window.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onMouseDown);
            window.removeEventListener('keydown', onKey);
        };
    }, [open, onClose]);

    if (!open) return null;

    return (
        <div
            data-settings-dropdown
            role="dialog"
            aria-label="Add-on settings"
            className="absolute right-0 top-full z-50 mt-2 max-h-80 w-80 overflow-y-auto rounded-xl border border-neutral-200 bg-white p-3 shadow-xl shadow-black/10 dark:border-neutral-800 dark:bg-neutral-900 dark:shadow-black/50"
        >
            <p className="m-0 mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-400">
                Add-ons
            </p>
            {error && (
                <div
                    role="alert"
                    className="rounded-lg border border-neutral-400 bg-neutral-100 px-3 py-2 text-sm text-neutral-800 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200"
                >
                    {error}
                </div>
            )}
            {loading && <div className="text-sm italic text-neutral-500">Loading add-ons…</div>}
            {!loading && addons.length === 0 && (
                <p className="m-0 px-1 py-1 text-sm italic text-neutral-500">No add-ons available.</p>
            )}
            {!loading &&
                addons.map((f) => (
                    <div key={f.name} className="flex items-start justify-between gap-3 py-2">
                        <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-1.5">
                                <span className="text-xs text-neutral-700 dark:text-neutral-200">{f.description}</span>
                                {f.disclaimer_level === 'high' && (
                                    <Badge tone="high" title="Outputs from this add-on always carry a professional-review disclaimer">
                                        high stakes
                                    </Badge>
                                )}
                            </div>
                            <code className="mt-0.5 block truncate font-mono text-xs text-neutral-500 dark:text-neutral-400">
                                {f.name}
                            </code>
                        </div>
                        <ToggleSwitch
                            checked={f.enabled}
                            disabled={!sessionId || pending === f.name}
                            label={`Toggle ${f.name}`}
                            onToggle={() => toggle(f)}
                        />
                    </div>
                ))}
        </div>
    );
}
