// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import SourceCard from '@/components/chat/SourceCard'
import type { SourceAttribution } from '@/services/websocket'

function makeSource(overrides: Partial<SourceAttribution> = {}): SourceAttribution {
  return {
    document_id: 'd1',
    title: 'Test Source',
    source_type: 'teams',
    source_id: 's1',
    excerpt: 'Some excerpt text',
    relevance_score: 0.9,
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

describe('SourceCard', () => {
  it('renders title and relevance percentage', () => {
    render(<SourceCard source={makeSource()} index={0} />)
    expect(screen.getByText('Test Source')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()
  })

  it('expands to show excerpt on click', async () => {
    const user = userEvent.setup()
    render(<SourceCard source={makeSource()} index={0} />)
    await user.click(screen.getByRole('button'))
    expect(screen.getByText('Some excerpt text')).toBeInTheDocument()
  })

  it('renders Open link for https:// URL after expanding', async () => {
    const user = userEvent.setup()
    render(<SourceCard source={makeSource({ url: 'https://example.com' })} index={0} />)
    await user.click(screen.getByRole('button'))
    const link = screen.getByRole('link', { name: /open/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'https://example.com')
  })

  it('renders Open link for http:// URL after expanding', async () => {
    const user = userEvent.setup()
    render(<SourceCard source={makeSource({ url: 'http://localhost:3000/note' })} index={0} />)
    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('link', { name: /open/i })).toBeInTheDocument()
  })

  it('does not render link for javascript: URL', async () => {
    const user = userEvent.setup()
    render(
      <SourceCard source={makeSource({ url: 'javascript:alert(1)' })} index={0} />
    )
    await user.click(screen.getByRole('button'))
    expect(screen.queryByRole('link', { name: /open/i })).not.toBeInTheDocument()
  })

  it('does not render link for data: URL', async () => {
    const user = userEvent.setup()
    render(
      <SourceCard
        source={makeSource({ url: 'data:text/html,<script>alert(1)</script>' })}
        index={0}
      />
    )
    await user.click(screen.getByRole('button'))
    expect(screen.queryByRole('link', { name: /open/i })).not.toBeInTheDocument()
  })

  it('does not render link when url is null', async () => {
    const user = userEvent.setup()
    render(<SourceCard source={makeSource({ url: null })} index={0} />)
    await user.click(screen.getByRole('button'))
    expect(screen.queryByRole('link', { name: /open/i })).not.toBeInTheDocument()
  })

  it('does not render link when url is absent', async () => {
    const user = userEvent.setup()
    render(<SourceCard source={makeSource()} index={0} />)
    await user.click(screen.getByRole('button'))
    expect(screen.queryByRole('link', { name: /open/i })).not.toBeInTheDocument()
  })
})
