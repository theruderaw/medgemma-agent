import { Plus } from 'lucide-react';

interface Props {
    onClick: () => void;
}

export default function NewButton({ onClick }: Props) {
    return (
        <div className="px-3">
            <button
                type="button"
                onClick={onClick}
                className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border border-neutral-300 bg-neutral-100 px-3 py-2 text-base font-medium text-neutral-800 transition-colors hover:border-neutral-400 hover:bg-neutral-200 dark:border-neutral-700 dark:bg-neutral-800/60 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
                <Plus className="h-4 w-4" aria-hidden="true" />
                New chat
            </button>
        </div>
    );
}
