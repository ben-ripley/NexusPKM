import { useEffect, useRef } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import ChatMessage from './ChatMessage'
import { useChatStore } from '@/stores/chat'
import { cn } from '@/lib/utils'

interface ChatMessageListProps {
  className?: string
}

export default function ChatMessageList({ className }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  const currentSessionId = useChatStore((s) => s.currentSessionId)
  const messagesBySession = useChatStore((s) => s.messagesBySession)
  const streamingContent = useChatStore((s) => s.streamingContent)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const suggestions = useChatStore((s) => s.suggestions)

  const messages = currentSessionId
    ? (messagesBySession[currentSessionId] ?? [])
    : []

  useEffect(() => {
    if (bottomRef.current && typeof bottomRef.current.scrollIntoView === 'function') {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length, streamingContent])

  return (
    <ScrollArea className={cn('px-4', className)}>
      <div className="mx-auto max-w-3xl space-y-4 py-4">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {isStreaming && streamingContent && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-2xl rounded-tl-sm bg-muted px-4 py-2">
              <p className="whitespace-pre-wrap">{streamingContent}</p>
            </div>
          </div>
        )}

        {isStreaming && !streamingContent && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-tl-sm bg-muted px-4 py-2">
              <span className="inline-flex gap-1">
                <span className="size-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:0ms]" />
                <span className="size-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:150ms]" />
                <span className="size-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:300ms]" />
              </span>
            </div>
          </div>
        )}

        {!isStreaming && suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className="rounded-full border bg-background px-3 py-1 text-sm transition-colors hover:bg-muted"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
