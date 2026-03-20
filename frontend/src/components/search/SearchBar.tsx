import { useState, useRef } from 'react'
import { Search, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SearchBarProps {
  query: string
  onQueryChange: (value: string) => void
  onSearch: (value: string) => void
  suggestions: string[]
  isSearching: boolean
  className?: string
}

export default function SearchBar({
  query,
  onQueryChange,
  onSearch,
  suggestions,
  isSearching,
  className,
}: SearchBarProps) {
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const selected = activeIndex >= 0 ? suggestions[activeIndex] : query
      if (selected) {
        onSearch(selected)
        setShowSuggestions(false)
        setActiveIndex(-1)
      }
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
      setActiveIndex(-1)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, -1))
    }
  }

  const handleSuggestionClick = (suggestion: string) => {
    onSearch(suggestion)
    setShowSuggestions(false)
    setActiveIndex(-1)
  }

  const isDropdownVisible = showSuggestions && suggestions.length > 0

  return (
    <div className={cn('relative', className)}>
      <div className="relative flex items-center">
        <Search className="absolute left-3 size-4 text-muted-foreground" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          placeholder="Search your knowledge base..."
          className="w-full rounded-md border bg-background py-2 pl-9 pr-10 text-sm outline-none focus:ring-2 focus:ring-ring"
          onChange={(e) => {
            onQueryChange(e.target.value)
            setShowSuggestions(true)
            setActiveIndex(-1)
          }}
          onFocus={() => setShowSuggestions(true)}
          onKeyDown={handleKeyDown}
          aria-label="Search"
          aria-autocomplete="list"
          aria-expanded={isDropdownVisible}
          aria-controls="search-suggestions"
        />
        {isSearching && (
          <Loader2 className="absolute right-3 size-4 animate-spin text-muted-foreground" />
        )}
      </div>

      {isDropdownVisible && (
        <ul
          id="search-suggestions"
          className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md"
          role="listbox"
        >
          {suggestions.map((suggestion, i) => (
            <li
              key={suggestion}
              role="option"
              aria-selected={i === activeIndex}
              className={cn(
                'cursor-pointer px-3 py-2 text-sm',
                i === activeIndex ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
              )}
              onMouseDown={(e) => {
                e.preventDefault()
                handleSuggestionClick(suggestion)
              }}
            >
              {suggestion}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
