import { useState } from 'react'
import GraphControls from '@/components/graph/GraphControls'
import GraphCanvas from '@/components/graph/GraphCanvas'
import EntityDetail from '@/components/graph/EntityDetail'
import { useGraphData } from '@/hooks/useGraphData'
import type { GraphNode } from '@/hooks/useGraphData'

const ALL_TYPES = ['person', 'project', 'topic', 'decision', 'action_item', 'meeting']

export default function GraphPage() {
  const [selectedTypes, setSelectedTypes] = useState<string[]>(ALL_TYPES)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  const { nodes, links, isLoading } = useGraphData(selectedTypes)

  function handleNodeClick(node: GraphNode) {
    setSelectedNodeId(node.id)
  }

  function handleCloseDetail() {
    setSelectedNodeId(null)
  }

  return (
    <div className="flex h-full w-full overflow-hidden">
      <h1 className="sr-only">Graph Explorer</h1>
      {/* Left sidebar — filters */}
      <aside className="w-48 shrink-0 border-r bg-sidebar">
        <GraphControls
          selectedTypes={selectedTypes}
          onChange={setSelectedTypes}
          nodeCount={isLoading ? 0 : nodes.length}
          edgeCount={isLoading ? 0 : links.length}
        />
      </aside>

      {/* Center — graph canvas */}
      <main className="relative flex-1 overflow-hidden bg-background">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Loading graph…
          </div>
        ) : (
          <GraphCanvas
            graphData={{ nodes, links }}
            onNodeClick={handleNodeClick}
            selectedNodeId={selectedNodeId}
          />
        )}
      </main>

      {/* Right panel — entity detail */}
      {selectedNodeId && (
        <aside className="w-72 shrink-0 border-l bg-sidebar">
          <EntityDetail entityId={selectedNodeId} onClose={handleCloseDetail} />
        </aside>
      )}
    </div>
  )
}
