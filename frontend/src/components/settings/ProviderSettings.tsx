import { AlertTriangle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { STATUS_CONFIG } from '@/lib/statusConfig'
import { fetchProvidersHealth, fetchActiveProviders } from '@/services/api'

export default function ProviderSettings() {
  const healthQuery = useQuery({
    queryKey: ['providers', 'health'],
    queryFn: fetchProvidersHealth,
  })
  const activeQuery = useQuery({
    queryKey: ['providers', 'active'],
    queryFn: fetchActiveProviders,
  })

  const active = activeQuery.data
  const health = healthQuery.data

  return (
    <div className="space-y-6">
      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-4 text-sm font-semibold">Active Configuration</h2>
        {activeQuery.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-4 w-48" />
          </div>
        ) : activeQuery.isError ? (
          <p className="flex items-center gap-2 text-sm text-red-500/80">
            <AlertTriangle className="size-4" />
            Failed to load provider configuration
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-sm">
              <span className="w-24 text-muted-foreground">LLM Provider</span>
              <span className="font-medium">{active?.llm.provider ?? '—'}</span>
              <span className="text-muted-foreground">{active?.llm.model}</span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <span className="w-24 text-muted-foreground">Embedding</span>
              <span className="font-medium">{active?.embedding.provider ?? '—'}</span>
              <span className="text-muted-foreground">{active?.embedding.model}</span>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-4 text-sm font-semibold">Provider Health</h2>
        {healthQuery.isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : healthQuery.isError ? (
          <p className="flex items-center gap-2 text-sm text-red-500/80">
            <AlertTriangle className="size-4" />
            Failed to load provider health
          </p>
        ) : health && Object.keys(health).length > 0 ? (
          <div className="space-y-2">
            {Object.entries(health)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([name, info]) => {
                const cfg = STATUS_CONFIG[info.status]
                return (
                  <div
                    key={name}
                    className="rounded-md border p-4"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        {cfg.icon}
                        <span className="text-sm font-medium">{name}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        {info.latency_ms != null && (
                          <span className="text-xs text-muted-foreground">{info.latency_ms.toFixed(0)}ms</span>
                        )}
                        <Badge className={cn('text-xs capitalize', cfg.badge)}>{info.status}</Badge>
                      </div>
                    </div>
                    {info.error && (
                      <p className="mt-2 text-xs text-red-500/80">{info.error}</p>
                    )}
                  </div>
                )
              })}
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No provider data available
          </p>
        )}
      </div>
    </div>
  )
}
