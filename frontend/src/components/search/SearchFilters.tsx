import { cn } from '@/lib/utils'
import type { SearchFilters } from '@/services/api'

interface SearchFiltersProps {
  filters: SearchFilters
  availableSourceTypes: string[]
  onChange: (filters: SearchFilters) => void
  className?: string
}

export default function SearchFiltersPanel({
  filters,
  availableSourceTypes,
  onChange,
  className,
}: SearchFiltersProps) {
  const selectedTypes = filters.source_types ?? []

  const toggleSourceType = (type: string) => {
    const next = selectedTypes.includes(type)
      ? selectedTypes.filter((t) => t !== type)
      : [...selectedTypes, type]
    onChange({ ...filters, source_types: next.length > 0 ? next : undefined })
  }

  const handleDateFrom = (value: string) => {
    onChange({
      ...filters,
      date_from: value ? new Date(value).toISOString() : undefined,
    })
  }

  const handleDateTo = (value: string) => {
    onChange({
      ...filters,
      date_to: value ? new Date(value).toISOString() : undefined,
    })
  }

  return (
    <div className={cn('flex flex-col gap-4 text-sm', className)}>
      <div>
        <p className="mb-2 font-medium">Source Type</p>
        <div className="flex flex-col gap-1.5">
          {availableSourceTypes.map((type) => (
            <label key={type} className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={selectedTypes.includes(type)}
                onChange={() => toggleSourceType(type)}
                className="rounded"
                aria-label={type}
              />
              <span>{type}</span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 font-medium">Date Range</p>
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">From</span>
            <input
              type="date"
              aria-label="From"
              value={
                filters.date_from
                  ? new Date(filters.date_from).toISOString().slice(0, 10)
                  : ''
              }
              className="rounded-md border bg-background px-2 py-1 text-xs"
              onChange={(e) => handleDateFrom(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">To</span>
            <input
              type="date"
              aria-label="To"
              value={
                filters.date_to
                  ? new Date(filters.date_to).toISOString().slice(0, 10)
                  : ''
              }
              className="rounded-md border bg-background px-2 py-1 text-xs"
              onChange={(e) => handleDateTo(e.target.value)}
            />
          </label>
        </div>
      </div>

      <button
        type="button"
        className="mt-auto rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent"
        onClick={() => onChange({})}
      >
        Clear all
      </button>
    </div>
  )
}
