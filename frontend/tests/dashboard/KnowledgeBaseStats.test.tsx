// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import KnowledgeBaseStats from '@/components/dashboard/KnowledgeBaseStats'
import type { DashboardStats } from '@/services/api'

const mockStats: DashboardStats = {
  total_documents: 100,
  total_entities: 50,
  total_relationships: 30,
  total_chunks: 500,
  by_source_type: {
    obsidian_note: 60,
    teams_transcript: 40,
  },
}

describe('KnowledgeBaseStats', () => {
  it('shows skeleton placeholders when isLoading is true', () => {
    render(<KnowledgeBaseStats stats={null} isLoading={true} />)
    const skeletons = document.querySelectorAll('[data-testid="stats-skeleton"]')
    expect(skeletons).toHaveLength(4)
  })

  it('renders document count', () => {
    render(<KnowledgeBaseStats stats={mockStats} isLoading={false} />)
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('renders entity count', () => {
    render(<KnowledgeBaseStats stats={mockStats} isLoading={false} />)
    expect(screen.getByText('50')).toBeInTheDocument()
  })

  it('renders relationship count', () => {
    render(<KnowledgeBaseStats stats={mockStats} isLoading={false} />)
    expect(screen.getByText('30')).toBeInTheDocument()
  })

  it('renders bar chart entries for source types', () => {
    render(<KnowledgeBaseStats stats={mockStats} isLoading={false} />)
    expect(screen.getByText('obsidian_note')).toBeInTheDocument()
    expect(screen.getByText('teams_transcript')).toBeInTheDocument()
    expect(screen.getByText('60')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
  })

  it('does not render bar chart when by_source_type is empty', () => {
    const statsNoSource: DashboardStats = { ...mockStats, by_source_type: {} }
    render(<KnowledgeBaseStats stats={statsNoSource} isLoading={false} />)
    expect(screen.queryByText('obsidian_note')).not.toBeInTheDocument()
  })
})
