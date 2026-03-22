import { create } from 'zustand'
import type { Notification } from '@/services/api'

interface NotificationState {
  notifications: Notification[]
  unreadCount: number
}

interface NotificationActions {
  setNotifications: (notifications: Notification[]) => void
  addNotification: (notification: Notification) => void
  markRead: (id: string) => void
  dismiss: (id: string) => void
  setUnreadCount: (count: number) => void
}

export const useNotificationsStore = create<NotificationState & NotificationActions>()(
  (set) => ({
    notifications: [],
    unreadCount: 0,

    setNotifications: (notifications) => set({ notifications }),

    addNotification: (notification) =>
      set((state) => ({
        notifications: [notification, ...state.notifications],
        unreadCount: notification.read ? state.unreadCount : state.unreadCount + 1,
      })),

    markRead: (id) =>
      set((state) => ({
        notifications: state.notifications.map((n) =>
          n.id === id ? { ...n, read: true } : n
        ),
        unreadCount: Math.max(0, state.unreadCount - 1),
      })),

    dismiss: (id) =>
      set((state) => {
        const target = state.notifications.find((n) => n.id === id)
        return {
          notifications: state.notifications.filter((n) => n.id !== id),
          unreadCount: target && !target.read
            ? Math.max(0, state.unreadCount - 1)
            : state.unreadCount,
        }
      }),

    setUnreadCount: (count) => set({ unreadCount: count }),
  })
)
