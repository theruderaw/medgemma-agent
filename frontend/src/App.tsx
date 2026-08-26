import { useState } from 'react';
import EmergencyGate from './components/chat/EmergencyGate';
import Layout from './components/layout/Layout';
import Sidebar from './components/layout/Sidebar';
import { useConversation } from './hooks/useConversation';
import { useHealth } from './hooks/useHealth';

export default function App() {
    const { state, send, newChat, acknowledge, switchSession, toggleStep } = useConversation();
    const online = useHealth();
    const [sidebarOpen, setSidebarOpen] = useState(false);

    return (
        <div className="flex h-full overflow-hidden bg-white text-neutral-800 antialiased dark:bg-neutral-950 dark:text-neutral-200">
            <Sidebar
                sessionId={state.sessionId}
                open={sidebarOpen}
                onClose={() => setSidebarOpen(false)}
                onOpenChat={(id) => void switchSession(id)}
                onNewChat={newChat}
            />
            <Layout
                sessionId={state.sessionId}
                online={online}
                messages={state.messages}
                busy={state.busy}
                expandedSteps={state.expandedSteps}
                onSend={send}
                onToggleStep={toggleStep}
                onMenu={() => setSidebarOpen(true)}
                onOpenChat={(id) => void switchSession(id)}
                onNewChat={newChat}
            />
            <EmergencyGate message={state.urgent} onAcknowledge={acknowledge} />
        </div>
    );
}
