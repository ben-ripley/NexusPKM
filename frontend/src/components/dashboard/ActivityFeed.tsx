import type { ReactNode } from 'react'
import { Activity, FileText, GitBranch, RefreshCw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { ActivityItem } from '@/services/api'

const ACTIVITY_ICONS: Record<ActivityItem['type'], ReactNode> = {
  document_ingested: <FileText className="size-4 text-blue-500" />,
  entity_discovered: <GitBranch className="size-4 text-purple-500" />,
  relationship_created: <GitBranch className="size-4 text-green-500" />,
  sync_completed: <RefreshCw className="size-4 text-orange-500" />,
}

interface Props {
  items: ActivityItem[]
  isLoading: boolean
  className?: string
}

export default function ActivityFeed({ items, isLoading, className }: Props) {
  return (
    <div className={cn('rounded-lg border bg-card p-4', className)}>
      <div className="mb-3 flex items-center gap-2">
        <Activity className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">Recent Activity</h2>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-start gap-3" data-testid="activity-skeleton">
              <Skeleton className="size-4 shrink-0 rounded-full" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
          <Activity className="size-8 opacity-40" />
          <p className="text-sm">No recent activity</p>
        </div>
      )}

      {!isLoading && items.length > 0 && (
        <div className="space-y-3">
          {items.slice(0, 20).map((item) => (
            <div key={item.id} className="flex items-start gap-3">
              <div className="mt-0.5 shrink-0">{ACTIVITY_ICONS[item.type]}</div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{item.title}</p>
                <p className="truncate text-xs text-muted-foreground">{item.description}</p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {item.source_type && (
                  <Badge variant="secondary" className="text-xs">
                    {item.source_type}
                  </Badge>
                )}
                <span className="text-xs text-muted-foreground">
                  {new Date(item.timestamp).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
