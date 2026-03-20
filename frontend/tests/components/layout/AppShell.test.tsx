import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
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
