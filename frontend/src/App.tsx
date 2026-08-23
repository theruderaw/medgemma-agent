import { useState } from 'react';
import AddonsPanel from './components/addons/AddonsPanel';
import ChatView from './components/chat/ChatView';
import EmergencyGate from './components/chat/EmergencyGate';
import Header, { type View } from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import LogsPanel from './components/logs/LogsPanel';
import { useConversation } from './hooks/useConversation';
import { useHealth } from './hooks/useHealth';

export default function App() {
  const { state, send, newChat, acknowledge, switchSession, toggleStep } = useConversation();
  const online = useHealth();
  const [view, setView] = useState<View>('chat');
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-full">
      <Sidebar
        sessionId={state.sessionId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onOpenChat={(id) => void switchSession(id)}
        onNewChat={newChat}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          sessionId={state.sessionId}
          online={online}
          view={view}
          onView={setView}
          onMenu={() => setSidebarOpen(true)}
        />
        {view === 'chat' && (
          <ChatView
            messages={state.messages}
            busy={state.busy}
            onSend={send}
            expandedSteps={state.expandedSteps}
            onToggleStep={toggleStep}
          />
        )}
        {view === 'addons' && <AddonsPanel sessionId={state.sessionId} />}
        {view === 'logs' && <LogsPanel sessionId={state.sessionId} />}
      </div>
      <EmergencyGate message={state.urgent} onAcknowledge={acknowledge} />
    </div>
  );
}
