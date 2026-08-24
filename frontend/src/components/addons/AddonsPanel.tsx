import { useAddons } from '../../hooks/useAddons';
import Badge from '../ui/Badge';
import ToggleSwitch from '../ui/ToggleSwitch';

interface Props {
  sessionId: string | null;
}

/** Per-session add-on toggles (router-selectable addons). */
export default function AddonsPanel({ sessionId }: Props) {
  const { addons, loading, error, pending, toggle } = useAddons(sessionId);

  return (
    <main aria-live="polite" className="flex flex-1 flex-col overflow-y-auto p-5">
      <div className="mx-auto flex w-full max-w-xl flex-col gap-3">
        <header>
          <h2 className="m-0 text-sm font-semibold uppercase tracking-widest text-neutral-400">
            Add-ons
          </h2>
          <p className="m-0 mt-1 text-xs text-neutral-500">
            Capabilities the router may pick during a turn. Toggles are saved per
            conversation{sessionId ? '' : ' — start a chat first to change them'}.
          </p>
        </header>

        {error && (
          <div
            role="alert"
            className="rounded-lg border border-neutral-400 bg-neutral-100 px-3 py-2 text-xs text-neutral-800 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200"
          >
            {error}
          </div>
        )}
        {loading && <div className="text-xs italic text-neutral-500">Loading add-ons…</div>}

        {!loading &&
          addons.map((f) => (
            <div key={f.name} className="panel flex items-start justify-between gap-4 p-3.5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-neutral-700 dark:text-neutral-200">{f.description}</span>
                  {f.disclaimer_level === 'high' && (
                    <Badge tone="high" title="Outputs from this add-on always carry a professional-review disclaimer">
                      high stakes
                    </Badge>
                  )}
                </div>
                <code className="mt-1 block truncate font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
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
    </main>
  );
}
