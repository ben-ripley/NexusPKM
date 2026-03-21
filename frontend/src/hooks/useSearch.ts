import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  searchDocuments,
  fetchSuggestions,
  fetchSearchFacets,
} from '@/services/api'
import type { SearchFilters, SearchRequest, SearchResponse } from '@/services/api'

function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

export function useSearch() {
  const [searchParams] = useSearchParams()
  const urlQuery = searchParams.get('q') ?? ''
  const [query, setQuery] = useState(urlQuery)
  const [filters, setFilters] = useState<SearchFilters>({})
  const [filtersInitialized, setFiltersInitialized] = useState(false)
  const debouncedQuery = useDebounce(query, 300)

  const searchMutation = useMutation<SearchResponse, Error, SearchRequest>({
    mutationFn: searchDocuments,
  })

  const suggestQuery = useQuery({
    queryKey: ['search-suggest', debouncedQuery],
    queryFn: () => fetchSuggestions(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
    staleTime: 30_000,
  })

  const facetsQuery = useQuery({
    queryKey: ['search-facets'],
    queryFn: fetchSearchFacets,
    staleTime: Infinity,
  })

  const availableSourceTypes = facetsQuery.data?.source_types ?? []

  // Once the available source types load, initialize all checkboxes to checked.
  // If a query was passed via URL (?q=), fire the search immediately.
  // The guard ensures we only do this once — subsequent filter changes by the
  // user are not overwritten.
  useEffect(() => {
    if (!filtersInitialized && availableSourceTypes.length > 0) {
      const initialFilters: SearchFilters = { source_types: availableSourceTypes }
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFilters(initialFilters)
      setFiltersInitialized(true)
      if (urlQuery) {
        searchMutation.mutate({ query: urlQuery, filters: initialFilters, top_k: 20 })
      }
    }
  }, [availableSourceTypes, filtersInitialized]) // eslint-disable-line react-hooks/exhaustive-deps

  const search = useCallback(
    (q: string, f?: SearchFilters) => {
      if (!q.trim()) return
      searchMutation.mutate({ query: q, filters: f ?? filters, top_k: 20 })
    },
    [filters, searchMutation]
  )

  return {
    query,
    setQuery,
    filters,
    setFilters,
    results: searchMutation.data?.results ?? [],
    facets: searchMutation.data?.facets ?? null,
    totalCount: searchMutation.data?.total_count ?? 0,
    isSearching: searchMutation.isPending,
    searchError: searchMutation.error,
    suggestions: suggestQuery.data ?? [],
    availableSourceTypes,
    search,
  }
}
