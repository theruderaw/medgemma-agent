# Frontend Component Reorganisation — Full Plan

## 1. Scope & Constraints

- No component file exceeds **200 LOC** (including blank lines)
- All component files re-indented from **2-space → 4-space**
- **Hooks, APIs, types, styles untouched**
- Addon toggles move from deleted `AddonsPanel` into a `SettingsDropdown` inside `StatusDisplay`
- Slash menu in Composer stays as-is (fetches addons via `fetchAddons`)
- `MessageBubble` uses a role prop (not two components)
- `Layout` owns tabs + view switching
- `Header` is hamburger-only
- `ErrorBoundary` stays

## 2. Component Tree

```
App                          Root shell — sidebar open/close only
├── Layout                   Owns view tabs + switching, renders active view
│   ├── Header               Hamburger menu (mobile only)
│   ├── StatusDisplay        Online dot + session badge + gear icon + theme toggle
│   │   └── SettingsDropdown Addon toggles in dropdown panel
│   ├── ChatView             Chat surface wrapper
│   │   ├── MessageList      Scrollable feed, auto-scroll, empty state
│   │   │   ├── MessageBubble    Single message (role prop → alignment)
│   │   │   │   ├── MessageContent   Shared markdown/streaming renderer
│   │   │   │   ├── UrgencyBadge     Urgency tag
│   │   │   │   ├── PrescriptionCard Structured prescription display
│   │   │   │   └── ClinicalNoteDialog Specialist note modal
│   │   │   └── EventTimeline   Pipeline visualization
│   │   │       └── EventStep   Single expandable pipeline node
│   │   └── Composer         Input orchestrator
│   │       ├── InputField       Autosizing textarea + keyboard
│   │       ├── SendButton       Submit
│   │       ├── AttachButton     File attach + hidden input + validation
│   │       ├── AttachmentPreview Image/PDF chip + remove
│   │       ├── TriageButton     Per-message triage toggle
│   │       └── SlashMenu        Tool picker popup (unchanged)
│   └── LogsPanel            Audit trail viewer (re-indent only)
├── Sidebar                  Mobile drawer + static rail shell
│   ├── NewButton            "New chat" button
│   └── ChatList             Searchable conversation list
│       └── ChatListItem     Individual chat entry
└── EmergencyGate            Full-screen safety acknowledgment gate

Standalone:
  ErrorBoundary              Wraps subtrees (App + ChatView)
```

## 3. Addon Data Flow

```
StatusDisplay
  └── SettingsDropdown
        ├── useAddons(sessionId) → { addons, loading, error, pending, toggle }
        └── ToggleSwitch (per addon row)

Composer (slash menu — unchanged)
  └── fetchAddons(sessionId) → AddonInfo[] → SlashMenu → slash_override
```

`useAddons` hook: kept, now consumed by `SettingsDropdown`.
`ToggleSwitch`: kept, now consumed by `SettingsDropdown`.
`fetchAddons` API: kept, still consumed by `Composer`.
`toggleAddon` API: kept, still consumed by `useAddons`.

## 4. Complete File Inventory

### Delete (1)

| File | Lines | Why |
|------|-------|-----|
| `src/components/addons/AddonsPanel.tsx` | 63 | Replaced by SettingsDropdown |

### Create (13)

| # | File | Est. LOC | Source / Purpose |
|---|------|----------|------------------|
| 1 | `src/components/chat/MessageContent.tsx` | ~20 | Extract markdown/streaming rendering from MessageBubble lines 82-89 |
| 2 | `src/components/chat/EventStep.tsx` | ~120 | Extract from EventTimeline lines 10-167: MODULE_DOT, stepLabel, kv, EventPayload, EventStep |
| 3 | `src/components/chat/InputField.tsx` | ~55 | Extract textarea from Composer lines 217-262 |
| 4 | `src/components/chat/SendButton.tsx` | ~20 | Extract send button from Composer lines 264-271 |
| 5 | `src/components/chat/AttachButton.tsx` | ~65 | Extract file input + validation from Composer lines 102-130 + 185-201 |
| 6 | `src/components/chat/AttachmentPreview.tsx` | ~30 | Extract image/PDF chip from Composer lines 158-181 |
| 7 | `src/components/chat/TriageButton.tsx` | ~25 | Extract triage toggle from Composer lines 202-215 |
| 8 | `src/components/layout/StatusDisplay.tsx` | ~40 | Online indicator + session badge + gear icon + ThemeToggle (from Header lines 58-69) |
| 9 | `src/components/layout/SettingsDropdown.tsx` | ~65 | Addon toggles dropdown using useAddons + ToggleSwitch |
| 10 | `src/components/layout/Layout.tsx` | ~55 | Tabs + view state + renders Header, StatusDisplay, ChatView/LogsPanel |
| 11 | `src/components/sidebar/NewButton.tsx` | ~25 | Extract new-chat button from Sidebar lines 100-114 |
| 12 | `src/components/sidebar/ChatList.tsx` | ~50 | Extract chat list + state + filter from Sidebar lines 30-56 + 116-188 |
| 13 | `src/components/sidebar/ChatListItem.tsx` | ~30 | Extract single chat entry from Sidebar lines 164-187 |

### Rewrite (7)

| File | Current LOC | New Est. LOC | Changes |
|------|------------|--------------|---------|
| `src/components/chat/MessageBubble.tsx` | 100 | ~65 | Add role prop for alignment. Import MessageContent. Remove inline markdown/streaming |
| `src/components/chat/EventTimeline.tsx` | 210 | ~55 | Strip to list wrapper. Import EventStep. Remove MODULE_DOT, stepLabel, kv, EventPayload, EventStep |
| `src/components/chat/Composer.tsx` | 276 | ~140 | Keep state + slash menu + submit. Import InputField, SendButton, AttachButton, AttachmentPreview, TriageButton |
| `src/components/layout/Header.tsx` | 72 | ~25 | Hamburger button only. Remove View type, tabs, session badge, online indicator, ThemeToggle |
| `src/components/layout/Sidebar.tsx` | 192 | ~50 | Shell: brand header + mobile close + NewButton + ChatList. Remove timeAgo, state, filter, chat list JSX |
| `src/components/chat/ChatView.tsx` | 42 | ~25 | Thin wrapper: ErrorBoundary(MessageList) + Composer |
| `src/App.tsx` | 50 | ~25 | Shell: Sidebar + Layout + EmergencyGate. Remove view state, Header, ChatView, LogsPanel, AddonsPanel imports |

### Re-indent only (13, no content changes)

`MessageList.tsx` (59), `SlashMenu.tsx` (70), `EmergencyGate.tsx` (69), `ClinicalNoteDialog.tsx` (26), `PrescriptionCard.tsx` (78), `UrgencyBadge.tsx` (15), `Markdown.tsx` (17), `ErrorBoundary.tsx` (53), `Badge.tsx` (36), `ToggleSwitch.tsx` (31), `Modal.tsx` (79), `ThemeToggle.tsx` (30), `StreamIndicators.tsx` (17)

## 5. Component Designs

### 5.1 SettingsDropdown (~65 LOC)

**Props:** `{ sessionId: string | null; open: boolean; onClose: () => void }`

**Behavior:**
- Returns `null` when `!open` (unmounts, so useAddons refetches on next open)
- Calls `useAddons(sessionId)` → `{ addons, loading, error, pending, toggle }`
- Absolute-positioned panel (`absolute right-0 top-full mt-2 z-50`)
- Click-outside-to-close: `useEffect` adds `mousedown` listener on `document`
- Escape-to-close: `useEffect` adds `keydown` listener on `window`

**Accessibility:**
- Panel: `role="dialog"`, `aria-label="Add-on settings"`
- Each ToggleSwitch row: existing accessible `role="switch"` + `aria-checked` from ToggleSwitch component

**Layout:**
```
┌─────────────────────────────┐
│ Add-ons                     │  ← header
├─────────────────────────────┤
│ <loading text>              │  ← if loading
│ <error alert>               │  ← if error
│ description1  [badge] [≡]   │  ← ToggleSwitch per addon
│ description2       [≡]      │
│ No add-ons available.       │  ← if empty
└─────────────────────────────┘
```

### 5.2 StatusDisplay (~40 LOC)

**Props:** `{ sessionId: string | null; online: Online }`

**Layout:** flex row, items-center, gap-3

```
[dot + label]  [session badge]  [⚙️ gear button]  [🌙/☀️ theme toggle]
```

- `useState<boolean>` for dropdown open/close
- Gear icon: SVG cog, `h-4 w-4`, toggles `open`
- Gear button: `aria-expanded={open}`, `aria-label="Add-on settings"`
- `position: relative` on wrapper for dropdown anchoring
- Renders `<SettingsDropdown sessionId={sessionId} open={open} onClose={() => setOpen(false)} />`

### 5.3 Layout (~55 LOC)

**Exports:** `type View = 'chat' | 'logs'`

**Props:** `{ sessionId, online, messages, busy, expandedSteps, onSend, onToggleStep, onMenu, onOpenChat, onNewChat }`

**Internal state:** `const [view, setView] = useState<View>('chat')`

**Render structure:**
```tsx
<div className="flex min-w-0 flex-1 flex-col">
    <Header onMenu={onMenu} />
    {/* Tab bar + status row */}
    <div className="flex items-center justify-between border-b border-neutral-200 bg-white/70 px-5 py-2 backdrop-blur dark:border-neutral-800 dark:bg-neutral-900/70">
        <nav className="flex rounded-full border border-neutral-300 p-0.5 dark:border-neutral-700" aria-label="Views">
            {TABS.map(t => <button ...>{t.label}</button>)}
        </nav>
        <StatusDisplay sessionId={sessionId} online={online} />
    </div>
    {/* Active view */}
    {view === 'chat' && <ChatView messages={messages} busy={busy} sessionId={sessionId} onSend={onSend} expandedSteps={expandedSteps} onToggleStep={onToggleStep} />}
    {view === 'logs' && <LogsPanel sessionId={sessionId} />}
</div>
```

**TABS constant:**
```ts
const TABS: { id: View; label: string }[] = [
    { id: 'chat', label: 'Chat' },
    { id: 'logs', label: 'Logs' },
];
```

### 5.4 Header (~25 LOC)

**Props:** `{ onMenu: () => void }`

**Render:** Hamburger button only (`md:hidden`). Same SVG as current.

### 5.5 Sidebar (~50 LOC)

**Props:** `{ sessionId, open, onClose, onOpenChat, onNewChat }`

**Render:**
```tsx
<>
    {open && <backdrop overlay onClick={onClose} />}
    <aside className="fixed ...">
        {/* Brand: glow dot + title + mobile close button */}
        <div>...</div>
        <p>Qwen router · MedGemma specialist · safety floor</p>
        <NewButton onClick={() => { onClose(); onNewChat(); }} />
        <ChatList sessionId={sessionId} onPick={(id) => { onClose(); onOpenChat(id); }} />
    </aside>
</>
```

No state, no callbacks, no filter. All logic moved to ChatList.

### 5.6 ChatList (~50 LOC)

**Props:** `{ sessionId: string | null; onPick: (id: string) => void }`

**Internal state:** `chats`, `refreshing`, `filter`

**Logic (from current Sidebar):**
- `useCallback` refresh → `fetchRecentChats(100)`
- `useEffect` refresh on mount + sessionId change
- `useMemo` filtered chats by query
- Renders: "All chats" header + refresh button + filter input + nav with ChatListItem entries + loading/empty/no-match states

### 5.7 ChatListItem (~30 LOC)

**Props:** `{ chat: RecentChat; active: boolean; onClick: () => void }`

**Render:** Button with preview text, session ID slice, relative time, message count. Same as current Sidebar chat entry JSX.

**Helper:** `timeAgo(ts)` function lives inside ChatList.

### 5.8 MessageBubble (~65 LOC)

**Props:** `{ message: ChatMessage }`

**Key change:** `role` prop determines alignment.
```tsx
const alignment = message.role === 'user' ? 'self-end' : 'self-start';
```

**Imports:** MessageContent, UrgencyBadge, PrescriptionCard, ClinicalNoteDialog, StreamCaret, WritingDots

**Structure:**
- ThinkingRow (inline, ~7 lines)
- Main bubble: role label, image preview, assistant-only (UrgencyBadge, PrescriptionCard, ClinicalNoteDialog button), MessageContent or streaming text, ClinicalNoteDialog modal

### 5.9 MessageContent (~20 LOC)

**Props:** `{ text: string; streaming?: boolean }`

**Render:** If streaming: `<span className="whitespace-pre-wrap">{text}<StreamCaret /></span>`. Otherwise: `<Markdown text={text} />`.

### 5.10 EventStep (~120 LOC)

**Props:** `{ ev: AuditEvent; open: boolean; onToggle: () => void; isLast: boolean }`

**Contains:** MODULE_DOT map, stepLabel function, kv helper, EventPayload component, EventStep component (all extracted from current EventTimeline lines 10-167).

### 5.11 EventTimeline (~55 LOC)

**Props:** `{ events, streaming, idPrefix, expanded, onToggle }` (unchanged)

**Render:** Maps events to `<EventStep>`, shows "pipeline running" indicator when streaming. Imports EventStep.

### 5.12 Composer (~140 LOC)

**Props:** `{ busy, sessionId, onSend }` (unchanged)

**Keeps:** All state (value, image, triage, error, limits, addons, caret, active, dismissed), refs, useEffects for config + slash menu, applyChoice, resize, submit.

**Imports and renders:** InputField, SendButton, AttachButton, AttachmentPreview, TriageButton, SlashMenu.

**JSX:**
```tsx
<footer>
    <div className="relative ...">
        {menuOpen && <SlashMenu ... />}
        {image && <AttachmentPreview image={image} busy={busy} onDetach={detach} />}
        {error && <p>...</p>}
        <div className="flex items-end gap-2">
            <AttachButton busy={busy} limits={limits} onAttach={attach} onError={setError} />
            <TriageButton busy={busy} triage={triage} onToggle={() => setTriage(t => !t)} />
            <InputField ref={ref} ...all textarea props />
            <SendButton busy={busy} disabled={!value.trim()} onClick={submit} />
        </div>
    </div>
</footer>
```

### 5.13 AttachButton (~65 LOC)

**Props:** `{ busy: boolean; limits: { maxBytes: number; mimes: string[] }; onAttach: (image: AttachedImage) => void; onError: (msg: string) => void }`

**Owns the full attach flow:**
- Hidden `<input type="file">` with `accept={limits.mimes.join(',')}`
- Click handler triggers file input
- `attach(file)` function: validates mime → `onError('Only JPEG, PNG, WebP images or PDF documents are supported.')` if invalid, validates size → `onError('File exceeds the ... limit.')` if too large, reads via FileReader → calls `onAttach({ b64, mime, previewUrl })` on success

### 5.14 AttachmentPreview (~30 LOC)

**Props:** `image: AttachedImage`, `busy: boolean`, `onDetach: () => void`

**Render:** Image/PDF chip with preview, format label, size, remove button.

### 5.15 TriageButton (~25 LOC)

**Props:** `busy`, `triage`, `onToggle`

**Render:** Toggle button with aria-pressed, same styling as current.

### 5.16 InputField (~55 LOC)

**Props:** `ref`, `busy`, `value`, `menuOpen`, `matches`, `active`, `caret`, all onChange/onSelect/onKeyDown handlers

**Render:** `<textarea>` with autosize, placeholder, aria attributes, keyboard handler delegation.

### 5.17 SendButton (~20 LOC)

**Props:** `busy`, `disabled`, `onClick`

**Render:** Button with "…" when busy, "Send" otherwise. Same styling as current.

### 5.18 App.tsx (~25 LOC)

```tsx
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
        <div className="flex h-full overflow-hidden bg-white text-neutral-900 antialiased dark:bg-neutral-950 dark:text-neutral-100">
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
```

## 6. Import Graph

```
App.tsx
  ├── Sidebar
  │   ├── NewButton
  │   └── ChatList → ChatListItem
  ├── Layout
  │   ├── Header
  │   ├── StatusDisplay
  │   │   ├── ThemeToggle
  │   │   └── SettingsDropdown
  │   │       ├── useAddons → { fetchAddons, toggleAddon }
  │   │       ├── ToggleSwitch
  │   │       └── Badge
  │   ├── ChatView
  │   │   ├── MessageList → MessageBubble
  │   │   │                    ├── MessageContent → Markdown
  │   │   │                    ├── UrgencyBadge
  │   │   │                    ├── PrescriptionCard
  │   │   │                    └── ClinicalNoteDialog → Modal, StreamIndicators
  │   │   │                 → EventTimeline → EventStep → Badge
  │   │   └── Composer
  │   │       ├── InputField
  │   │       ├── SendButton
  │   │       ├── AttachButton
  │   │       ├── AttachmentPreview
  │   │       ├── TriageButton
  │   │       └── SlashMenu
  │   └── LogsPanel → Badge
  └── EmergencyGate → Modal, Markdown
```

No circular dependencies. All imports flow downward.

## 7. Execution Phases

### Phase 1: Delete

```bash
rm src/components/addons/AddonsPanel.tsx
rmdir src/components/addons/   # if empty
```

### Phase 2: Create leaf components (13 files)

All files authored directly in 4-space. Order within this phase doesn't matter (leaves don't import each other).

**Chat leaves:**
1. `MessageContent.tsx`
2. `EventStep.tsx`
3. `InputField.tsx`
4. `SendButton.tsx`
5. `AttachButton.tsx`
6. `AttachmentPreview.tsx`
7. `TriageButton.tsx`

**Layout leaves:**
8. `SettingsDropdown.tsx`
9. `StatusDisplay.tsx`

**Sidebar leaves:**
10. `NewButton.tsx`
11. `ChatListItem.tsx`
12. `ChatList.tsx`

**Layout shell:**
13. `Layout.tsx`

### Phase 3: Rewrite parent components (7 files)

All rewrites authored directly in 4-space. Order matters for imports:

1. `MessageBubble.tsx` — import MessageContent
2. `EventTimeline.tsx` — import EventStep
3. `Composer.tsx` — import 5 children
4. `Header.tsx` — strip to hamburger, remove View export
5. `Sidebar.tsx` — import NewButton, ChatList
6. `ChatView.tsx` — thin wrapper
7. `App.tsx` — import Layout, remove all old imports

### Phase 4: Re-indent unchanged files

Re-indent only the 13 files in the "Re-indent only" list from 2-space to 4-space. The 13 created files, 7 rewritten files, and App.tsx are authored directly in 4-space — no separate re-indent pass needed for them.

### Phase 5: Verify

```bash
npx tsc --noEmit           # type check
npx vite build             # production build
wc -l src/components/**/*.tsx src/components/**/**/*.tsx  # all ≤200
```

## 8. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| SettingsDropdown unmounts on close → useAddons refetches each open | Minor network overhead | Acceptable; addons list is small and fast |
| View type moves from Header to Layout | Import path change | Single source of truth; only App.tsx imports it (now from Layout) |
| Layout has many props (passes through to children) | Large props interface | Acceptable for an orchestrator; no prop drilling beyond one level |
| Sidebar loses state management (moved to ChatList) | Architecture change | ChatList is self-contained; Sidebar becomes a pure layout shell |
