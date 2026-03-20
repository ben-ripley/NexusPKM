// @vitest-environment jsdom
import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { useDashboard } from '@/hooks/useDashboard'
import * as api from '@/services/api'

vi.mock('@/services/api', () => ({
  fetchDashboardActivity: vi.fn().mockResolvedValue({ items: [] }),
  fetchDashboardStats: vi.fn().mockResolvedValue({
    total_documents: 5,
    total_chunks: 25,
    total_entities: 3,
    total_relationships: 2,
    by_source_type: {},
  }),
  fetchConnectorStatuses: vi.fn().mockResolvedValue([]),
  fetchDashboardUpcoming: vi.fn().mockResolvedValue({ items: [] }),
  triggerConnectorSync: vi.fn().mockResolvedValue(undefined),
}))

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
}

describe('useDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls fetchDashboardActivity with correct query key', async () => {
    const { result } = renderHook(() => useDashboard(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isLoadingActivity).toBe(false))
    expect(api.fetchDashboardActivity).toHaveBeenCalled()
  })

  it('calls fetchDashboardStats', async () => {
    const { result } = renderHook(() => useDashboard(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isLoadingActivity).toBe(false))
    expect(api.fetchDashboardStats).toHaveBeenCalled()
    expect(result.current.stats?.total_documents).toBe(5)
  })

  it('calls fetchConnectorStatuses', async () => {
    const { result } = renderHook(() => useDashboard(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isLoadingActivity).toBe(false))
    expect(api.fetchConnectorStatuses).toHaveBeenCalled()
  })

  it('triggerSync calls triggerConnectorSync with the connector name', async () => {
    const { result } = renderHook(() => useDashboard(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isLoadingActivity).toBe(false))
    result.current.triggerSync('teams')
    await waitFor(() => expect(api.triggerConnectorSync).toHaveBeenCalled())
    const calls = (api.triggerConnectorSync as ReturnType<typeof vi.fn>).mock.calls
    expect(calls[0][0]).toBe('teams')
  })
})
