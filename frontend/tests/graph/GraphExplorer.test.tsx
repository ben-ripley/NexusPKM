// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// react-force-graph is aliased to a jsdom-safe stub in vite.config.ts test.alias

vi.mock('@/services/api', () => ({
  fetchEntities: vi.fn(),
  fetchEntityDetail: vi.fn(),
  fetchRelationships: vi.fn(),
}))

import * as api from '@/services/api'
import { useGraphData } from '@/hooks/useGraphData'
import GraphControls from '@/components/graph/GraphControls'
import EntityDetail from '@/components/graph/EntityDetail'
import GraphPage from '@/pages/GraphPage'
import { ALL_ENTITY_TYPES } from '@/constants/entityTypes'

const ENTITY_TYPES = [...ALL_ENTITY_TYPES]

function makeEntities() {
  return [
    { id: 'e1', name: 'Alice', entity_type: 'person', source_type: 'teams', created_at: '2026-03-01T00:00:00Z' },
    { id: 'e2', name: 'Project X', entity_type: 'project', source_type: 'jira', created_at: '2026-03-02T00:00:00Z' },
    { id: 'e3', name: 'AI Topic', entity_type: 'topic', source_type: 'obsidian', created_at: '2026-03-03T00:00:00Z' },
  ]
}

function makeRelationships() {
  return [
    { id: 'r1', source_entity_id: 'e1', target_entity_id: 'e2', relationship_type: 'works_on', properties: {} },
    { id: 'r2', source_entity_id: 'e2', target_entity_id: 'e3', relationship_type: 'relates_to', properties: {} },
  ]
}

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) =>
    createElement(
      MemoryRouter,
      {},
      createElement(QueryClientProvider, { client }, children)
    )
}

// ---------------------------------------------------------------------------
// useGraphData hook tests
// ---------------------------------------------------------------------------

describe('useGraphData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(api.fetchEntities as ReturnType<typeof vi.fn>).mockResolvedValue(makeEntities())
    ;(api.fetchRelationships as ReturnType<typeof vi.fn>).mockResolvedValue(makeRelationships())
  })

  it('returns nodes and links from API data', async () => {
    const { result } = renderHook(() => useGraphData(ENTITY_TYPES), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.nodes).toHaveLength(3)
    expect(result.current.links).toHaveLength(2)
  })

  it('filters nodes by selectedTypes', async () => {
    const { result } = renderHook(() => useGraphData(['person']), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.nodes).toHaveLength(1)
    expect(result.current.nodes[0].name).toBe('Alice')
  })

  it('returns isLoading true while fetching', () => {
    ;(api.fetchEntities as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}))
    ;(api.fetchRelationships as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useGraphData(ENTITY_TYPES), { wrapper: makeWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// GraphControls tests
// ---------------------------------------------------------------------------

describe('GraphControls', () => {
  it('renders all entity type checkboxes', () => {
    render(
      <GraphControls
        selectedTypes={ENTITY_TYPES}
        onChange={() => {}}
        nodeCount={10}
        edgeCount={5}
      />
    )
    expect(screen.getByRole('checkbox', { name: /person/i })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /project/i })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /topic/i })).toBeInTheDocument()
  })

  it('shows node and edge counts', () => {
    render(
      <GraphControls
        selectedTypes={ENTITY_TYPES}
        onChange={() => {}}
        nodeCount={42}
        edgeCount={17}
      />
    )
    expect(screen.getByText(/42 nodes/i)).toBeInTheDocument()
    expect(screen.getByText(/17 edges/i)).toBeInTheDocument()
  })

  it('calls onChange when a type checkbox is toggled off', () => {
    const onChange = vi.fn()
    render(
      <GraphControls
        selectedTypes={ENTITY_TYPES}
        onChange={onChange}
        nodeCount={3}
        edgeCount={1}
      />
    )
    fireEvent.click(screen.getByRole('checkbox', { name: /person/i }))
    expect(onChange).toHaveBeenCalledWith(ENTITY_TYPES.filter((t) => t !== 'person'))
  })

  it('calls onChange with all types when Select all is clicked', () => {
    const onChange = vi.fn()
    render(
      <GraphControls
        selectedTypes={[]}
        onChange={onChange}
        nodeCount={0}
        edgeCount={0}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /select all/i }))
    expect(onChange).toHaveBeenCalledWith(ENTITY_TYPES)
  })

  it('calls onChange with empty array when Clear all is clicked', () => {
    const onChange = vi.fn()
    render(
      <GraphControls
        selectedTypes={ENTITY_TYPES}
        onChange={onChange}
        nodeCount={3}
        edgeCount={1}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }))
    expect(onChange).toHaveBeenCalledWith([])
  })
})

// ---------------------------------------------------------------------------
// EntityDetail tests
// ---------------------------------------------------------------------------

describe('EntityDetail', () => {
  const mockDetail = {
    id: 'e1',
    name: 'Alice',
    entity_type: 'person',
    source_type: 'teams',
    created_at: '2026-03-01T00:00:00Z',
    properties: { role: 'Engineer' },
    relationships: [
      {
        id: 'r1',
        source_entity_id: 'e1',
        target_entity_id: 'e2',
        relationship_type: 'works_on',
        properties: {},
      },
    ],
  }

  beforeEach(() => {
    vi.clearAllMocks()
    ;(api.fetchEntityDetail as ReturnType<typeof vi.fn>).mockResolvedValue(mockDetail)
  })

  it('shows loading skeleton while fetching', () => {
    ;(api.fetchEntityDetail as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      createElement(
        QueryClientProvider,
        { client },
        createElement(EntityDetail, { entityId: 'e1', onClose: () => {} })
      )
    )
    expect(document.querySelectorAll('[data-testid^="entity-detail-skeleton"]').length).toBeGreaterThan(0)
  })

  it('renders entity name and type after loading', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      createElement(
        QueryClientProvider,
        { client },
        createElement(EntityDetail, { entityId: 'e1', onClose: () => {} })
      )
    )
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Alice', level: 3 })).toBeInTheDocument())
    expect(screen.getByText(/person/i)).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      createElement(
        QueryClientProvider,
        { client },
        createElement(EntityDetail, { entityId: 'e1', onClose })
      )
    )
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Alice', level: 3 })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('renders relationship list', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      createElement(
        QueryClientProvider,
        { client },
        createElement(EntityDetail, { entityId: 'e1', onClose: () => {} })
      )
    )
    await waitFor(() => expect(screen.getByText(/works_on/i)).toBeInTheDocument())
  })

  it('shows error message when fetch fails', async () => {
    ;(api.fetchEntityDetail as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      createElement(
        QueryClientProvider,
        { client },
        createElement(EntityDetail, { entityId: 'e1', onClose: () => {} })
      )
    )
    await waitFor(() => expect(screen.getByText(/failed to load entity/i)).toBeInTheDocument())
  })
})

// ---------------------------------------------------------------------------
// GraphPage integration tests
// ---------------------------------------------------------------------------

describe('GraphPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(api.fetchEntities as ReturnType<typeof vi.fn>).mockResolvedValue(makeEntities())
    ;(api.fetchRelationships as ReturnType<typeof vi.fn>).mockResolvedValue(makeRelationships())
    ;(api.fetchEntityDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'e1',
      name: 'Alice',
      entity_type: 'person',
      source_type: 'teams',
      created_at: '2026-03-01T00:00:00Z',
      properties: {},
      relationships: [],
    })
  })

  it('renders the force graph canvas', async () => {
    render(<GraphPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByTestId('force-graph')).toBeInTheDocument())
  })

  it('shows node count in controls after loading', async () => {
    render(<GraphPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByText(/3 nodes/i)).toBeInTheDocument())
  })

  it('shows entity detail panel when a node is clicked', async () => {
    render(<GraphPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByTestId('node-e1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('node-e1'))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Alice', level: 3 })).toBeInTheDocument())
  })

  it('closes entity detail panel when close button is clicked', async () => {
    render(<GraphPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByTestId('node-e1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('node-e1'))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Alice', level: 3 })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Alice', level: 3 })).not.toBeInTheDocument())
  })

  it('type filter toggle reduces node count', async () => {
    render(<GraphPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByText(/3 nodes/i)).toBeInTheDocument())
    // Uncheck 'person' — Alice should be filtered out
    fireEvent.click(screen.getByRole('checkbox', { name: /person/i }))
    await waitFor(() => expect(screen.getByText(/2 nodes/i)).toBeInTheDocument())
  })

  it('shows error message when graph data fails to load', async () => {
    ;(api.fetchEntities as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'))
    render(<GraphPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByText(/failed to load graph data/i)).toBeInTheDocument())
  })
})
