import { useState } from 'react';
import ChatInput from './components/ChatInput';
import Header, { type View } from './components/Header';
import LogsView from './components/LogsView';
import MessageList from './components/MessageList';
import UrgencyModal from './components/UrgencyModal';
import { useChat } from './hooks/useChat';
import { useHealth } from './hooks/useHealth';

export default function App() {
  const { state, send, newChat, acknowledge } = useChat();
  const online = useHealth();
  const [view, setView] = useState<View>('chat');

  return (
    <div className="flex h-full flex-col">
      <Header
        sessionId={state.sessionId}
        online={online}
        view={view}
        onView={setView}
        onNewChat={newChat}
      />
      {view === 'chat' ? (
        <>
          <div className="flex flex-1 overflow-hidden">
            <MessageList messages={state.messages} />
          </div>
          <ChatInput busy={state.busy} onSend={send} />
        </>
      ) : (
        <LogsView sessionId={state.sessionId} />
      )}
      <UrgencyModal message={state.urgent} onAcknowledge={acknowledge} />
    </div>
  );
}
