import { useChat } from '@/hooks/useChat'
import ChatMessageList from '@/components/chat/ChatMessageList'
import ChatInput from '@/components/chat/ChatInput'
import SessionList from '@/components/chat/SessionList'

export default function ChatPage() {
  const { sendMessage, newSession, loadSession, deleteSession, isStreaming, isConnected } =
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
        <ChatMessageList className="flex-1" />
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
