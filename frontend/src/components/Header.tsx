import type { Online } from '../hooks/useHealth';

interface Props {
  sessionId: string | null;
  online: Online;
  onNewChat: () => void;
}

function statusLabel(online: Online): string {
  return online === null ? 'checking…' : online ? 'online' : 'offline';
}

export default function Header({ sessionId, online, onNewChat }: Props) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-900 px-5 py-3">
      <div>
        <h1 className="m-0 text-base">MedGemma Agent</h1>
        <div className="text-xs text-slate-400">Qwen3 router &middot; MedGemma specialist &middot; triage classifier</div>
      </div>
      <div className="flex items-center gap-3">
        {sessionId && <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">session {sessionId.slice(0, 8)}</span>}
        {sessionId && (
          <button
            className="cursor-pointer rounded-lg border border-slate-800 bg-transparent px-5 py-2 font-normal text-slate-400 hover:text-slate-200"
            type="button"
            onClick={onNewChat}
          >
            New chat
          </button>
        )}
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
          <span className={`h-2 w-2 rounded-full ${online === false ? 'bg-red-500' : 'bg-green-500'}`} />
          {statusLabel(online)}
        </span>
      </div>
    </header>
  );
}