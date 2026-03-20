import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchEntities, fetchRelationships } from '@/services/api'
import type { GraphEntity, GraphRelationship } from '@/services/api'

export type GraphNode = GraphEntity

export interface GraphLink {
  id: string
  source: string
  target: string
  relationship_type: string
}

export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

export function useGraphData(selectedTypes: string[]) {
  const entitiesQuery = useQuery({
    queryKey: ['graph-entities'],
    queryFn: () => fetchEntities(),
    staleTime: 60_000,
  })

  const relationshipsQuery = useQuery({
    queryKey: ['graph-relationships'],
    queryFn: () => fetchRelationships(),
    staleTime: 60_000,
  })

  const graphData = useMemo<GraphData>(() => {
    const allEntities: GraphEntity[] = entitiesQuery.data ?? []
    const allRelationships: GraphRelationship[] = relationshipsQuery.data ?? []

    const selectedSet = new Set(selectedTypes)
    const nodes = allEntities.filter((e) => selectedSet.has(e.entity_type))
    const nodeIdSet = new Set(nodes.map((n) => n.id))

    // Only include links where both endpoints are in the filtered node set
    const links: GraphLink[] = allRelationships
      .filter((r) => nodeIdSet.has(r.source_entity_id) && nodeIdSet.has(r.target_entity_id))
      .map((r) => ({
        id: r.id,
        source: r.source_entity_id,
        target: r.target_entity_id,
        relationship_type: r.relationship_type,
      }))

    return { nodes, links }
  }, [entitiesQuery.data, relationshipsQuery.data, selectedTypes])

  return {
    ...graphData,
    isLoading: entitiesQuery.isLoading || relationshipsQuery.isLoading,
    error: entitiesQuery.error ?? relationshipsQuery.error,
  }
}
