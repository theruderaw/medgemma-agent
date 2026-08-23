import { useCallback, useEffect, useReducer, useRef } from 'react';
import {
  ApiError,
  enqueueTurn,
  fetchAuditEvents,
  fetchSessionHistory,
  pollUntilDone,
  resetSession,
  watchJob,
} from '../lib/api';
import type { AttachedImage, AuditEvent, ChatResponse } from '../types';

// ---------------------------------------------------------------------------
// ChatMessage: the UI's view of one bubble. Wire types stay in types.ts.

export type ChatRole = 'user' | 'assistant' | 'error';

export interface ChatMessage {
  id: number;
  role: ChatRole;
  text: string;
  thinking?: boolean;
  streaming?: boolean;
  urgency?: ChatResponse['urgency'];
  events?: AuditEvent[];
  /** Server pipeline turn this message belongs to — links restored chats to
   * their persisted audit timeline after a reload. */
  turnId?: string | null;
  /** Client-side preview of an image attached to a user message. */
  imagePreview?: string;
  /** MedGemma clinical note, accumulated live from specialist_token events. */
  specialistNote?: string;
  specialistStreaming?: boolean;
}

// ---------------------------------------------------------------------------
// State machine. One action per UI event; every transition is total.

interface ConversationState {
  messages: ChatMessage[];
  sessionId: string | null;
  busy: boolean;
  /** Emergency turn awaiting typed acknowledgment (blocks the whole app). */
  urgent: ChatMessage | null;
  /** Open event-timeline steps, keyed `${messageId}:${index}`. Lives here so
   * it survives view switches (ChatView unmounts) instead of per-component
   * useState that resets every time. */
  expandedSteps: Record<string, boolean>;
}

type ConversationAction =
  | { type: 'send_start'; user: ChatMessage; thinking: ChatMessage }
  | { type: 'stream_token'; messageId: number; delta: string }
  | { type: 'specialist_token'; messageId: number; delta: string }
  | { type: 'pipeline_event'; messageId: number; event: AuditEvent }
  | { type: 'session_known'; sessionId: string }
  | { type: 'history_loaded'; messages: ChatMessage[] }
  | { type: 'history_missing' }
  | { type: 'turn_success'; data: ChatResponse; thinkingId: number }
  | { type: 'turn_error'; message: ChatMessage; thinkingId: number; sessionGone: boolean }
  | { type: 'acknowledge' }
  | { type: 'new_chat' }
  | { type: 'switch_session'; sessionId: string }
  | { type: 'toggle_step'; key: string };

const SESSION_KEY = 'medgemma:session_id';

const initialState: ConversationState = {
  messages: [],
  // Session identity survives reloads; the conversation itself is restored
  // from Postgres by the history effect below.
  sessionId: localStorage.getItem(SESSION_KEY),
  busy: false,
  urgent: null,
  expandedSteps: {},
};

function patchMessage(
  state: ConversationState,
  messageId: number,
  patch: (m: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return state.messages.map((m) => (m.id === messageId ? patch(m) : m));
}

function reducer(state: ConversationState, action: ConversationAction): ConversationState {
  switch (action.type) {
    case 'send_start':
      return { ...state, busy: true, messages: [...state.messages, action.user, action.thinking] };

    case 'stream_token':
      if (!action.delta) return state;
      return {
        ...state,
        messages: patchMessage(state, action.messageId, (m) => ({
          ...m,
          thinking: false,
          streaming: true,
          text: m.thinking ? action.delta : m.text + action.delta,
        })),
      };

    case 'specialist_token':
      return {
        ...state,
        messages: patchMessage(state, action.messageId, (m) => ({
          ...m,
          specialistNote: (m.specialistNote ?? '') + action.delta,
          specialistStreaming: true,
        })),
      };

    case 'pipeline_event':
      return {
        ...state,
        messages: patchMessage(state, action.messageId, (m) => ({
          ...m,
          turnId: m.turnId ?? action.event.turn_id ?? null,
          events: [...(m.events ?? []), action.event],
        })),
      };

    case 'session_known':
      return state.sessionId ? state : { ...state, sessionId: action.sessionId };

    case 'history_loaded':
      // Restore only into an otherwise-empty view; a live turn always wins.
      if (state.messages.length || state.busy) return state;
      return { ...state, messages: action.messages };

    case 'history_missing':
      // The stored session expired server-side — start clean.
      return { ...state, sessionId: null, messages: [] };

    case 'turn_success': {
      const base =
        state.messages.find((m) => m.id === action.thinkingId) ?? {
          id: action.thinkingId,
          role: 'assistant' as const,
          text: action.data.response,
        };
      const assistant: ChatMessage = {
        ...base,
        thinking: false,
        streaming: false,
        text: action.data.response,
        urgency: action.data.urgency,
        events: action.data.events ?? [],
        turnId:
          base.turnId ??
          action.data.events?.find((e) => e.turn_id)?.turn_id ??
          null,
        specialistStreaming: false,
      };
      return {
        ...state,
        busy: false,
        sessionId: action.data.session_id,
        messages: patchMessage(state, action.thinkingId, () => assistant),
        urgent: action.data.urgency === 'emergency' ? assistant : state.urgent,
      };
    }

    case 'turn_error':
      return {
        ...state,
        busy: false,
        sessionId: action.sessionGone ? null : state.sessionId,
        messages: state.messages
          .filter((m) => m.id !== action.thinkingId)
          .concat(action.message),
      };

    case 'acknowledge':
      return { ...state, urgent: null };

    case 'new_chat':
      return {
        ...state,
        busy: false,
        messages: [],
        sessionId: null,
        urgent: null,
        expandedSteps: {},
      };

    case 'switch_session':
      return {
        ...state,
        sessionId: action.sessionId,
        messages: [],
        busy: false,
        urgent: null,
        expandedSteps: {},
      };

    case 'toggle_step':
      return {
        ...state,
        expandedSteps: { ...state.expandedSteps, [action.key]: !state.expandedSteps[action.key] },
      };
  }
}

// ---------------------------------------------------------------------------

/** Group audit rows (newest-first) into ordered per-turn timelines. */
function groupEventsByTurn(records: Awaited<ReturnType<typeof fetchAuditEvents>>) {
  const byTurn = new Map<string, AuditEvent[]>();
  for (const r of [...records].reverse()) {
    if (!r.turn_id) continue;
    const list = byTurn.get(r.turn_id) ?? [];
    list.push({
      module: r.module,
      event_type: r.event_type,
      payload: r.payload,
      turn_id: r.turn_id,
    });
    byTurn.set(r.turn_id, list);
  }
  return byTurn;
}

// ---------------------------------------------------------------------------
// Hook

export function useConversation() {
  const [state, dispatch] = useReducer(reducer, undefined, () => initialState);
  const nextId = useRef(0);
  const closeWatcher = useRef<(() => void) | null>(null);

  const freshId = () => nextId.current++;

  useEffect(() => {
    if (state.sessionId) localStorage.setItem(SESSION_KEY, state.sessionId);
    else localStorage.removeItem(SESSION_KEY);
  }, [state.sessionId]);

  // Stop the SSE watcher on unmount.
  useEffect(() => () => closeWatcher.current?.(), []);

  /**
   * Load a conversation + its audit timeline from Postgres into the view.
   * Used both by the mount-time restore and by switching sessions from the
   * recent-chats menu. The timeline join is best-effort: a failed audit fetch
   * still restores the plain conversation.
   */
  const loadSession = useCallback(async (sessionId: string): Promise<boolean> => {
    try {
      const [history, records] = await Promise.all([
        fetchSessionHistory(sessionId),
        fetchAuditEvents({ id: sessionId, limit: 500 }).catch(() => []),
      ]);
      const byTurn = groupEventsByTurn(records);
      const messages: ChatMessage[] = history.messages.map((m) => ({
        id: freshId(),
        role: m.role,
        text: m.content,
        turnId: m.turn_id ?? null,
        events: m.turn_id ? byTurn.get(m.turn_id) : undefined,
      }));
      if (messages.length) dispatch({ type: 'history_loaded', messages });
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        dispatch({ type: 'history_missing' });
      }
      // Network hiccups keep the session; the next successful turn re-syncs.
      return false;
    }
    // freshId is a stable ref-based counter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Restore the persisted conversation once on mount when a stored session
  // exists (page refresh / revisit). A 404 means it expired server-side.
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current || !state.sessionId || state.busy) return;
    restored.current = true;
    void loadSession(state.sessionId);
    // Run once per mount — exactly the stored-session restore window.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const send = useCallback(
    async (text: string, image?: AttachedImage, triage = false) => {
      const trimmed = text.trim();
      if (!trimmed || state.busy) return;

      const user: ChatMessage = {
        id: freshId(),
        role: 'user',
        text: trimmed,
        imagePreview: image?.previewUrl,
      };
      const thinking: ChatMessage = {
        id: freshId(),
        role: 'assistant',
        text: 'Assistant is thinking…',
        thinking: true,
      };
      dispatch({ type: 'send_start', user, thinking });

      const fail = (message: string, sessionGone = false) => {
        dispatch({
          type: 'turn_error',
          message: { id: freshId(), role: 'error', text: message },
          sessionGone,
          thinkingId: thinking.id,
        });
      };

      try {
        const outcome = await enqueueTurn(trimmed, state.sessionId, image, triage);

        // Emergency floor matched: the full response arrived synchronously.
        if (outcome.kind === 'sync') {
          dispatch({ type: 'turn_success', data: outcome.data, thinkingId: thinking.id });
          return;
        }

        // Queued: capture the session id immediately so a refresh keeps it,
        // then watch the job's event stream live.
        dispatch({ type: 'session_known', sessionId: outcome.data.session_id });

        let polling = false;
        const startPollingFallback = () => {
          if (polling) return;
          polling = true;
          pollUntilDone(outcome.data.job_id)
            .then((data) => dispatch({ type: 'turn_success', data, thinkingId: thinking.id }))
            .catch((err) => fail(err instanceof Error ? err.message : 'Turn failed'));
        };

        const close = watchJob(outcome.data.job_id, {
          onToken: (delta) => dispatch({ type: 'stream_token', messageId: thinking.id, delta }),
          onSpecialistToken: (delta) =>
            dispatch({ type: 'specialist_token', messageId: thinking.id, delta }),
          onPipeline: (event) =>
            dispatch({ type: 'pipeline_event', messageId: thinking.id, event }),
          onResult: (data) => {
            close();
            dispatch({ type: 'turn_success', data, thinkingId: thinking.id });
          },
          onError: (message) => {
            close();
            fail(message);
          },
          onConnectionLost: () => {
            close();
            startPollingFallback();
          },
        });
        closeWatcher.current?.();
        closeWatcher.current = close;
      } catch (err) {
        fail(
          err instanceof Error ? err.message : 'Request failed',
          err instanceof ApiError && err.gone,
        );
      }
    },
    [state.busy, state.sessionId],
  );

  const newChat = useCallback(async () => {
    closeWatcher.current?.();
    closeWatcher.current = null;
    if (state.sessionId) {
      try {
        await resetSession(state.sessionId);
      } catch {
        /* best-effort reset */
      }
    }
    dispatch({ type: 'new_chat' });
  }, [state.sessionId]);

  /** Jump to another existing conversation from the recent-chats menu. */
  const switchSession = useCallback(
    async (sessionId: string) => {
      if (state.busy || sessionId === state.sessionId) return;
      closeWatcher.current?.();
      closeWatcher.current = null;
      dispatch({ type: 'switch_session', sessionId });
      await loadSession(sessionId);
    },
    [state.busy, state.sessionId, loadSession],
  );

  const acknowledge = useCallback(() => dispatch({ type: 'acknowledge' }), []);

  const toggleStep = useCallback(
    (key: string) => dispatch({ type: 'toggle_step', key }),
    [],
  );

  return { state, send, newChat, acknowledge, switchSession, toggleStep };
}
