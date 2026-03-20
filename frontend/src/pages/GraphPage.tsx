import { Network } from 'lucide-react'

export default function GraphPage() {
  return (
    <div className="flex flex-1 items-center justify-center gap-3 text-muted-foreground">
      <Network className="size-8" />
      <h1 className="text-2xl font-semibold">Graph Explorer</h1>
    </div>
  )
}
