import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

// Mock the API module
vi.mock('@/services/api', () => ({
  fetchProvidersHealth: vi.fn(),
  fetchActiveProviders: vi.fn(),
  fetchConnectorStatuses: vi.fn(),
  triggerConnectorSync: vi.fn(),
}))

import * as api from '@/services/api'
import SettingsPage from '@/pages/SettingsPage'

const mockProvidersHealth = {
  bedrock: { status: 'healthy' as const, latency_ms: 42 },
  ollama: { status: 'degraded' as const, latency_ms: 500, error: 'High latency' },
}

const mockActiveProviders = {
  llm: { provider: 'bedrock', model: 'claude-3-5-sonnet' },
  embedding: { provider: 'bedrock', model: 'titan-embed-v2' },
}

const mockConnectors = [
  {
    name: 'obsidian',
    status: 'healthy' as const,
    last_sync_at: '2026-03-20T10:00:00Z',
    last_error: null,
    documents_synced: 120,
  },
  {
    name: 'jira',
    status: 'degraded' as const,
    last_sync_at: null,
    last_error: 'Auth failed',
    documents_synced: 0,
  },
]

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.fetchProvidersHealth).mockResolvedValue(mockProvidersHealth)
  vi.mocked(api.fetchActiveProviders).mockResolvedValue(mockActiveProviders)
  vi.mocked(api.fetchConnectorStatuses).mockResolvedValue(mockConnectors)
  vi.mocked(api.triggerConnectorSync).mockResolvedValue(undefined)
})

afterEach(cleanup)

describe('SettingsPage', () => {
  it('renders Settings heading', () => {
    renderSettings()
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  it('shows Providers tab active by default', () => {
    renderSettings()
    const providersTab = screen.getByRole('button', { name: 'Providers' })
    expect(providersTab).toBeInTheDocument()
    // Providers section should be visible
    expect(screen.getByText('Active Configuration')).toBeInTheDocument()
  })

  it('shows provider health data after query resolves', async () => {
    renderSettings()
    await waitFor(() => {
      // 'bedrock' appears in both active config and health sections
      expect(screen.getAllByText('bedrock').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('42ms')).toBeInTheDocument()
  })

  it('shows degraded status badge styling for degraded provider', async () => {
    renderSettings()
    await waitFor(() => {
      const badges = screen.getAllByText('degraded')
      expect(badges.length).toBeGreaterThan(0)
    })
  })

  it('switches to Connectors tab on click', async () => {
    const user = userEvent.setup()
    renderSettings()
    await user.click(screen.getByRole('button', { name: 'Connectors' }))
    expect(screen.getByText('Connector Status')).toBeInTheDocument()
  })

  it('shows connector list with sync button and triggers sync on click', async () => {
    const user = userEvent.setup()
    renderSettings()
    await user.click(screen.getByRole('button', { name: 'Connectors' }))
    await waitFor(() => {
      expect(screen.getByText('obsidian')).toBeInTheDocument()
    })
    const syncButtons = screen.getAllByRole('button', { name: /sync/i })
    await user.click(syncButtons[0])
    expect(api.triggerConnectorSync).toHaveBeenCalledWith('obsidian')
  })

  it('switches to Preferences tab on click', async () => {
    const user = userEvent.setup()
    renderSettings()
    await user.click(screen.getByRole('button', { name: 'Preferences' }))
    expect(screen.getByText('Theme')).toBeInTheDocument()
  })

  it('renders theme buttons Light, Dark, System', async () => {
    const user = userEvent.setup()
    renderSettings()
    await user.click(screen.getByRole('button', { name: 'Preferences' }))
    expect(screen.getByRole('button', { name: 'Light' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dark' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'System' })).toBeInTheDocument()
  })

  it('renders notifications toggle and responds to click', async () => {
    const user = userEvent.setup()
    renderSettings()
    await user.click(screen.getByRole('button', { name: 'Preferences' }))
    const toggle = screen.getByRole('checkbox', { name: /notifications/i })
    expect(toggle).toBeInTheDocument()
    expect(toggle).toBeChecked()
    await user.click(toggle)
    expect(toggle).not.toBeChecked()
  })
})
