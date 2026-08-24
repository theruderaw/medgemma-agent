import type { PrescriptionData, PrescriptionMedication } from '../../types';

const FIELDS: { key: keyof PrescriptionMedication; label: string }[] = [
  { key: 'strength', label: 'Strength' },
  { key: 'dose', label: 'Dose' },
  { key: 'frequency', label: 'Frequency' },
  { key: 'duration', label: 'Duration' },
  { key: 'instructions', label: 'Instructions' },
];

function unreadable(value?: string | null): value is null | undefined | '' {
  return !value;
}

/**
 * Structured prescription transcription card — rendered from the dedicated
 * `structured` payload, separate from the conversational reply. Unreadable
 * fields are shown as "—" so nothing looks more legible than it was.
 */
export default function PrescriptionCard({ data }: { data: PrescriptionData }) {
  const names = Object.keys(data.medications ?? {});

  return (
    <div className="mb-2 w-full overflow-hidden rounded-lg border border-neutral-300 bg-white text-sm dark:border-neutral-700 dark:bg-neutral-950">
      <div className="flex items-center gap-2 border-b border-neutral-200 bg-neutral-100 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
        <span aria-hidden>℞</span>
        Prescription
        <span className="ml-auto font-normal normal-case tracking-normal text-neutral-500">
          {names.length === 0 ? 'nothing readable' : `${names.length} medication${names.length === 1 ? '' : 's'}`}
        </span>
      </div>

      {names.length === 0 ? (
        <p className="px-3 py-2 text-xs italic text-neutral-500">
          No medications could be read from this document. Please verify with your pharmacist.
        </p>
      ) : (
        <ul className="divide-y divide-neutral-200 dark:divide-neutral-800">
          {names.map((name) => {
            const med = data.medications[name];
            return (
              <li key={name} className="px-3 py-2">
                <p className="font-semibold text-neutral-900 dark:text-neutral-100">{name}</p>
                <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 text-xs text-neutral-700 dark:text-neutral-300">
                  {FIELDS.map(({ key, label }) => (
                    <div key={key} className="contents">
                      <dt className="text-neutral-500 dark:text-neutral-400">{label}</dt>
                      <dd className={unreadable(med?.[key]) ? 'italic text-neutral-400 dark:text-neutral-600' : ''}>
                        {unreadable(med?.[key]) ? '— unreadable —' : med[key]}
                      </dd>
                    </div>
                  ))}
                </dl>
              </li>
            );
          })}
        </ul>
      )}

      {(data.clarifications?.length ?? 0) > 0 && (
        <div className="border-t border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-900 dark:bg-amber-950/40">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
            Needs your input
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-amber-800 dark:text-amber-300">
            {data.clarifications!.map((ask) => (
              <li key={ask}>{ask}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="border-t border-neutral-200 px-3 py-1.5 text-[11px] text-neutral-500 dark:border-neutral-800">
        Machine-read transcription — verify against the original prescription before acting on it.
      </p>
    </div>
  );
}
