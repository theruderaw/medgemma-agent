/** Inline "MedGemma is writing" indicator. */
export function WritingDots({ className = 'text-emerald-400' }: { className?: string }) {
  return (
    <span className={`flex gap-0.5 ${className}`} aria-label="streaming">
      <span className="h-1 w-1 animate-bounce rounded-full bg-current [animation-delay:0ms]" />
      <span className="h-1 w-1 animate-bounce rounded-full bg-current [animation-delay:150ms]" />
      <span className="h-1 w-1 animate-bounce rounded-full bg-current [animation-delay:300ms]" />
    </span>
  );
}

/** Block caret appended to text while tokens stream in. */
export function StreamCaret() {
  return (
    <span className="ml-0.5 inline-block h-3.5 w-[7px] animate-blink bg-accent-400 align-text-bottom" />
  );
}
