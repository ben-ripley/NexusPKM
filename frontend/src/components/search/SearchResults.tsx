import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import ResultCard from './ResultCard'
import type { SearchResult } from '@/services/api'

interface SearchResultsProps {
  results: SearchResult[]
  totalCount: number
  isLoading: boolean
  error: Error | null
  query: string
  className?: string
}

export default function SearchResults({
  results,
  totalCount,
  isLoading,
  error,
  query,
  className,
}: SearchResultsProps) {
  if (isLoading) {
    return (
      <div className={cn('space-y-3', className)}>
        {[0, 1, 2].map((i) => (
          <Skeleton
            key={i}
            data-testid="result-skeleton"
            className="h-24 w-full rounded-lg"
          />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div
        className={cn(
          'rounded-lg border border-destructive bg-destructive/10 p-4 text-sm text-destructive',
          className
        )}
      >
        {error.message}
      </div>
    )
  }

  if (!query) {
    return (
      <div className={cn('flex flex-1 items-center justify-center text-muted-foreground', className)}>
        Enter a query to search your knowledge base
      </div>
    )
  }

  if (results.length === 0) {
    return (
      <div className={cn('flex flex-1 items-center justify-center text-muted-foreground', className)}>
        No results for &ldquo;{query}&rdquo;
      </div>
    )
  }

  return (
    <div className={cn('space-y-3', className)}>
      <p className="text-sm text-muted-foreground">
        {totalCount} result{totalCount !== 1 ? 's' : ''}
      </p>
      {results.map((result, i) => (
        <ResultCard key={result.id} result={result} index={i} />
      ))}
    </div>
  )
}
