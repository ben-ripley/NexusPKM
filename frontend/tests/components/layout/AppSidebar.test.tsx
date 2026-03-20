import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { SidebarProvider } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppSidebar } from '@/components/layout/AppSidebar'

function renderSidebar(initialRoute = '/') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <TooltipProvider>
        <SidebarProvider defaultOpen>
          <AppSidebar />
        </SidebarProvider>
      </TooltipProvider>
    </MemoryRouter>
  )
}

describe('AppSidebar', () => {
  it('renders all navigation links', () => {
    renderSidebar()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Chat')).toBeInTheDocument()
    expect(screen.getByText('Search')).toBeInTheDocument()
    expect(screen.getByText('Graph Explorer')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('renders the NexusPKM brand', () => {
    renderSidebar()
    expect(screen.getByText('NexusPKM')).toBeInTheDocument()
  })

  it('highlights active nav link for Dashboard', () => {
    renderSidebar('/')
    const dashboardButton = screen.getByText('Dashboard').closest('[data-slot="sidebar-menu-button"]')
    expect(dashboardButton).toHaveAttribute('data-active')
  })

  it('highlights active nav link for Chat', () => {
    renderSidebar('/chat')
    const chatButton = screen.getByText('Chat').closest('[data-slot="sidebar-menu-button"]')
    expect(chatButton).toHaveAttribute('data-active')
  })
})
