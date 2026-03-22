import { useState } from 'react'
import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useNotificationsStore } from '@/stores/notifications'
import NotificationPanel from './NotificationPanel'

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const unreadCount = useNotificationsStore((s) => s.unreadCount)

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Notifications"
        onClick={() => setOpen((prev) => !prev)}
      >
        <Bell className="size-4" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-destructive text-[10px] font-medium text-destructive-foreground">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </Button>
      {open && <NotificationPanel onClose={() => setOpen(false)} />}
    </div>
  )
}
