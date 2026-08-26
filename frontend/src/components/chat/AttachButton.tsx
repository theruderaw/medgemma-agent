import { useRef } from 'react';
import { Paperclip } from 'lucide-react';
import type { AttachedImage } from '../../types';
import { formatBytes } from '../../lib/format';

interface Props {
    busy: boolean;
    limits: { maxBytes: number; mimes: string[] };
    onAttach: (image: AttachedImage) => void;
    onError: (msg: string) => void;
}

export default function AttachButton({ busy, limits, onAttach, onError }: Props) {
    const fileRef = useRef<HTMLInputElement>(null);

    const attach = (file: File | undefined | null) => {
        if (!file) return;
        const mime = file.type || (file.name.toLowerCase().endsWith('.pdf') ? 'application/pdf' : '');
        if (!limits.mimes.includes(mime)) {
            onError('Only JPEG, PNG, WebP images or PDF documents are supported.');
            return;
        }
        if (file.size > limits.maxBytes) {
            onError(`File exceeds the ${formatBytes(limits.maxBytes)} limit.`);
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const dataUrl = String(reader.result);
            onAttach({
                b64: dataUrl.slice(dataUrl.indexOf(',') + 1),
                mime,
                previewUrl: dataUrl,
            });
        };
        reader.readAsDataURL(file);
    };

    return (
        <>
            <input
                ref={fileRef}
                type="file"
                accept={limits.mimes.join(',')}
                className="hidden"
                onChange={(e) => attach(e.target.files?.[0])}
            />
            <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
                aria-label="Attach image or PDF"
                title={`Attach a symptom photo or a prescription (image/PDF, max ${formatBytes(limits.maxBytes)})`}
                className="cursor-pointer rounded-lg border border-neutral-300 px-2.5 py-2 text-sm text-neutral-600 transition-colors hover:border-neutral-500 hover:text-neutral-900 disabled:cursor-not-allowed disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:text-neutral-100"
            >
                <Paperclip className="h-4 w-4" aria-hidden="true" />
            </button>
        </>
    );
}
