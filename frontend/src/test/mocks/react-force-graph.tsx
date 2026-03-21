import { createElement } from 'react'

// Stub for react-force-graph-2d used in jsdom test environments.
// Canvas-based rendering is incompatible with jsdom, so we render a simple div.
export default function ForceGraph2D({
  graphData,
  onNodeClick,
}: {
  graphData: { nodes: { id: string; name: string }[]; links: unknown[] }
  onNodeClick?: (node: { id: string; name: string }) => void
}) {
  return createElement(
    'div',
    { 'data-testid': 'force-graph' },
    graphData.nodes.map((n) =>
      createElement(
        'button',
        { key: n.id, 'data-testid': `node-${n.id}`, onClick: () => onNodeClick?.(n) },
        n.name
      )
    )
  )
}
