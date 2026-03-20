// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import ResultCard from '@/components/search/ResultCard'
import type { SearchResult } from '@/services/api'

function makeResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    id: 'doc-1',
    title: 'Test Document',
    excerpt: 'Some excerpt content',
    source_type: 'obsidian_note',
    source_id: 'note-1',
    relevance_score: 0.92,
    created_at: '2026-03-18T12:00:00+00:00',
    url: null,
    matched_entities: [],
    related_documents: [],
    ...overrides,
  }
}

describe('ResultCard', () => {
  it('renders title, excerpt, source type badge, and relevance percentage', () => {
    render(<ResultCard result={makeResult()} index={0} />)
    expect(screen.getByText('Test Document')).toBeInTheDocument()
    expect(screen.getByText('obsidian_note')).toBeInTheDocument()
    expect(screen.getByText('92%')).toBeInTheDocument()
  })

  it('renders excerpt text', () => {
    render(<ResultCard result={makeResult()} index={0} />)
    expect(screen.getByText('Some excerpt content')).toBeInTheDocument()
  })

  it('renders formatted timestamp', () => {
    render(<ResultCard result={makeResult()} index={0} />)
    // Date should be rendered in some localised form
    expect(screen.getByText(/2026/)).toBeInTheDocument()
  })

  it('does not render URL link for javascript: URL', () => {
    render(
      <ResultCard
        result={makeResult({ url: 'javascript:alert(1)' })}
        index={0}
      />
    )
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('renders URL link for https:// URL', () => {
    render(
      <ResultCard result={makeResult({ url: 'https://example.com' })} index={0} />
    )
    const link = screen.getByRole('link')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'https://example.com')
  })

  it('shows matched_entities on expand when present', async () => {
    const user = userEvent.setup()
    render(
      <ResultCard
        result={makeResult({
          matched_entities: [{ name: 'Alice', entity_type: 'person' }],
        })}
        index={0}
      />
    )
    await user.click(screen.getByRole('button', { name: /expand/i }))
    expect(screen.getByText(/Alice/)).toBeInTheDocument()
  })

  it('does not show entities section when matched_entities is empty', () => {
    render(<ResultCard result={makeResult({ matched_entities: [] })} index={0} />)
    expect(screen.queryByText(/Entities/i)).not.toBeInTheDocument()
  })
})
