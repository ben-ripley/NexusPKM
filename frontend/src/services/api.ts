/**
 * Typed fetch client for the NexusPKM REST API.
 * Covers the search endpoints (F-007).
 */
import { z } from 'zod'

const API = import.meta.env.VITE_API_URL ?? ''

// ---------------------------------------------------------------------------
// Zod schemas
// ---------------------------------------------------------------------------

const EntitySummarySchema = z.object({
  name: z.string(),
  entity_type: z.string(),
})

const SearchResultSchema = z.object({
  id: z.string(),
  title: z.string(),
  excerpt: z.string(),
  source_type: z.string(),
  source_id: z.string(),
  relevance_score: z.number(),
  created_at: z.string(),
  url: z.string().nullable().optional(),
  matched_entities: z.array(EntitySummarySchema).default([]),
  related_documents: z.array(z.string()).default([]),
})

const DateBucketSchema = z.object({
  date: z.string(),
  count: z.number(),
})

const EntityCountSchema = z.object({
  name: z.string(),
  entity_type: z.string(),
  count: z.number(),
})

const TagCountSchema = z.object({
  tag: z.string(),
  count: z.number(),
})

const SearchFacetsSchema = z.object({
  source_types: z.record(z.string(), z.number()),
  date_histogram: z.array(DateBucketSchema),
  top_entities: z.array(EntityCountSchema),
  top_tags: z.array(TagCountSchema),
})

const SearchResponseSchema = z.object({
  results: z.array(SearchResultSchema),
  total_count: z.number(),
  facets: SearchFacetsSchema,
  query_entities: z.array(z.string()).default([]),
})

const SuggestResponseSchema = z.array(z.string())

const FacetsResponseSchema = z.object({
  source_types: z.array(z.string()),
})

// ---------------------------------------------------------------------------
// Exported types
// ---------------------------------------------------------------------------

export type EntitySummary = z.infer<typeof EntitySummarySchema>
export type SearchResult = z.infer<typeof SearchResultSchema>
export type SearchFacets = z.infer<typeof SearchFacetsSchema>
export type SearchResponse = z.infer<typeof SearchResponseSchema>

export interface SearchFilters {
  source_types?: string[]
  date_from?: string
  date_to?: string
  entities?: string[]
  tags?: string[]
}

export interface SearchRequest {
  query: string
  filters?: SearchFilters
  top_k?: number
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function searchDocuments(request: SearchRequest): Promise<SearchResponse> {
  const res = await fetch(`${API}/api/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) throw new Error(`Search failed: ${res.status}`)
  return SearchResponseSchema.parse(await res.json())
}

export async function fetchSuggestions(q: string): Promise<string[]> {
  const params = new URLSearchParams({ q })
  const res = await fetch(`${API}/api/search/suggest?${params}`)
  if (!res.ok) return []
  return SuggestResponseSchema.parse(await res.json())
}

export async function fetchSearchFacets(): Promise<{ source_types: string[] }> {
  const res = await fetch(`${API}/api/search/facets`)
  if (!res.ok) throw new Error('Failed to fetch facets')
  return FacetsResponseSchema.parse(await res.json())
}
