import { useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn, formatSourceType, sourceTypeBadgeClass } from '@/lib/utils'
import type { SearchResult } from '@/services/api'

interface ResultCardProps {
  result: SearchResult
  index: number
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

const SAFE_PROTOCOLS = new Set(['https:', 'http:', 'obsidian:'])

function isSafeUrl(url: string): boolean {
  try {
    const { protocol } = new URL(url)
    return SAFE_PROTOCOLS.has(protocol)
  } catch {
    return false
  }
}

export default function ResultCard({ result, index }: ResultCardProps) {
  const [expanded, setExpanded] = useState(false)
  const scorePercent = Math.round(result.relevance_score * 100)
  const safeUrl = result.url && isSafeUrl(result.url) ? result.url : null

  const handleCardClick = () => {
    if (safeUrl) window.open(safeUrl, '_blank', 'noopener,noreferrer')
  }

  return (
    <div
      className={cn(
        'rounded-lg border p-4 text-sm transition-colors hover:border-muted-foreground/30',
        safeUrl && 'cursor-pointer hover:bg-muted/30',
      )}
      data-testid={`result-card-${index}`}
      onClick={safeUrl ? handleCardClick : undefined}
      role={safeUrl ? 'button' : undefined}
      tabIndex={safeUrl ? 0 : undefined}
      onKeyDown={safeUrl ? (e) => { if (e.key === 'Enter' || e.key === ' ') handleCardClick() } : undefined}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <Badge className={cn('shrink-0', sourceTypeBadgeClass(result.source_type))}>
              {formatSourceType(result.source_type)}
            </Badge>
            <span className="text-xs text-muted-foreground">{scorePercent}%</span>
          </div>
          <h3 className="font-semibold leading-tight">{result.title}</h3>
          <p className="mt-1 line-clamp-2 text-muted-foreground">{result.excerpt}</p>
          <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
            <span>{formatTimestamp(result.created_at)}</span>
            {safeUrl && (
              <a
                href={safeUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                Open <ExternalLink className="size-3" />
              </a>
            )}
          </div>
        </div>

        {result.matched_entities.length > 0 && (
          <button
            type="button"
            aria-label={expanded ? 'Collapse entities' : 'Expand entities'}
            className="shrink-0 text-muted-foreground"
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
          >
            {expanded ? (
              <ChevronUp className="size-4" />
            ) : (
              <ChevronDown className="size-4" />
            )}
          </button>
        )}
      </div>

      {expanded && result.matched_entities.length > 0 && (
        <div className="mt-3 border-t pt-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Entities</p>
          <div className="flex flex-wrap gap-1">
            {result.matched_entities.map((e, i) => (
              <Badge key={`${e.name}-${e.entity_type}-${i}`} variant="outline" className="text-xs">
                {e.name} ({e.entity_type})
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
