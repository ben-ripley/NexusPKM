import { Trash2, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { useChatStore } from '@/stores/chat'
import type { SessionMeta } from '@/stores/chat'

interface SessionListProps {
  onNewSession?: () => void
  onLoadSession?: (id: string) => void
  onDeleteSession?: (id: string) => void
  className?: string
}

function relativeTime(iso: string): string {
  const now = Date.now()
  const then = new Date(iso).getTime()
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60000)

  if (diffMin < 1) return 'Just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay === 1) return 'Yesterday'
  if (diffDay < 30) return `${diffDay}d ago`
  return new Date(iso).toLocaleDateString()
}

export default function SessionList({
  onNewSession,
  onLoadSession,
  onDeleteSession,
  className,
}: SessionListProps) {
  const sessions = useChatStore((s) => s.sessions)
  const currentSessionId = useChatStore((s) => s.currentSessionId)

  return (
    <div className={cn('flex flex-col', className)}>
      <div className="p-3">
        <Button
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={onNewSession}
        >
          <Plus className="size-4" />
          New Chat
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="space-y-1 px-3 pb-3">
          {sessions.map((session: SessionMeta) => {
            const isActive = session.id === currentSessionId
            return (
              <div
                key={session.id}
                data-active={isActive || undefined}
                className={cn(
                  'group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-muted',
                  isActive && 'bg-muted font-medium'
                )}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => onLoadSession?.(session.id)}
                >
                  <p className="truncate">{session.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {relativeTime(session.updated_at)}
                  </p>
                </button>
                <button
                  type="button"
                  className="shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDeleteSession?.(session.id)
                  }}
                  aria-label={`Delete session ${session.title}`}
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            )
          })}
        </div>
      </ScrollArea>
    </div>
  )
}
