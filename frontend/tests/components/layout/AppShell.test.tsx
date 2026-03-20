import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from '@/components/layout/AppShell'

function renderShell(initialRoute = '/') {
  const router = createMemoryRouter(
    [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <div>Dashboard Content</div> },
          { path: 'chat', element: <div>Chat Content</div> },
        ],
      },
    ],
    { initialEntries: [initialRoute] }
  )
  return render(<RouterProvider router={router} />)
}

describe('AppShell', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      length: 0,
      key: vi.fn(() => null),
    })

    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }))
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('renders the sidebar navigation', () => {
    renderShell()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Chat')).toBeInTheDocument()
  })

  it('renders the top bar', () => {
    renderShell()
    expect(screen.getByPlaceholderText('Search knowledge base...')).toBeInTheDocument()
  })

  it('renders the content outlet', () => {
    renderShell('/')
    expect(screen.getByText('Dashboard Content')).toBeInTheDocument()
  })

  it('renders different content for different routes', () => {
    renderShell('/chat')
    expect(screen.getByText('Chat Content')).toBeInTheDocument()
  })
})
