import { useCallback, useEffect, useReducer, useRef } from 'react';
import { ApiError, enqueueTurn, pollUntilDone, resetSession, watchJob } from '../lib/api';
import type { AttachedImage, AuditEvent, ChatResponse, Message } from '../types';

const SESSION_KEY = 'medgemma:session_id';

export interface ChatState {
  messages: Message[];
  sessionId: string | null;
  busy: boolean;
  urgent: Message | null;
}

export type ChatAction =
  | { type: 'send_start'; user: Message; thinking: Message }
  | { type: 'stream_token'; messageId: number; delta: string }
  | { type: 'specialist_token'; messageId: number; delta: string }
  | { type: 'pipeline_event'; messageId: number; event: AuditEvent }
  | { type: 'session_known'; sessionId: string }
  | { type: 'turn_success'; data: ChatResponse; thinkingId: number }
  | { type: 'turn_error'; message: Message; gone: boolean; thinkingId: number }
  | { type: 'acknowledge' }
  | { type: 'new_chat' };

const initChatState = (): ChatState => ({
  messages: [],
  sessionId: localStorage.getItem(SESSION_KEY),
  busy: false,
  urgent: null,
});

function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'send_start':
      return { ...state, busy: true, messages: [...state.messages, action.user, action.thinking] };
    case 'stream_token':
      if (!action.delta) return state;
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.messageId
            ? {
                ...m,
                thinking: false,
                streaming: true,
                text: m.thinking ? action.delta : m.text + action.delta,
              }
            : m,
        ),
      };
    case 'specialist_token':
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.messageId
            ? {
                ...m,
                specialistNote: (m.specialistNote ?? '') + action.delta,
                specialistStreaming: true,
              }
            : m,
        ),
      };
    case 'pipeline_event':
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.messageId
            ? { ...m, events: [...(m.events ?? []), action.event] }
            : m,
        ),
      };
    case 'session_known':
      return state.sessionId ? state : { ...state, sessionId: action.sessionId };
    case 'turn_success': {
      const base =
        state.messages.find((m) => m.id === action.thinkingId) ?? {
          id: action.thinkingId,
          role: 'assistant' as const,
          text: action.data.response,
        };
      const assistant: Message = {
        ...base,
        thinking: false,
        streaming: false,
        text: action.data.response,
        urgency: action.data.urgency,
        events: action.data.events ?? [],
        specialistStreaming: false,
      };
      return {
        ...state,
        busy: false,
        sessionId: action.data.session_id,
        messages: state.messages.map((m) => (m.id === action.thinkingId ? assistant : m)),
        urgent: action.data.urgency === 'emergency' ? assistant : state.urgent,
      };
    }
    case 'turn_error':
      return {
        ...state,
        busy: false,
        sessionId: action.gone ? null : state.sessionId,
        messages: state.messages.filter((m) => m.id !== action.thinkingId).concat(action.message),
      };
    case 'acknowledge':
      return { ...state, urgent: null };
    case 'new_chat':
      return { ...state, busy: false, messages: [], sessionId: null, urgent: null };
  }
}

export function useChat() {
  const [state, dispatch] = useReducer(chatReducer, undefined, initChatState);
  const nextId = useRef(0);
  const closeWatcher = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (state.sessionId) localStorage.setItem(SESSION_KEY, state.sessionId);
    else localStorage.removeItem(SESSION_KEY);
  }, [state.sessionId]);

  // Stop the SSE watcher when the component unmounts.
  useEffect(() => () => closeWatcher.current?.(), []);

  const send = useCallback(
    async (text: string, image?: AttachedImage, triage = false) => {
      const trimmed = text.trim();
      if (!trimmed || state.busy) return;

      const user: Message = {
        id: nextId.current++,
        role: 'user',
        text: trimmed,
        imagePreview: image?.previewUrl,
      };
      const thinking: Message = {
        id: nextId.current++,
        role: 'assistant',
        text: 'Assistant is thinking…',
        thinking: true,
      };
      dispatch({ type: 'send_start', user, thinking });

      const fail = (message: string, gone = false) => {
        dispatch({
          type: 'turn_error',
          message: { id: nextId.current++, role: 'error', text: message },
          gone,
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
            .catch((err) =>
              fail(err instanceof Error ? err.message : 'Turn failed'),
            );
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
        const gone = err instanceof ApiError && err.gone;
        fail(
          err instanceof Error ? err.message : 'Request failed',
          gone,
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

  const acknowledge = useCallback(() => dispatch({ type: 'acknowledge' }), []);

  return { state, send, newChat, acknowledge };
}
