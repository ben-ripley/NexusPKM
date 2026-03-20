import { Settings } from 'lucide-react'

export default function SettingsPage() {
  return (
    <div className="flex flex-1 items-center justify-center gap-3 text-muted-foreground">
      <Settings className="size-8" />
      <h1 className="text-2xl font-semibold">Settings</h1>
    </div>
  )
}
