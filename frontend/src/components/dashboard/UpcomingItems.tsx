import { Calendar } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { UpcomingItem } from '@/services/api'

interface Props {
  items: UpcomingItem[]
  isLoading: boolean
  className?: string
}

export default function UpcomingItems({ items, isLoading, className }: Props) {
  return (
    <div className={cn('rounded-lg border bg-card p-4', className)}>
      <div className="mb-3 flex items-center gap-2">
        <Calendar className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">Upcoming</h2>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-md border p-3" data-testid="upcoming-skeleton">
              <Skeleton className="mb-2 h-4 w-3/4" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          ))}
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
          <Calendar className="size-8 opacity-40" />
          <p className="text-sm">No upcoming items — connect a calendar to see events</p>
        </div>
      )}

      {!isLoading && items.length > 0 && (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.id} className="rounded-md border p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium">{item.title}</p>
                <div className="flex shrink-0 gap-1">
                  {item.meeting_prep_available && (
                    <Badge variant="secondary" className="text-xs">
                      Prep available
                    </Badge>
                  )}
                  {item.action_items.length > 0 && (
                    <Badge variant="outline" className="text-xs">
                      {item.action_items.length} action{item.action_items.length !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </div>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {new Date(item.starts_at).toLocaleString()}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
