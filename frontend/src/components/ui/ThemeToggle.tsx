import { Moon, Sun } from 'lucide-react';
import useTheme from '../../hooks/useTheme';

export default function ThemeToggle() {
    const { theme, toggle } = useTheme();
    const dark = theme === 'dark';
    const label = dark ? 'Switch to light mode' : 'Switch to dark mode';
    return (
        <button
            type="button"
            onClick={toggle}
            aria-label={label}
            title={label}
            className="cursor-pointer rounded-full border border-neutral-300 p-1.5 text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-800 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
        >
            {dark ? (
                <Sun className="h-4 w-4" aria-hidden="true" />
            ) : (
                <Moon className="h-4 w-4" aria-hidden="true" />
            )}
        </button>
    );
}
