import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { SidebarProvider } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { TopBar } from '@/components/layout/TopBar'

function renderTopBar() {
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <SidebarProvider defaultOpen>
          <TopBar />
        </SidebarProvider>
      </TooltipProvider>
    </MemoryRouter>
  )
}

describe('TopBar', () => {
  it('renders the global search input', () => {
    renderTopBar()
    expect(screen.getByPlaceholderText('Search knowledge base...')).toBeInTheDocument()
  })

  it('renders the sidebar toggle', () => {
    renderTopBar()
    expect(screen.getByText('Toggle Sidebar')).toBeInTheDocument()
  })

  it('renders the theme toggle button', () => {
    renderTopBar()
    expect(screen.getByRole('button', { name: /theme/i })).toBeInTheDocument()
  })

  it('renders a settings link to /settings', () => {
    renderTopBar()
    // Button renders as <a> with role="button" via base-ui
    const settingsEl = screen.getByRole('button', { name: /settings/i }).closest('a') ??
      screen.getByRole('button', { name: /settings/i })
    expect(settingsEl).toHaveAttribute('href', '/settings')
  })
})
