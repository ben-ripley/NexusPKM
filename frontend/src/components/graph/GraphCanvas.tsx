import { useCallback, useEffect, useRef, useState } from 'react'
import { ForceGraph2D } from 'react-force-graph'
import type { GraphNode, GraphLink } from '@/hooks/useGraphData'

const TYPE_COLORS: Record<string, string> = {
  person: '#3b82f6',
  project: '#10b981',
  topic: '#f59e0b',
  decision: '#8b5cf6',
  action_item: '#ef4444',
  meeting: '#06b6d4',
}

const DEFAULT_COLOR = '#94a3b8'
const SELECTED_RING_COLOR = '#ffffff'
const NODE_RADIUS = 6

interface Props {
  graphData: { nodes: GraphNode[]; links: GraphLink[] }
  onNodeClick: (node: GraphNode) => void
  selectedNodeId: string | null
}

export default function GraphCanvas({ graphData, onNodeClick, selectedNodeId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        const { width, height } = entry.contentRect
        setDimensions({ width, height })
      }
    })

    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const paintNode = useCallback(
    (node: GraphNode & { x?: number; y?: number }, ctx: CanvasRenderingContext2D) => {
      const x = node.x ?? 0
      const y = node.y ?? 0
      const color = TYPE_COLORS[node.entity_type] ?? DEFAULT_COLOR

      if (node.id === selectedNodeId) {
        ctx.beginPath()
        ctx.arc(x, y, NODE_RADIUS + 3, 0, 2 * Math.PI)
        ctx.fillStyle = SELECTED_RING_COLOR
        ctx.fill()
      }

      ctx.beginPath()
      ctx.arc(x, y, NODE_RADIUS, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.fill()
    },
    [selectedNodeId]
  )

  return (
    <div ref={containerRef} className="size-full">
      {dimensions.width > 0 && (
        <ForceGraph2D
          graphData={graphData}
          nodeCanvasObject={paintNode}
          nodeCanvasObjectMode={() => 'replace'}
          onNodeClick={(node) => onNodeClick(node as GraphNode)}
          nodeLabel={(node) => (node as GraphNode).name}
          linkColor={() => '#475569'}
          backgroundColor="transparent"
          width={dimensions.width}
          height={dimensions.height}
        />
      )}
    </div>
  )
}
