import { Menu } from 'lucide-react';

interface Props {
    onMenu: () => void;
}

/** Top bar: hamburger to open the sidebar drawer (small screens only). */
export default function Header({ onMenu }: Props) {
    return (
        <header className="flex items-center border-b border-neutral-200 bg-white/70 px-5 py-3 backdrop-blur dark:border-neutral-800 dark:bg-neutral-900/70">
            <button
                type="button"
                onClick={onMenu}
                aria-label="Open conversations menu"
                className="cursor-pointer rounded-lg border border-neutral-300 p-1.5 text-neutral-500 transition-colors hover:text-neutral-800 md:hidden dark:border-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
            >
                <Menu className="h-4 w-4" aria-hidden="true" />
            </button>
        </header>
    );
}
