import { useSearch } from '@/hooks/useSearch'
import SearchBar from '@/components/search/SearchBar'
import SearchFiltersPanel from '@/components/search/SearchFilters'
import SearchResults from '@/components/search/SearchResults'

export default function SearchPage() {
  const {
    query,
    setQuery,
    filters,
    setFilters,
    results,
    totalCount,
    isSearching,
    searchError,
    suggestions,
    availableSourceTypes,
    search,
  } = useSearch()

  return (
    <div className="flex flex-1 overflow-hidden">
      <SearchFiltersPanel
        className="w-60 shrink-0 border-r p-4"
        filters={filters}
        availableSourceTypes={availableSourceTypes}
        onChange={(f) => {
          setFilters(f)
          if (query) search(query, f)
        }}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="border-b p-4">
          <SearchBar
            query={query}
            onQueryChange={setQuery}
            onSearch={(q) => search(q)}
            suggestions={suggestions}
            isSearching={isSearching}
          />
        </div>
        <SearchResults
          className="flex-1 overflow-auto p-4"
          results={results}
          totalCount={totalCount}
          isLoading={isSearching}
          error={searchError instanceof Error ? searchError : null}
          query={query}
        />
      </div>
    </div>
  )
}
