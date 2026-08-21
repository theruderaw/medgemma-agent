import { useCallback, useEffect, useReducer, useRef } from 'react';
import { QueuedResponse, resetSession, streamChat, waitForJob } from '../lib/api';
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
  const thinkingId = useRef<number | null>(null);

  useEffect(() => {
    if (state.sessionId) localStorage.setItem(SESSION_KEY, state.sessionId);
    else localStorage.removeItem(SESSION_KEY);
  }, [state.sessionId]);

  const send = useCallback(
    async (text: string, image?: AttachedImage) => {
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
      thinkingId.current = thinking.id;
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
        await streamChat(
          trimmed,
          state.sessionId,
          {
            onToken: (delta) => dispatch({ type: 'stream_token', messageId: thinking.id, delta }),
            onSpecialistToken: (delta) =>
              dispatch({ type: 'specialist_token', messageId: thinking.id, delta }),
            onPipeline: (event) => dispatch({ type: 'pipeline_event', messageId: thinking.id, event }),
            onDone: (data) => dispatch({ type: 'turn_success', data, thinkingId: thinking.id }),
            onError: (message, status) => fail(message, status === 410),
          },
          image,
        );
      } catch (err) {
        if (err instanceof QueuedResponse) {
          try {
            const data = await waitForJob(err.data.job_id);
            dispatch({ type: 'turn_success', data, thinkingId: thinking.id });
          } catch (jobErr) {
            fail(jobErr instanceof Error ? jobErr.message : 'Turn failed');
          }
        } else {
          fail(err instanceof Error ? err.message : 'Request failed');
        }
      }
    },
    [state.busy, state.sessionId],
  );

  const newChat = useCallback(async () => {
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