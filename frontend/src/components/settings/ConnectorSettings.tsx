import { useState } from 'react'
import { AlertTriangle, Clock, Loader2, RefreshCw } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { STATUS_CONFIG } from '@/lib/statusConfig'
import { fetchConnectorStatuses, triggerConnectorSync } from '@/services/api'

export default function ConnectorSettings() {
  const queryClient = useQueryClient()
  // Track when each connector sync was triggered (name → timestamp)
  const [syncingAt, setSyncingAt] = useState<Record<string, number>>({})

  const { data: connectors = [], isLoading, isError } = useQuery({
    queryKey: ['connectors', 'status'],
    queryFn: fetchConnectorStatuses,
    // Poll every 3 s while any connector is in the syncing window
    refetchInterval: Object.keys(syncingAt).length > 0 ? 3_000 : false,
  })

  // Clear syncing state for connectors whose last_sync_at is now after trigger time
  const activeSyncingAt = { ...syncingAt }
  for (const c of connectors) {
    const triggeredAt = syncingAt[c.name]
    if (triggeredAt && c.last_sync_at && new Date(c.last_sync_at).getTime() >= triggeredAt) {
      delete activeSyncingAt[c.name]
    }
  }

  const syncMutation = useMutation({
    mutationFn: (name: string) => triggerConnectorSync(name),
    onSuccess: (_data, name) => {
      setSyncingAt((prev) => ({ ...prev, [name]: Date.now() }))
      queryClient.invalidateQueries({ queryKey: ['connectors', 'status'] })
    },
  })

  const isSyncing = (name: string) =>
    syncMutation.isPending && syncMutation.variables === name || name in activeSyncingAt

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

      {isError && (
        <p className="flex items-center gap-2 text-sm text-red-500/80">
          <AlertTriangle className="size-4" />
          Failed to load connector status
        </p>
      )}

      {!isLoading && !isError && connectors.length === 0 && (
        <p className="py-4 text-center text-sm text-muted-foreground">No connectors configured</p>
      )}

      {!isLoading && !isError && connectors.length > 0 && (
        <div className="space-y-2">
          {connectors.map((c) => {
            const cfg = STATUS_CONFIG[c.status]
            return (
              <div key={c.name} className="rounded-md border p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {isSyncing(c.name) ? (
                      <Loader2 className="size-4 animate-spin text-muted-foreground" />
                    ) : cfg.icon}
                    <span className="text-sm font-medium capitalize">{c.name}</span>
                    {isSyncing(c.name) && (
                      <span className="text-xs text-muted-foreground">Syncing…</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={cn('text-xs capitalize', cfg.badge)}>{c.status}</Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 gap-1 px-2 text-xs"
                      disabled={isSyncing(c.name)}
                      onClick={() => syncMutation.mutate(c.name)}
                      aria-label={`Sync ${c.name}`}
                    >
                      <RefreshCw className={cn('size-3', isSyncing(c.name) && 'animate-spin')} />
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
                    <span className="truncate text-red-500/80" title={c.last_error}>
                      {c.last_error}
                    </span>
                  )}
                </div>
                {c.sync_errors && c.sync_errors.length > 0 && (
                  <div className="mt-2 rounded-md border border-red-200 bg-red-50 p-2 dark:border-red-900/40 dark:bg-red-950/20">
                    <p className="mb-1 text-xs font-medium text-red-600 dark:text-red-400">
                      {c.sync_errors.length} file{c.sync_errors.length === 1 ? '' : 's'} failed to sync
                    </p>
                    <ul className="space-y-0.5">
                      {c.sync_errors.map((err, i) => (
                        <li key={i} className="truncate font-mono text-xs text-red-500/80 dark:text-red-400/70" title={err}>
                          {err}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
