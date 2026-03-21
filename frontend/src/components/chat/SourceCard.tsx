import { useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn, formatSourceType, sourceTypeBadgeClass } from '@/lib/utils'
import type { SourceAttribution } from '@/services/websocket'

interface SourceCardProps {
  source: SourceAttribution
  index: number
  highlighted?: boolean
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '...'
}

function isSafeUrl(url: string): boolean {
  try {
    const { protocol } = new URL(url)
    return protocol === 'https:' || protocol === 'http:'
  } catch {
    return false
  }
}

export default function SourceCard({ source, index, highlighted }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false)
  const scorePercent = Math.round(source.relevance_score * 100)

  return (
    <div
      className={cn(
        'rounded-lg border p-3 text-sm transition-colors',
        highlighted && 'border-primary bg-primary/5'
      )}
      data-testid={`source-card-${index}`}
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="font-mono text-xs text-muted-foreground">[{index + 1}]</span>
        <Badge className={cn('shrink-0', sourceTypeBadgeClass(source.source_type))}>
          {formatSourceType(source.source_type)}
        </Badge>
        <span className="text-xs text-muted-foreground">{scorePercent}%</span>
        <span className="min-w-0 flex-1 truncate font-medium">
          {truncate(source.title, 60)}
        </span>
        {expanded ? (
          <ChevronUp className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="mt-2 space-y-2 border-t pt-2">
          <p className="text-muted-foreground">{source.excerpt}</p>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>{formatTimestamp(source.created_at)}</span>
            {source.url && isSafeUrl(source.url) && (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline"
              >
                Open <ExternalLink className="size-3" />
              </a>
            )}
          </div>
          {source.participants && source.participants.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Participants: {source.participants.join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
