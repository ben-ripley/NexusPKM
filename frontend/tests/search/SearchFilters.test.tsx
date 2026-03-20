// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import SearchFilters from '@/components/search/SearchFilters'

describe('SearchFilters', () => {
  it('renders source type checkboxes for each available type', () => {
    render(
      <SearchFilters
        filters={{}}
        availableSourceTypes={['obsidian_note', 'teams_transcript']}
        onChange={vi.fn()}
      />
    )
    expect(screen.getByLabelText('obsidian_note')).toBeInTheDocument()
    expect(screen.getByLabelText('teams_transcript')).toBeInTheDocument()
  })

  it('checking a source type calls onChange with updated filter', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <SearchFilters
        filters={{}}
        availableSourceTypes={['obsidian_note']}
        onChange={onChange}
      />
    )
    await user.click(screen.getByLabelText('obsidian_note'))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ source_types: ['obsidian_note'] })
    )
  })

  it('renders from and to date inputs', () => {
    render(
      <SearchFilters
        filters={{}}
        availableSourceTypes={[]}
        onChange={vi.fn()}
      />
    )
    expect(screen.getByLabelText(/from/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/to/i)).toBeInTheDocument()
  })

  it('Clear all calls onChange with empty object', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <SearchFilters
        filters={{ source_types: ['obsidian_note'] }}
        availableSourceTypes={['obsidian_note']}
        onChange={onChange}
      />
    )
    await user.click(screen.getByRole('button', { name: /clear all/i }))
    expect(onChange).toHaveBeenCalledWith({})
  })
})
