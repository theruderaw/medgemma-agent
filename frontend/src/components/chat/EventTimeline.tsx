import type { AuditEvent } from '../../types';
import EventStep from './EventStep';
import { WritingDots } from '../ui/StreamIndicators';

export default function EventTimeline({
    events,
    streaming,
    idPrefix,
    expanded,
    onToggle,
}: {
    events: AuditEvent[];
    /** While the note streams live, hint that more steps are coming. */
    streaming?: boolean;
    /** Stable per-message prefix for expansion keys (state lives in the
     * conversation reducer so it survives view switches). */
    idPrefix: string;
    expanded: Record<string, boolean>;
    onToggle: (key: string) => void;
}) {
    if (!events?.length) return null;
    return (
        <div className="flex max-w-xl flex-col self-start">
            {events.map((ev, i) => {
                const key = `${idPrefix}:${i}`;
                return (
                    <EventStep
                        key={key}
                        ev={ev}
                        open={!!expanded[key]}
                        onToggle={() => onToggle(key)}
                        isLast={i === events.length - 1 && !streaming}
                    />
                );
            })}
            {streaming && (
                <div className="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
                    <div className="flex w-4 shrink-0 justify-center">
                        <WritingDots className="text-neutral-500 dark:text-neutral-400" />
                    </div>
                    pipeline running
                </div>
            )}
        </div>
    );
}
