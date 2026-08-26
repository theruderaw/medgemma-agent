import { forwardRef } from 'react';

interface InputFieldProps {
    busy: boolean;
    value: string;
    menuOpen: boolean;
    onSelect: (e: React.SyntheticEvent<HTMLTextAreaElement>) => void;
    onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
    onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
}

const InputField = forwardRef<HTMLTextAreaElement, InputFieldProps>(
    function InputField({ busy, value, menuOpen, onSelect, onChange, onKeyDown }, ref) {
        return (
            <textarea
                ref={ref}
                rows={1}
                placeholder="Describe your symptoms, ask a health question, or attach a prescription…  ( / for tools )"
                aria-label="Message"
                aria-expanded={menuOpen}
                aria-controls={menuOpen ? 'slash-menu' : undefined}
                value={value}
                disabled={busy}
                onSelect={onSelect}
                onChange={onChange}
                onKeyDown={onKeyDown}
                className="max-h-[120px] flex-1 resize-none bg-transparent px-2 py-2 text-base leading-relaxed text-inherit placeholder:text-neutral-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:placeholder:text-neutral-500"
            />
        );
    }
);

export default InputField;
