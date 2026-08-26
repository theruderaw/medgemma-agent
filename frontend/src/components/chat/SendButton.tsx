interface Props {
    busy: boolean;
    disabled: boolean;
    onClick: () => void;
}

export default function SendButton({ busy, disabled, onClick }: Props) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={busy || disabled}
            className="cursor-pointer rounded-lg bg-neutral-900 px-6 py-2 text-base font-semibold text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-200 disabled:text-neutral-400 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300 dark:disabled:bg-neutral-800 dark:disabled:text-neutral-500"
        >
            {busy ? '…' : 'Send'}
        </button>
    );
}
