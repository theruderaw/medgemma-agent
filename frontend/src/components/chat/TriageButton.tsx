interface Props {
    busy: boolean;
    triage: boolean;
    onToggle: () => void;
}

export default function TriageButton({ busy, triage, onToggle }: Props) {
    return (
        <button
            type="button"
            onClick={onToggle}
            disabled={busy}
            aria-pressed={triage}
            title="Classify this message's urgency before the specialist sees it (?triage=true)"
            className={`cursor-pointer rounded-full border px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                triage
                    ? 'border-neutral-900 bg-neutral-100 text-neutral-900 dark:border-neutral-100 dark:bg-neutral-800 dark:text-neutral-100'
                    : 'border-neutral-300 text-neutral-500 hover:text-neutral-800 dark:border-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200'
            }`}
        >
            Triage
        </button>
    );
}
