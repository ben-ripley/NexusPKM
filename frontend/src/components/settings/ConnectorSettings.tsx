import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle, Clock, RefreshCw, XCircle } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { fetchConnectorStatuses, triggerConnectorSync } from '@/services/api'
import type { ConnectorStatus } from '@/services/api'

const STATUS_CONFIG: Record<ConnectorStatus['status'], { icon: ReactNode; badge: string }> = {
  healthy: {
    icon: <CheckCircle className="size-4 text-green-500" />,
    badge: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  degraded: {
    icon: <AlertCircle className="size-4 text-yellow-500" />,
    badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  unavailable: {
    icon: <XCircle className="size-4 text-red-500" />,
    badge: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
}

export default function ConnectorSettings() {
  const queryClient = useQueryClient()
  const { data: connectors = [], isLoading } = useQuery({
    queryKey: ['connectors', 'status'],
    queryFn: fetchConnectorStatuses,
  })
  const syncMutation = useMutation({
    mutationFn: (name: string) => triggerConnectorSync(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['connectors', 'status'] }),
  })

  return (
    <div className="rounded-lg border bg-card p-6">
      <h2 className="mb-4 text-sm font-semibold">Connector Status</h2>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {!isLoading && connectors.length === 0 && (
        <p className="py-4 text-center text-sm text-muted-foreground">No connectors configured</p>
      )}

      {!isLoading && connectors.length > 0 && (
        <div className="space-y-2">
          {connectors.map((c) => {
            const cfg = STATUS_CONFIG[c.status]
            return (
              <div key={c.name} className="rounded-md border p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {cfg.icon}
                    <span className="text-sm font-medium capitalize">{c.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={cn('text-xs capitalize', cfg.badge)}>{c.status}</Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 gap-1 px-2 text-xs"
                      disabled={syncMutation.isPending}
                      onClick={() => syncMutation.mutate(c.name)}
                      aria-label={`Sync ${c.name}`}
                    >
                      <RefreshCw className={cn('size-3', syncMutation.isPending && 'animate-spin')} />
                      Sync
                    </Button>
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-4 text-xs text-muted-foreground">
                  <span>{c.documents_synced} docs synced</span>
                  {c.last_sync_at && (
                    <span className="flex items-center gap-1">
                      <Clock className="size-3" />
                      {new Date(c.last_sync_at).toLocaleString()}
                    </span>
                  )}
                  {c.last_error && (
                    <span className="truncate text-red-500" title={c.last_error}>
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
