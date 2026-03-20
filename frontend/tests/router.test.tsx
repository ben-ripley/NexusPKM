import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AppShell } from '@/components/layout/AppShell'
import DashboardPage from '@/pages/DashboardPage'
import ChatPage from '@/pages/ChatPage'
import SearchPage from '@/pages/SearchPage'
import GraphPage from '@/pages/GraphPage'
import SettingsPage from '@/pages/SettingsPage'

const routes = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'graph', element: <GraphPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]

function renderRoute(initialRoute: string) {
  const router = createMemoryRouter(routes, {
    initialEntries: [initialRoute],
  })
  return render(<RouterProvider router={router} />)
}

describe('Router', () => {
  it('renders Dashboard at /', () => {
    renderRoute('/')
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('renders Chat at /chat', () => {
    renderRoute('/chat')
    expect(screen.getByRole('heading', { name: 'Chat' })).toBeInTheDocument()
  })

  it('renders Search at /search', () => {
    renderRoute('/search')
    expect(screen.getByRole('heading', { name: 'Search' })).toBeInTheDocument()
  })

  it('renders Graph Explorer at /graph', () => {
    renderRoute('/graph')
    expect(screen.getByRole('heading', { name: 'Graph Explorer' })).toBeInTheDocument()
  })

  it('renders Settings at /settings', () => {
    renderRoute('/settings')
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })
})
