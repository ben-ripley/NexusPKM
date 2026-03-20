import { Search } from 'lucide-react'

export default function SearchPage() {
  return (
    <div className="flex flex-1 items-center justify-center gap-3 text-muted-foreground">
      <Search className="size-8" />
      <h1 className="text-2xl font-semibold">Search</h1>
    </div>
  )
}
