import { useEffect, useRef } from 'react'
import { X, CheckCheck, Bell, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useNotificationsStore } from '@/stores/notifications'
import { useDismiss, useResolveContradiction } from '@/hooks/useNotifications'
import type { Notification } from '@/services/api'
import { formatDistanceToNow } from 'date-fns'
import { cn, formatSourceType, sourceTypeBadgeClass } from '@/lib/utils'

const SAFE_PROTOCOLS = new Set(['https:', 'http:', 'obsidian:'])

function isSafeUrl(url: string): boolean {
  try {
    const { protocol } = new URL(url)
    return SAFE_PROTOCOLS.has(protocol)
  } catch {
    return false
  }
}

interface Props {
  onClose: () => void
}

const PRIORITY_VARIANT: Record<string, 'default' | 'secondary' | 'destructive'> = {
  high: 'destructive',
  medium: 'default',
  low: 'secondary',
}

const TYPE_LABEL: Record<string, string> = {
  meeting_prep: 'Meeting',
  related_content: 'Related',
  contradiction: 'Conflict',
  insight: 'Insight',
}

function NotificationItem({ n }: { n: Notification }) {
  const { mutate: dismiss } = useDismiss()
  const { mutate: resolve, isPending: resolving } = useResolveContradiction()

  const sourceType = n.data.source_type as string | undefined
  const sourceUrl = n.data.source_url as string | undefined
  const contradictionId = n.data.contradiction_id as string | undefined

  return (
    <div
      className="flex flex-col gap-1 border-b p-3 last:border-0"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1">
          <Badge variant={PRIORITY_VARIANT[n.priority] ?? 'secondary'} className="text-[10px]">
            {TYPE_LABEL[n.type] ?? n.type}
          </Badge>
          <span className="text-xs font-medium leading-tight">{n.title}</span>
        </div>
        <span className="shrink-0 text-[10px] text-muted-foreground">
          {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{n.summary}</p>
      {sourceType && (
        <div className="flex items-center gap-2 mt-1">
          <Badge className={cn('text-[10px]', sourceTypeBadgeClass(sourceType))}>
            {formatSourceType(sourceType)}
          </Badge>
          {sourceUrl && isSafeUrl(sourceUrl) && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              Open <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      )}
      <div className="flex gap-1">
        {n.type === 'contradiction' && contradictionId && (
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-xs text-green-600 hover:text-green-700"
            aria-label="Resolve contradiction"
            disabled={resolving}
            onClick={() => resolve(contradictionId)}
          >
            <CheckCheck className="mr-1 size-3" /> Resolve
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-2 text-xs"
          aria-label="Dismiss"
          onClick={() => dismiss(n.id)}
        >
          <X className="mr-1 size-3" /> Dismiss
        </Button>
      </div>
    </div>
  )
}

export default function NotificationPanel({ onClose }: Props) {
  const notifications = useNotificationsStore((s) => s.notifications)
  const panelRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [onClose])

  return (
    <div
      ref={panelRef}
      className="absolute right-0 top-full z-50 mt-1 w-80 rounded-lg border bg-popover shadow-lg"
    >
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-sm font-semibold">Notifications</span>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close">
          <X className="size-3" />
        </Button>
      </div>
      {notifications.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
          <Bell className="size-6 opacity-40" />
          <p className="text-sm">No notifications</p>
        </div>
      ) : (
        <div className="max-h-96 overflow-y-auto">
          {notifications.slice(0, 20).map((n) => (
            <NotificationItem key={n.id} n={n} />
          ))}
        </div>
      )}
    </div>
  )
}
