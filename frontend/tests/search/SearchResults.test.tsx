// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import SearchResults from '@/components/search/SearchResults'
import type { SearchResult } from '@/services/api'

function makeResult(id: string): SearchResult {
  return {
    id,
    title: `Doc ${id}`,
    excerpt: `Excerpt for ${id}`,
    source_type: 'obsidian_note',
    source_id: `src-${id}`,
    relevance_score: 0.8,
    created_at: '2026-03-18T12:00:00+00:00',
    url: null,
    matched_entities: [],
    related_documents: [],
  }
}

describe('SearchResults', () => {
  it('shows 3 skeleton divs when isLoading is true', () => {
    render(
      <SearchResults
        results={[]}
        totalCount={0}
        isLoading={true}
        error={null}
        query="test"
      />
    )
    const skeletons = document.querySelectorAll('[data-testid="result-skeleton"]')
    expect(skeletons).toHaveLength(3)
  })

  it('shows prompt when query is empty', () => {
    render(
      <SearchResults
        results={[]}
        totalCount={0}
        isLoading={false}
        error={null}
        query=""
      />
    )
    expect(screen.getByText(/enter a query/i)).toBeInTheDocument()
  })

  it('shows empty state message when results empty and query non-empty', () => {
    render(
      <SearchResults
        results={[]}
        totalCount={0}
        isLoading={false}
        error={null}
        query="unknown xyz"
      />
    )
    expect(screen.getByText(/no results/i)).toBeInTheDocument()
    expect(screen.getByText(/unknown xyz/i)).toBeInTheDocument()
  })

  it('renders correct number of result cards', () => {
    const results = [makeResult('1'), makeResult('2'), makeResult('3')]
    render(
      <SearchResults
        results={results}
        totalCount={3}
        isLoading={false}
        error={null}
        query="test"
      />
    )
    expect(screen.getByText('Doc 1')).toBeInTheDocument()
    expect(screen.getByText('Doc 2')).toBeInTheDocument()
    expect(screen.getByText('Doc 3')).toBeInTheDocument()
  })

  it('shows error banner when error is set', () => {
    render(
      <SearchResults
        results={[]}
        totalCount={0}
        isLoading={false}
        error={new Error('Search failed')}
        query="test"
      />
    )
    expect(screen.getByText(/search failed/i)).toBeInTheDocument()
  })
})
