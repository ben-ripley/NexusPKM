import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  dismissNotification,
  fetchNotificationPreferences,
  updateNotificationPreferences,
} from '@/services/api'
import type { NotificationPreferences } from '@/services/api'
import { useNotificationsStore } from '@/stores/notifications'

const NOTIFICATIONS_KEY = ['notifications']
const UNREAD_COUNT_KEY = ['notifications', 'unread-count']
const PREFERENCES_KEY = ['notifications', 'preferences']

export function useNotificationsList(unreadOnly?: boolean) {
  const setNotifications = useNotificationsStore((s) => s.setNotifications)
  const result = useQuery({
    queryKey: [...NOTIFICATIONS_KEY, { unreadOnly }],
    queryFn: () => fetchNotifications(unreadOnly),
  })
  useEffect(() => {
    if (result.data) setNotifications(result.data)
  }, [result.data, setNotifications])
  return result
}

export function useUnreadCount() {
  const setUnreadCount = useNotificationsStore((s) => s.setUnreadCount)
  const result = useQuery({
    queryKey: UNREAD_COUNT_KEY,
    queryFn: fetchUnreadCount,
    refetchInterval: 30_000,
  })
  useEffect(() => {
    if (result.data) setUnreadCount(result.data.count)
  }, [result.data, setUnreadCount])
  return result
}

export function useMarkRead() {
  const markRead = useNotificationsStore((s) => s.markRead)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: markNotificationRead,
    onSuccess: (_data, id) => {
      markRead(id)
      queryClient.invalidateQueries({ queryKey: UNREAD_COUNT_KEY })
    },
  })
}

export function useDismiss() {
  const dismiss = useNotificationsStore((s) => s.dismiss)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: dismissNotification,
    onSuccess: (_data, id) => {
      dismiss(id)
      queryClient.invalidateQueries({ queryKey: UNREAD_COUNT_KEY })
    },
  })
}

export function useNotificationPreferences() {
  return useQuery({
    queryKey: PREFERENCES_KEY,
    queryFn: fetchNotificationPreferences,
  })
}

export function useUpdatePreferences() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (prefs: NotificationPreferences) => updateNotificationPreferences(prefs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PREFERENCES_KEY })
    },
  })
}

export function useNotificationWebSocket() {
  const addNotification = useNotificationsStore((s) => s.addNotification)
  const queryClient = useQueryClient()

  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL as string | undefined
    const wsBase = apiUrl
      ? apiUrl.replace(/^http/, 'ws')
      : (() => {
          const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
          const host = window.location.host || 'localhost:8000'
          return `${protocol}//${host}`
        })()

    let ws: WebSocket | null = null
    let shouldReconnect = true
    let retryCount = 0
    const maxRetries = 5

    function connect() {
      ws = new WebSocket(`${wsBase}/ws/notifications`)

      ws.onmessage = (event: MessageEvent) => {
        try {
          const notif = JSON.parse(event.data as string)
          // addNotification already increments unreadCount in the store.
          addNotification(notif)
          // Invalidate the server count so a background refetch stays in sync.
          if (!notif.read) {
            queryClient.invalidateQueries({ queryKey: UNREAD_COUNT_KEY })
          }
        } catch {
          // ignore malformed frames
        }
      }

      ws.onclose = (event: CloseEvent) => {
        if (!shouldReconnect || event.code === 1000) return
        if (retryCount < maxRetries) {
          const delay = Math.pow(2, retryCount) * 500
          retryCount++
          setTimeout(connect, delay)
        }
      }
    }

    connect()

    return () => {
      shouldReconnect = false
      ws?.close(1000)
    }
  }, [addNotification, queryClient])
}
