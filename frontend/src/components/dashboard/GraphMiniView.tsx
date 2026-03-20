import { Network } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export default function GraphMiniView() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Network className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">Knowledge Graph</h2>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-4 py-8 text-center text-muted-foreground">
        <Network className="size-12 opacity-30" />
        <div className="space-y-1">
          <p className="text-sm font-medium">Graph visualization coming soon</p>
          <p className="text-xs">Visual exploration of your knowledge connections</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => navigate('/graph')}>
          Open Graph Explorer
        </Button>
      </div>
    </div>
  )
}
