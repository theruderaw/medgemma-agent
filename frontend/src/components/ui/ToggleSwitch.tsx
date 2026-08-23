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
        checked ? 'border-accent-500/60 bg-accent-900' : 'border-ink-700 bg-ink-850'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <span
        className={`absolute top-[3px] h-4 w-4 rounded-full transition-all ${
          checked ? 'left-[24px] bg-accent-400' : 'left-[3px] bg-slate-500'
        }`}
      />
    </button>
  );
}
