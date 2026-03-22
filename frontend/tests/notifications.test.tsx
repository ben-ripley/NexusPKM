import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

// Mock API and WebSocket — must be before imports (Vitest hoisting)
vi.mock('@/services/api', () => ({
  fetchNotifications: vi.fn(),
  fetchUnreadCount: vi.fn(),
  markNotificationRead: vi.fn(),
  dismissNotification: vi.fn(),
  resolveContradiction: vi.fn(),
  fetchNotificationPreferences: vi.fn(),
  updateNotificationPreferences: vi.fn(),
}))

vi.mock('@/services/websocket', () => ({
  ChatWebSocket: vi.fn(),
}))

import * as api from '@/services/api'
import NotificationBell from '@/components/notifications/NotificationBell'
import NotificationPanel from '@/components/notifications/NotificationPanel'
import NotificationSettings from '@/components/settings/NotificationSettings'
import { useNotificationsStore } from '@/stores/notifications'
import type { Notification } from '@/services/api'

const mockNotifications: Notification[] = [
  {
    id: 'n-1',
    type: 'meeting_prep',
    title: 'Upcoming: Sprint Review',
    summary: 'Attendees: Alice, Bob',
    priority: 'high',
    data: { meeting_id: 'm-1' },
    read: false,
    created_at: '2026-03-21T10:00:00Z',
  },
  {
    id: 'n-2',
    type: 'related_content',
    title: 'Related content: Project Alpha Notes',
    summary: 'Connected to 2 existing documents',
    priority: 'low',
    data: {},
    read: true,
    created_at: '2026-03-21T09:00:00Z',
  },
]

const mockPreferences = {
  meeting_prep_enabled: true,
  meeting_prep_lead_time_minutes: 60,
  related_content_enabled: true,
  related_content_threshold: 0.7,
  contradiction_alerts_enabled: true,
  webhook_url: null,
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderWith(ui: React.ReactElement) {
  const client = makeClient()
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.fetchNotifications).mockResolvedValue(mockNotifications)
  vi.mocked(api.fetchUnreadCount).mockResolvedValue({ count: 1 })
  vi.mocked(api.markNotificationRead).mockResolvedValue(undefined)
  vi.mocked(api.dismissNotification).mockResolvedValue(undefined)
  vi.mocked(api.resolveContradiction).mockResolvedValue(undefined)
  vi.mocked(api.fetchNotificationPreferences).mockResolvedValue(mockPreferences)
  vi.mocked(api.updateNotificationPreferences).mockResolvedValue(mockPreferences)
  // Reset store
  useNotificationsStore.setState({ notifications: [], unreadCount: 0 })
})

afterEach(cleanup)

// ---------------------------------------------------------------------------
// NotificationBell
// ---------------------------------------------------------------------------

describe('NotificationBell', () => {
  it('renders bell icon button', () => {
    renderWith(<NotificationBell />)
    expect(screen.getByRole('button', { name: /notifications/i })).toBeInTheDocument()
  })

  it('shows unread count badge when count > 0', async () => {
    useNotificationsStore.setState({ unreadCount: 3 })
    renderWith(<NotificationBell />)
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('hides badge when count is 0', () => {
    useNotificationsStore.setState({ unreadCount: 0 })
    renderWith(<NotificationBell />)
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('opens panel on click', async () => {
    const user = userEvent.setup()
    useNotificationsStore.setState({ notifications: mockNotifications, unreadCount: 1 })
    renderWith(<NotificationBell />)
    await user.click(screen.getByRole('button', { name: /notifications/i }))
    expect(screen.getByText('Upcoming: Sprint Review')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// NotificationPanel
// ---------------------------------------------------------------------------

describe('NotificationPanel', () => {
  it('shows empty state when no notifications', () => {
    renderWith(<NotificationPanel onClose={() => {}} />)
    expect(screen.getByText(/no notifications/i)).toBeInTheDocument()
  })

  it('renders notification list', () => {
    useNotificationsStore.setState({ notifications: mockNotifications })
    renderWith(<NotificationPanel onClose={() => {}} />)
    expect(screen.getByText('Upcoming: Sprint Review')).toBeInTheDocument()
    expect(screen.getByText('Related content: Project Alpha Notes')).toBeInTheDocument()
  })

  it('shows no mark-read buttons (feature removed)', () => {
    useNotificationsStore.setState({ notifications: mockNotifications })
    renderWith(<NotificationPanel onClose={() => {}} />)
    expect(screen.queryByRole('button', { name: /mark read/i })).not.toBeInTheDocument()
  })

  it('shows dismiss button for each notification', () => {
    useNotificationsStore.setState({ notifications: mockNotifications })
    renderWith(<NotificationPanel onClose={() => {}} />)
    const dismissBtns = screen.getAllByRole('button', { name: /dismiss/i })
    expect(dismissBtns).toHaveLength(2)
  })

  it('shows resolve button only for contradiction notifications', () => {
    const contradictionNotif: Notification = {
      id: 'contradiction_c-1',
      type: 'contradiction',
      title: "'status' conflict on 'Foo' (project)",
      summary: "Field 'status' changed from 'open' to 'closed'",
      priority: 'medium',
      data: { contradiction_id: 'c-1', entity_id: 'e-1', field_name: 'status' },
      read: false,
      created_at: '2026-03-21T10:00:00Z',
    }
    useNotificationsStore.setState({ notifications: [contradictionNotif, mockNotifications[0]] })
    renderWith(<NotificationPanel onClose={() => {}} />)
    const resolveBtns = screen.getAllByRole('button', { name: /resolve/i })
    expect(resolveBtns).toHaveLength(1)
  })

  it('calls resolveContradiction with contradiction_id on resolve click', async () => {
    const user = userEvent.setup()
    const contradictionNotif: Notification = {
      id: 'contradiction_c-42',
      type: 'contradiction',
      title: "'status' conflict",
      summary: 'summary',
      priority: 'medium',
      data: { contradiction_id: 'c-42', entity_id: 'e-1', field_name: 'status' },
      read: false,
      created_at: '2026-03-21T10:00:00Z',
    }
    useNotificationsStore.setState({ notifications: [contradictionNotif] })
    renderWith(<NotificationPanel onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: /resolve/i }))
    await waitFor(() => expect(api.resolveContradiction).toHaveBeenCalled())
    expect(vi.mocked(api.resolveContradiction).mock.calls[0][0]).toBe('c-42')
  })

  it('dismisses notification from store after resolve succeeds', async () => {
    const user = userEvent.setup()
    const contradictionNotif: Notification = {
      id: 'contradiction_c-99',
      type: 'contradiction',
      title: "'status' conflict",
      summary: 'summary',
      priority: 'medium',
      data: { contradiction_id: 'c-99', entity_id: 'e-1', field_name: 'status' },
      read: false,
      created_at: '2026-03-21T10:00:00Z',
    }
    useNotificationsStore.setState({ notifications: [contradictionNotif] })
    renderWith(<NotificationPanel onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: /resolve/i }))
    await waitFor(() =>
      expect(
        useNotificationsStore.getState().notifications.find((n) => n.id === 'contradiction_c-99')
      ).toBeUndefined()
    )
  })

  it('shows source badge when notification has source_type', () => {
    const notifWithSource: Notification = {
      id: 'contradiction_c-src',
      type: 'contradiction',
      title: "'status' conflict",
      summary: 'summary',
      priority: 'medium',
      data: {
        contradiction_id: 'c-src',
        source_type: 'obsidian_note',
        source_title: 'Quebec City.md',
      },
      read: false,
      created_at: '2026-03-21T10:00:00Z',
    }
    useNotificationsStore.setState({ notifications: [notifWithSource] })
    renderWith(<NotificationPanel onClose={() => {}} />)
    expect(screen.getByText(/obsidian note/i)).toBeInTheDocument()
  })

  it('shows open link when notification has a safe source_url', () => {
    const notifWithUrl: Notification = {
      id: 'contradiction_c-url',
      type: 'contradiction',
      title: "'status' conflict",
      summary: 'summary',
      priority: 'medium',
      data: {
        contradiction_id: 'c-url',
        source_type: 'obsidian_note',
        source_url: 'obsidian://open?path=%2Fvault%2FNote.md',
      },
      read: false,
      created_at: '2026-03-21T10:00:00Z',
    }
    useNotificationsStore.setState({ notifications: [notifWithUrl] })
    renderWith(<NotificationPanel onClose={() => {}} />)
    const openLink = screen.getByRole('link', { name: /open/i })
    expect(openLink).toBeInTheDocument()
    expect(openLink).toHaveAttribute('href', 'obsidian://open?path=%2Fvault%2FNote.md')
  })

  it('does not show open link for unsafe URLs', () => {
    const notifBadUrl: Notification = {
      id: 'contradiction_c-bad',
      type: 'contradiction',
      title: "'status' conflict",
      summary: 'summary',
      priority: 'medium',
      data: {
        contradiction_id: 'c-bad',
        source_type: 'obsidian_note',
        source_url: 'javascript:alert(1)',
      },
      read: false,
      created_at: '2026-03-21T10:00:00Z',
    }
    useNotificationsStore.setState({ notifications: [notifBadUrl] })
    renderWith(<NotificationPanel onClose={() => {}} />)
    expect(screen.queryByRole('link', { name: /open/i })).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// NotificationSettings
// ---------------------------------------------------------------------------

describe('NotificationSettings', () => {
  it('renders preferences checkboxes', async () => {
    renderWith(<NotificationSettings />)
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: /meeting prep/i })).toBeInTheDocument()
    })
    expect(screen.getByRole('checkbox', { name: /related content/i })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /contradiction/i })).toBeInTheDocument()
  })

  it('shows error when preferences load fails', async () => {
    vi.mocked(api.fetchNotificationPreferences).mockRejectedValue(new Error('Network error'))
    renderWith(<NotificationSettings />)
    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument()
    })
  })

  it('submits updated preferences on save', async () => {
    const user = userEvent.setup()
    renderWith(<NotificationSettings />)
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: /meeting prep/i })).toBeInTheDocument()
    })
    const checkbox = screen.getByRole('checkbox', { name: /meeting prep/i })
    await user.click(checkbox)
    const saveBtn = screen.getByRole('button', { name: /save/i })
    await user.click(saveBtn)
    await waitFor(() => expect(api.updateNotificationPreferences).toHaveBeenCalled())
  })
})

// ---------------------------------------------------------------------------
// Zustand store
// ---------------------------------------------------------------------------

describe('useNotificationsStore', () => {
  it('addNotification prepends to list', () => {
    const store = useNotificationsStore.getState()
    store.setNotifications(mockNotifications)
    const newNotif: Notification = {
      id: 'n-new',
      type: 'insight',
      title: 'New!',
      summary: 'Summary',
      priority: 'low',
      data: {},
      read: false,
      created_at: '2026-03-21T11:00:00Z',
    }
    store.addNotification(newNotif)
    expect(useNotificationsStore.getState().notifications[0].id).toBe('n-new')
  })

  it('markRead sets read=true for matching id', () => {
    const store = useNotificationsStore.getState()
    store.setNotifications(mockNotifications)
    store.markRead('n-1')
    const n = useNotificationsStore.getState().notifications.find((n) => n.id === 'n-1')
    expect(n?.read).toBe(true)
  })

  it('dismiss removes notification from list', () => {
    const store = useNotificationsStore.getState()
    store.setNotifications(mockNotifications)
    store.dismiss('n-1')
    expect(useNotificationsStore.getState().notifications.find((n) => n.id === 'n-1')).toBeUndefined()
  })

  it('setUnreadCount updates count', () => {
    useNotificationsStore.getState().setUnreadCount(5)
    expect(useNotificationsStore.getState().unreadCount).toBe(5)
  })
})
