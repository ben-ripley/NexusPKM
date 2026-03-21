import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle, Clock, RefreshCw, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { ConnectorStatus } from '@/services/api'

const STATUS_CONFIG: Record<ConnectorStatus['status'], { icon: ReactNode; badge: string }> =
  {
    healthy: {
      icon: <CheckCircle className="size-4 text-green-500" />,
      badge: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    },
    degraded: {
      icon: <AlertCircle className="size-4 text-yellow-500" />,
      badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    },
    unavailable: {
      icon: <XCircle className="size-4 text-red-500/80" />,
      badge: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    },
  }

interface Props {
  connectors: ConnectorStatus[]
  isLoading: boolean
  onSync: (name: string) => void
  isSyncing: boolean
}

export default function ConnectorStatusPanel({ connectors, isLoading, onSync, isSyncing }: Props) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <RefreshCw className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">Connectors</h2>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-md border p-3" data-testid="connector-skeleton">
              <div className="flex items-center justify-between">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-5 w-16 rounded-full" />
              </div>
              <Skeleton className="mt-2 h-3 w-32" />
            </div>
          ))}
        </div>
      )}

      {!isLoading && connectors.length === 0 && (
        <p className="py-4 text-center text-sm text-muted-foreground">No connectors configured</p>
      )}

      {!isLoading && connectors.length > 0 && (
        <div className="space-y-2">
          {connectors.map((c) => {
            const config = STATUS_CONFIG[c.status]
            return (
              <div key={c.name} className="rounded-md border p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {config.icon}
                    <span className="text-sm font-medium capitalize">{c.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={cn('text-xs capitalize', config.badge)}>{c.status}</Badge>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs"
                      disabled={isSyncing}
                      onClick={() => onSync(c.name)}
                    >
                      <RefreshCw className={cn('size-3', isSyncing && 'animate-spin')} />
                    </Button>
                  </div>
                </div>
                <div className="mt-1.5 flex items-center gap-3 text-xs text-muted-foreground">
                  <span>{c.documents_synced} docs</span>
                  {c.last_sync_at && (
                    <span className="flex items-center gap-1">
                      <Clock className="size-3" />
                      {new Date(c.last_sync_at).toLocaleString()}
                    </span>
                  )}
                  {c.last_error && (
                    <span className="truncate text-red-500/80" title={c.last_error}>
                      {c.last_error}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
