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
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-4 w-4" aria-hidden="true">
          <circle cx="10" cy="10" r="3.25" />
          <path
            d="M10 2.5V4M10 16v1.5M17.5 10H16M4 10H2.5M15.3 4.7l-1.06 1.06M5.76 14.24 4.7 15.3M15.3 15.3l-1.06-1.06M5.76 5.76 4.7 4.7"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
          <path d="M17.2 12.6A7.6 7.6 0 0 1 7.4 2.8a7.5 7.5 0 1 0 9.8 9.8Z" />
        </svg>
      )}
    </button>
  );
}
