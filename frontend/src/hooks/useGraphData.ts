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
      .filter((r) => nodeIdSet.has(r.from_id) && nodeIdSet.has(r.to_id))
      .map((r) => ({
        id: `${r.rel_type}:${r.from_id}:${r.to_id}`,
        source: r.from_id,
        target: r.to_id,
        relationship_type: r.rel_type,
      }))

    return { nodes, links }
  }, [entitiesQuery.data, relationshipsQuery.data, selectedTypes])

  return {
    ...graphData,
    isLoading: entitiesQuery.isLoading || relationshipsQuery.isLoading,
    error: entitiesQuery.error ?? relationshipsQuery.error,
  }
}
