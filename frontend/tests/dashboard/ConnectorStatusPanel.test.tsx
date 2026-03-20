// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ConnectorStatusPanel from '@/components/dashboard/ConnectorStatusPanel'
import type { ConnectorStatus } from '@/services/api'

function makeConnector(
  name: string,
  status: ConnectorStatus['status'] = 'healthy',
): ConnectorStatus {
  return {
    name,
    status,
    last_sync_at: '2026-03-20T09:00:00+00:00',
    last_error: null,
    documents_synced: 10,
  }
}

describe('ConnectorStatusPanel', () => {
  it('shows skeleton cards when isLoading is true', () => {
    render(
      <ConnectorStatusPanel connectors={[]} isLoading={true} onSync={vi.fn()} isSyncing={false} />,
    )
    const skeletons = document.querySelectorAll('[data-testid="connector-skeleton"]')
    expect(skeletons).toHaveLength(3)
  })

  it('renders connector cards with healthy status badge', () => {
    const connectors = [makeConnector('teams', 'healthy'), makeConnector('obsidian', 'degraded')]
    render(
      <ConnectorStatusPanel
        connectors={connectors}
        isLoading={false}
        onSync={vi.fn()}
        isSyncing={false}
      />,
    )
    expect(screen.getByText('teams')).toBeInTheDocument()
    expect(screen.getByText('obsidian')).toBeInTheDocument()
    expect(screen.getByText('healthy')).toBeInTheDocument()
    expect(screen.getByText('degraded')).toBeInTheDocument()
  })

  it('renders unavailable status badge', () => {
    const connectors = [makeConnector('jira', 'unavailable')]
    render(
      <ConnectorStatusPanel
        connectors={connectors}
        isLoading={false}
        onSync={vi.fn()}
        isSyncing={false}
      />,
    )
    expect(screen.getByText('unavailable')).toBeInTheDocument()
  })

  it('calls onSync when sync button is clicked', () => {
    const onSync = vi.fn()
    const connectors = [makeConnector('teams')]
    render(
      <ConnectorStatusPanel
        connectors={connectors}
        isLoading={false}
        onSync={onSync}
        isSyncing={false}
      />,
    )
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    expect(onSync).toHaveBeenCalledWith('teams')
  })
})
