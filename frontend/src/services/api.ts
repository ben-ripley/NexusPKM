/**
 * Typed fetch client for the NexusPKM REST API.
 * Covers search (F-007) and dashboard (F-008) endpoints.
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

// ---------------------------------------------------------------------------
// Dashboard schemas (F-008)
// ---------------------------------------------------------------------------

const ActivityItemSchema = z.object({
  id: z.string(),
  type: z.enum([
    'document_ingested',
    'entity_discovered',
    'relationship_created',
    'sync_completed',
  ]),
  title: z.string(),
  description: z.string(),
  source_type: z.string().nullable().optional(),
  timestamp: z.string(),
})

const DashboardActivitySchema = z.object({
  items: z.array(ActivityItemSchema),
})

const DashboardStatsSchema = z.object({
  total_documents: z.number(),
  total_chunks: z.number(),
  total_entities: z.number(),
  total_relationships: z.number(),
  by_source_type: z.record(z.string(), z.number()),
})

const UpcomingItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  starts_at: z.string(),
  meeting_prep_available: z.boolean(),
  action_items: z.array(z.string()),
})

const DashboardUpcomingSchema = z.object({
  items: z.array(UpcomingItemSchema),
})

const ConnectorStatusSchema = z.object({
  name: z.string(),
  status: z.enum(['healthy', 'degraded', 'unavailable']),
  last_sync_at: z.string().nullable().optional(),
  last_error: z.string().nullable().optional(),
  documents_synced: z.number(),
})

// ---------------------------------------------------------------------------
// Dashboard exported types
// ---------------------------------------------------------------------------

export type ActivityItem = z.infer<typeof ActivityItemSchema>
export type DashboardActivity = z.infer<typeof DashboardActivitySchema>
export type DashboardStats = z.infer<typeof DashboardStatsSchema>
export type UpcomingItem = z.infer<typeof UpcomingItemSchema>
export type DashboardUpcoming = z.infer<typeof DashboardUpcomingSchema>
export type ConnectorStatus = z.infer<typeof ConnectorStatusSchema>

// ---------------------------------------------------------------------------
// Dashboard API functions
// ---------------------------------------------------------------------------

export async function fetchDashboardActivity(): Promise<DashboardActivity> {
  const res = await fetch(`${API}/api/dashboard/activity`)
  if (!res.ok) throw new Error(`Failed to fetch activity: ${res.status}`)
  return DashboardActivitySchema.parse(await res.json())
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const res = await fetch(`${API}/api/dashboard/stats`)
  if (!res.ok) throw new Error(`Failed to fetch dashboard stats: ${res.status}`)
  return DashboardStatsSchema.parse(await res.json())
}

export async function fetchConnectorStatuses(): Promise<ConnectorStatus[]> {
  const res = await fetch(`${API}/api/connectors/status`)
  if (!res.ok) throw new Error(`Failed to fetch connector statuses: ${res.status}`)
  return z.array(ConnectorStatusSchema).parse(await res.json())
}

export async function fetchDashboardUpcoming(): Promise<DashboardUpcoming> {
  const res = await fetch(`${API}/api/dashboard/upcoming`)
  if (!res.ok) throw new Error(`Failed to fetch upcoming items: ${res.status}`)
  return DashboardUpcomingSchema.parse(await res.json())
}

export async function triggerConnectorSync(name: string): Promise<void> {
  const res = await fetch(`${API}/api/connectors/${encodeURIComponent(name)}/sync`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to trigger sync for ${name}: ${res.status}`)
}

// ---------------------------------------------------------------------------
// Graph schemas (F-008 graph explorer)
// ---------------------------------------------------------------------------

const GraphEntitySchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  entity_type: z.string(),
  source_type: z.string(),
  created_at: z.string(),
})

const GraphRelationshipSchema = z.object({
  id: z.string().min(1),
  source_entity_id: z.string().min(1),
  target_entity_id: z.string().min(1),
  relationship_type: z.string(),
  properties: z.record(z.string(), z.unknown()),
})

const GraphEntityDetailSchema = GraphEntitySchema.extend({
  properties: z.record(z.string(), z.unknown()),
  relationships: z.array(GraphRelationshipSchema),
})

// ---------------------------------------------------------------------------
// Graph exported types
// ---------------------------------------------------------------------------

export type GraphEntity = z.infer<typeof GraphEntitySchema>
export type GraphRelationship = z.infer<typeof GraphRelationshipSchema>
export type GraphEntityDetail = z.infer<typeof GraphEntityDetailSchema>

// ---------------------------------------------------------------------------
// Graph API functions
// ---------------------------------------------------------------------------

export async function fetchEntities(type?: string, name?: string): Promise<GraphEntity[]> {
  const params = new URLSearchParams()
  if (type) params.set('entity_type', type)
  if (name) params.set('name', name)
  const query = params.toString()
  const res = await fetch(`${API}/api/entities${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`Failed to fetch entities: ${res.status}`)
  return z.array(GraphEntitySchema).parse(await res.json())
}

export async function fetchEntityDetail(id: string): Promise<GraphEntityDetail> {
  const res = await fetch(`${API}/api/entities/${encodeURIComponent(id)}`)
  if (!res.ok) throw new Error(`Failed to fetch entity detail: ${res.status}`)
  return GraphEntityDetailSchema.parse(await res.json())
}

export async function fetchRelationships(type?: string, entityId?: string): Promise<GraphRelationship[]> {
  const params = new URLSearchParams()
  if (type) params.set('relationship_type', type)
  if (entityId) params.set('entity_id', entityId)
  const query = params.toString()
  const res = await fetch(`${API}/api/relationships${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`Failed to fetch relationships: ${res.status}`)
  return z.array(GraphRelationshipSchema).parse(await res.json())
}
