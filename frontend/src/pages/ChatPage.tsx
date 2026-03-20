import { useChat } from '@/hooks/useChat'
import ChatMessageList from '@/components/chat/ChatMessageList'
import ChatInput from '@/components/chat/ChatInput'
import SessionList from '@/components/chat/SessionList'

export default function ChatPage() {
  const { sendMessage, newSession, loadSession, deleteSession, isStreaming, isConnected, isLoadingSessions, sessionsError } =
    useChat()

  return (
    <div className="flex flex-1 overflow-hidden">
      <SessionList
        className="w-60 shrink-0 border-r"
        onNewSession={() => newSession('')}
        onLoadSession={loadSession}
        onDeleteSession={deleteSession}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        {sessionsError && (
          <div className="border-b bg-destructive/10 px-4 py-2 text-sm text-destructive">
            Failed to load sessions. Check your connection.
          </div>
        )}
        {isLoadingSessions && (
          <div className="border-b px-4 py-2 text-sm text-muted-foreground">
            Loading sessions…
          </div>
        )}
        <ChatMessageList className="flex-1" onSuggestionClick={sendMessage} />
        <ChatInput
          className="border-t p-4"
          onSend={sendMessage}
          isStreaming={isStreaming}
          isConnected={isConnected}
        />
      </div>
    </div>
  )
}
