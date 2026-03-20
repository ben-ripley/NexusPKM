import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { AppShell } from '@/components/layout/AppShell'
import DashboardPage from '@/pages/DashboardPage'
import ChatPage from '@/pages/ChatPage'
import SearchPage from '@/pages/SearchPage'
import GraphPage from '@/pages/GraphPage'
import SettingsPage from '@/pages/SettingsPage'
import NotFoundPage from '@/pages/NotFoundPage'

const routes = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'graph', element: <GraphPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]

function renderRoute(initialRoute: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const router = createMemoryRouter(routes, {
    initialEntries: [initialRoute],
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

describe('Router', () => {
  it('renders Dashboard at /', () => {
    renderRoute('/')
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('renders Chat at /chat', () => {
    renderRoute('/chat')
    expect(screen.getByText('New Chat')).toBeInTheDocument()
  })

  it('renders Search at /search', () => {
    renderRoute('/search')
    expect(
      screen.getByPlaceholderText('Search your knowledge base...')
    ).toBeInTheDocument()
  })

  it('renders Graph Explorer at /graph', () => {
    renderRoute('/graph')
    expect(screen.getByRole('heading', { name: 'Graph Explorer' })).toBeInTheDocument()
  })

  it('renders Settings at /settings', () => {
    renderRoute('/settings')
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  it('renders Not Found page for unknown routes', () => {
    renderRoute('/unknown-page')
    expect(screen.getByRole('heading', { name: 'Page Not Found' })).toBeInTheDocument()
    expect(screen.getByText("The page you're looking for doesn't exist.")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go to Dashboard' })).toBeInTheDocument()
  })
})
