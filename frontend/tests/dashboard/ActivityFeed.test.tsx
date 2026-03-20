// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ActivityFeed from '@/components/dashboard/ActivityFeed'
import type { ActivityItem } from '@/services/api'

function makeItem(id: string): ActivityItem {
  return {
    id,
    type: 'document_ingested',
    title: `Activity ${id}`,
    description: `Description for ${id}`,
    source_type: 'obsidian_note',
    timestamp: '2026-03-20T10:00:00+00:00',
  }
}

describe('ActivityFeed', () => {
  it('shows skeleton rows when isLoading is true', () => {
    render(<ActivityFeed items={[]} isLoading={true} />)
    const skeletons = document.querySelectorAll('[data-testid="activity-skeleton"]')
    expect(skeletons).toHaveLength(4)
  })

  it('shows empty state when no items', () => {
    render(<ActivityFeed items={[]} isLoading={false} />)
    expect(screen.getByText(/no recent activity/i)).toBeInTheDocument()
  })

  it('renders correct number of activity items with title', () => {
    const items = [makeItem('1'), makeItem('2'), makeItem('3')]
    render(<ActivityFeed items={items} isLoading={false} />)
    expect(screen.getByText('Activity 1')).toBeInTheDocument()
    expect(screen.getByText('Activity 2')).toBeInTheDocument()
    expect(screen.getByText('Activity 3')).toBeInTheDocument()
  })

  it('shows source badge for items with source_type', () => {
    const items = [makeItem('1')]
    render(<ActivityFeed items={items} isLoading={false} />)
    expect(screen.getByText('obsidian_note')).toBeInTheDocument()
  })
})
