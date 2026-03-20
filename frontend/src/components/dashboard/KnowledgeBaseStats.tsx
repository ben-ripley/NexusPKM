import { BookOpen, GitBranch, Layers, Network } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { DashboardStats } from '@/services/api'

interface StatTileProps {
  label: string
  value: number
  icon: React.ReactNode
}

function StatTile({ label, value, icon }: StatTileProps) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <div className="mb-1 flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <p className="text-2xl font-bold">{value.toLocaleString()}</p>
    </div>
  )
}

interface Props {
  stats: DashboardStats | null
  isLoading: boolean
  className?: string
}

export default function KnowledgeBaseStats({ stats, isLoading, className }: Props) {
  const sourceEntries = stats ? Object.entries(stats.by_source_type) : []
  const totalDocs = stats?.total_documents ?? 0

  return (
    <div className={cn('rounded-lg border bg-card p-4', className)}>
      <div className="mb-3 flex items-center gap-2">
        <BookOpen className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">Knowledge Base</h2>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-md border p-3" data-testid="stats-skeleton">
              <Skeleton className="mb-2 h-3 w-20" />
              <Skeleton className="h-7 w-12" />
            </div>
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile
              label="Documents"
              value={stats?.total_documents ?? 0}
              icon={<BookOpen className="size-3.5" />}
            />
            <StatTile
              label="Entities"
              value={stats?.total_entities ?? 0}
              icon={<Network className="size-3.5" />}
            />
            <StatTile
              label="Relationships"
              value={stats?.total_relationships ?? 0}
              icon={<GitBranch className="size-3.5" />}
            />
            <StatTile
              label="Chunks"
              value={stats?.total_chunks ?? 0}
              icon={<Layers className="size-3.5" />}
            />
          </div>

          {sourceEntries.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs text-muted-foreground">By source</p>
              <div className="space-y-1.5">
                {sourceEntries.map(([source, count]) => {
                  const pct = totalDocs > 0 ? Math.round((count / totalDocs) * 100) : 0
                  return (
                    <div key={source}>
                      <div className="mb-0.5 flex justify-between text-xs">
                        <span className="text-muted-foreground">{source}</span>
                        <span>{count}</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
