import { FileText } from 'lucide-react';
import type { AttachedImage } from '../../types';
import { b64Bytes, formatBytes } from '../../lib/format';

interface Props {
    image: AttachedImage;
    busy: boolean;
    onDetach: () => void;
}

export default function AttachmentPreview({ image, busy, onDetach }: Props) {
    return (
        <div className="flex items-center gap-2 self-start rounded-lg border border-neutral-300 bg-neutral-100 px-2 py-1.5 dark:border-neutral-700 dark:bg-neutral-800">
            {image.mime === 'application/pdf' ? (
                <span aria-hidden className="flex h-10 w-10 items-center justify-center rounded bg-white text-lg dark:bg-neutral-900">
                    <FileText className="h-5 w-5" aria-hidden="true" />
                </span>
            ) : (
                <img src={image.previewUrl} alt="" className="h-10 w-10 rounded object-cover" />
            )}
            <span className="max-w-[180px] truncate text-xs text-neutral-700 dark:text-neutral-300">
                {image.mime.replace('application/', '').replace('image/', '').toUpperCase()} ·{' '}
                {formatBytes(b64Bytes(image.b64))}
            </span>
            <button
                type="button"
                onClick={onDetach}
                disabled={busy}
                aria-label="Remove image"
                className="cursor-pointer rounded px-1.5 text-neutral-500 transition-colors hover:text-neutral-900 disabled:cursor-not-allowed disabled:opacity-50 dark:text-neutral-400 dark:hover:text-neutral-100"
            >
                ✕
            </button>
        </div>
    );
}
