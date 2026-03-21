import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Settings } from 'lucide-react'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/components/layout/ThemeToggle'

export function TopBar() {
  const [inputValue, setInputValue] = useState('')
  const navigate = useNavigate()

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && inputValue.trim()) {
      navigate(`/search?q=${encodeURIComponent(inputValue.trim())}`)
      setInputValue('')
    }
  }

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <div className="flex flex-1 items-center gap-2">
        <Input
          type="search"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search knowledge base..."
          className="max-w-sm"
          aria-label="Global search"
        />
      </div>
      <div className="flex items-center gap-1">
        <ThemeToggle />
        <Button variant="ghost" size="icon-sm" nativeButton={false} render={<Link to="/settings" aria-label="Settings" />}>
          <Settings className="size-4" />
        </Button>
      </div>
    </header>
  )
}
