interface Props {
    checked: boolean;
    disabled?: boolean;
    label: string;
    onToggle: () => void;
}

/** Accessible switch control (role="switch") with the accent track. */
export default function ToggleSwitch({ checked, disabled, label, onToggle }: Props) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            aria-label={label}
            disabled={disabled}
            onClick={onToggle}
            className={`relative h-6 w-11 shrink-0 cursor-pointer rounded-full border transition-colors ${
                checked
                    ? 'border-neutral-900 bg-neutral-900 dark:border-neutral-100 dark:bg-neutral-100'
                    : 'border-neutral-300 bg-neutral-200 dark:border-neutral-700 dark:bg-neutral-800'
            } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
        >
            <span
                className={`absolute top-[3px] h-4 w-4 rounded-full transition-all ${
                    checked ? 'left-[24px] bg-white dark:bg-neutral-900' : 'left-[3px] bg-neutral-500 dark:bg-neutral-400'
                }`}
            />
        </button>
    );
}
