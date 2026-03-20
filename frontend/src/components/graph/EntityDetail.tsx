import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { fetchEntityDetail } from '@/services/api'
import { Skeleton } from '@/components/ui/skeleton'

interface Props {
  entityId: string
  onClose: () => void
}

export default function EntityDetail({ entityId, onClose }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['entity-detail', entityId],
    queryFn: () => fetchEntityDetail(entityId),
    staleTime: 60_000,
  })

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Entity Detail</h2>
        <button
          aria-label="Close"
          onClick={onClose}
          className="rounded p-1 hover:bg-accent"
        >
          <X className="size-4" />
        </button>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-3">
          <Skeleton data-testid="entity-detail-skeleton-name" className="h-6 w-3/4" />
          <Skeleton data-testid="entity-detail-skeleton-type" className="h-4 w-1/2" />
          <Skeleton data-testid="entity-detail-skeleton-prop1" className="h-4 w-full" />
          <Skeleton data-testid="entity-detail-skeleton-prop2" className="h-4 w-full" />
        </div>
      ) : isError ? (
        <p className="text-sm text-destructive">Failed to load entity.</p>
      ) : data ? (
        <>
          <div>
            <h3 className="text-lg font-semibold">{data.name}</h3>
            <span className="mt-1 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              {data.entity_type}
            </span>
          </div>

          {Object.keys(data.properties).length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Properties</div>
              <div className="flex flex-col gap-1">
                {Object.entries(data.properties).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-sm">
                    <span className="font-medium">{k}:</span>
                    <span className="text-muted-foreground">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data.relationships.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                Relationships
              </div>
              <div className="flex flex-col gap-1">
                {data.relationships.map((r) => (
                  <div key={r.id} className="rounded border px-2 py-1 text-sm">
                    <span className="font-medium">{r.relationship_type}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      → {r.target_entity_id === entityId ? r.source_entity_id : r.target_entity_id}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  )
}
