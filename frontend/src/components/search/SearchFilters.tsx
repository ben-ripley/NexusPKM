import { CalendarIcon } from 'lucide-react'
import { cn, formatSourceType, sourceTypeColor } from '@/lib/utils'
import { Calendar } from '@/components/ui/calendar'
import { PopoverContent, PopoverRoot, PopoverTrigger } from '@/components/ui/popover'
import type { SearchFilters } from '@/services/api'

function formatDate(iso: string | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function DatePickerButton({
  label,
  value,
  onSelect,
  disabledBefore,
  disabledAfter,
}: {
  label: string
  value: Date | undefined
  onSelect: (date: Date | undefined) => void
  disabledBefore?: Date
  disabledAfter?: Date
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <PopoverRoot>
        <PopoverTrigger
          className={cn(
            'flex w-full items-center gap-2 rounded-md border bg-background px-3 py-1.5',
            'text-xs text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            !value && 'text-muted-foreground',
          )}
          aria-label={label}
        >
          <CalendarIcon className="size-3.5 shrink-0 text-muted-foreground" />
          <span>{value ? formatDate(value.toISOString()) : 'Pick a date'}</span>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="single"
            selected={value}
            onSelect={onSelect}
            defaultMonth={value}
            disabled={[
              ...(disabledBefore ? [{ before: disabledBefore }] : []),
              ...(disabledAfter ? [{ after: disabledAfter }] : []),
            ]}
          />
        </PopoverContent>
      </PopoverRoot>
    </div>
  )
}

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

  const dateFrom = filters.date_from ? new Date(filters.date_from) : undefined
  const dateTo = filters.date_to ? new Date(filters.date_to) : undefined

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
                aria-label={formatSourceType(type)}
              />
              <span
                className="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                style={{
                  backgroundColor: `${sourceTypeColor(type)}26`,
                  color: sourceTypeColor(type),
                  border: `1px solid ${sourceTypeColor(type)}66`,
                }}
              >
                {formatSourceType(type)}
              </span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 font-medium">Date Range</p>
        <div className="flex flex-col gap-2">
          <DatePickerButton
            label="From"
            value={dateFrom}
            onSelect={(d) => onChange({ ...filters, date_from: d?.toISOString() })}
            disabledAfter={dateTo}
          />
          <DatePickerButton
            label="To"
            value={dateTo}
            onSelect={(d) => onChange({ ...filters, date_to: d?.toISOString() })}
            disabledBefore={dateFrom}
          />
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
