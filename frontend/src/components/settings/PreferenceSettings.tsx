import type { ReactNode } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/stores/theme'
import type { Theme } from '@/stores/theme'
import { usePreferencesStore } from '@/stores/preferences'

const THEME_OPTIONS: { value: Theme; label: string; icon: ReactNode }[] = [
  { value: 'light', label: 'Light', icon: <Sun className="size-4" /> },
  { value: 'dark', label: 'Dark', icon: <Moon className="size-4" /> },
  { value: 'system', label: 'System', icon: <Monitor className="size-4" /> },
]

export default function PreferenceSettings() {
  const { theme, setTheme } = useThemeStore()
  const { notificationsEnabled, setNotificationsEnabled } = usePreferencesStore()

  return (
    <div className="space-y-6">
      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-4 text-sm font-semibold">Theme</h2>
        <div className="flex gap-2">
          {THEME_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              type="button"
              variant={theme === opt.value ? 'default' : 'outline'}
              size="sm"
              className={cn('gap-2', theme === opt.value && 'ring-2 ring-ring ring-offset-2')}
              onClick={() => setTheme(opt.value)}
            >
              {opt.icon}
              {opt.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-4 text-sm font-semibold">Notifications</h2>
        <label className="flex cursor-pointer items-center justify-between gap-4">
          <span className="text-sm">Enable notifications</span>
          <Switch
            checked={notificationsEnabled}
            onCheckedChange={setNotificationsEnabled}
            aria-label="notifications enabled"
          />
        </label>
      </div>
    </div>
  )
}
