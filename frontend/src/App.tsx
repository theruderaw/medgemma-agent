import ChatInput from './components/ChatInput';
import Header from './components/Header';
import MessageList from './components/MessageList';
import UrgencyModal from './components/UrgencyModal';
import { useChat } from './hooks/useChat';
import { useHealth } from './hooks/useHealth';

export default function App() {
  const { state, send, newChat, acknowledge } = useChat();
  const online = useHealth();

  return (
    <div className="flex h-full flex-col">
      <Header sessionId={state.sessionId} online={online} onNewChat={newChat} />
      <div className="flex flex-1 overflow-hidden">
        <MessageList messages={state.messages} />
      </div>
      <ChatInput busy={state.busy} onSend={send} />
      <UrgencyModal message={state.urgent} onAcknowledge={acknowledge} />
    </div>
  );
}