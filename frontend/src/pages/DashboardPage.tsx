import { Home } from 'lucide-react'

export default function DashboardPage() {
  return (
    <div className="flex flex-1 items-center justify-center gap-3 text-muted-foreground">
      <Home className="size-8" />
      <h1 className="text-2xl font-semibold">Dashboard</h1>
    </div>
  )
}
