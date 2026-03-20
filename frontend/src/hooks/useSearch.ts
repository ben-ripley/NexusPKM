import { useState, useEffect, useCallback } from 'react'
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
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<SearchFilters>({})
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

  const search = useCallback(
    (q: string, f?: SearchFilters) => {
      if (!q.trim()) return
      searchMutation.mutate({ query: q, filters: f ?? filters, top_k: 20 })
    },
    [filters, searchMutation.mutate]
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
    availableSourceTypes: facetsQuery.data?.source_types ?? [],
    search,
  }
}
