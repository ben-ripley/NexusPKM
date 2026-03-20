import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle, XCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { fetchProvidersHealth, fetchActiveProviders } from '@/services/api'
import type { ProviderHealth } from '@/services/api'

const STATUS_CONFIG: Record<ProviderHealth['status'], { icon: ReactNode; badge: string }> = {
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
        ) : health && Object.keys(health).length > 0 ? (
          <div className="space-y-2">
            {Object.entries(health).map(([name, info]) => {
              const cfg = STATUS_CONFIG[info.status]
              return (
                <div key={name} className="flex items-center justify-between rounded-md border p-3">
                  <div className="flex items-center gap-3">
                    {cfg.icon}
                    <span className="text-sm font-medium">{name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    {info.error && (
                      <span className="text-xs text-red-500" title={info.error}>
                        {info.error}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground">{info.latency_ms}ms</span>
                    <Badge className={cn('text-xs capitalize', cfg.badge)}>{info.status}</Badge>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-muted-foreground">No provider data available</p>
        )}
      </div>
    </div>
  )
}
