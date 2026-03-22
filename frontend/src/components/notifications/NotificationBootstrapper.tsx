/**
 * Bootstraps notification data from the API into the Zustand store.
 * Must be rendered inside a QueryClientProvider.
 */
import { useNotificationsList, useUnreadCount, useNotificationWebSocket } from '@/hooks/useNotifications'

export default function NotificationBootstrapper() {
  useUnreadCount()
  useNotificationsList()
  useNotificationWebSocket()
  return null
}
