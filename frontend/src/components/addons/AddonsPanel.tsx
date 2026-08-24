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
          <h2 className="m-0 text-sm font-semibold uppercase tracking-widest text-slate-300">
            Add-ons
          </h2>
          <p className="m-0 mt-1 text-xs text-slate-500">
            Capabilities the router may pick during a turn. Toggles are saved per
            conversation{sessionId ? '' : ' — start a chat first to change them'}.
          </p>
        </header>

        {error && (
          <div
            role="alert"
            className="rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300"
          >
            {error}
          </div>
        )}
        {loading && <div className="text-xs italic text-slate-500">Loading add-ons…</div>}

        {!loading &&
          addons.map((f) => (
            <div key={f.name} className="panel flex items-start justify-between gap-4 p-3.5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-200">{f.description}</span>
                  {f.disclaimer_level === 'high' && (
                    <Badge tone="high" title="Outputs from this add-on always carry a professional-review disclaimer">
                      high stakes
                    </Badge>
                  )}
                </div>
                <code className="mt-1 block truncate font-mono text-[10px] text-slate-600">
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
