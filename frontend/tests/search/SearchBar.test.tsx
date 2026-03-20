// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import SearchBar from '@/components/search/SearchBar'

describe('SearchBar', () => {
  it('renders with placeholder text', () => {
    render(
      <SearchBar
        query=""
        onQueryChange={vi.fn()}
        onSearch={vi.fn()}
        suggestions={[]}
        isSearching={false}
      />
    )
    expect(
      screen.getByPlaceholderText('Search your knowledge base...')
    ).toBeInTheDocument()
  })

  it('typing calls onQueryChange', async () => {
    const onQueryChange = vi.fn()
    const user = userEvent.setup()
    render(
      <SearchBar
        query=""
        onQueryChange={onQueryChange}
        onSearch={vi.fn()}
        suggestions={[]}
        isSearching={false}
      />
    )
    await user.type(screen.getByRole('textbox'), 'hello')
    expect(onQueryChange).toHaveBeenCalled()
  })

  it('Enter key calls onSearch with current value', async () => {
    const onSearch = vi.fn()
    const user = userEvent.setup()
    render(
      <SearchBar
        query="meeting notes"
        onQueryChange={vi.fn()}
        onSearch={onSearch}
        suggestions={[]}
        isSearching={false}
      />
    )
    await user.click(screen.getByRole('textbox'))
    await user.keyboard('{Enter}')
    expect(onSearch).toHaveBeenCalledWith('meeting notes')
  })

  it('Escape key hides suggestions', async () => {
    const user = userEvent.setup()
    render(
      <SearchBar
        query="pro"
        onQueryChange={vi.fn()}
        onSearch={vi.fn()}
        suggestions={['Project Alpha', 'Project Beta']}
        isSearching={false}
      />
    )
    // Suggestions visible initially
    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    // Focus input and press Escape
    await user.click(screen.getByRole('textbox'))
    await user.keyboard('{Escape}')
    expect(screen.queryByText('Project Alpha')).not.toBeInTheDocument()
  })

  it('clicking a suggestion calls onSearch with suggestion text', async () => {
    const onSearch = vi.fn()
    const user = userEvent.setup()
    render(
      <SearchBar
        query="pro"
        onQueryChange={vi.fn()}
        onSearch={onSearch}
        suggestions={['Project Alpha']}
        isSearching={false}
      />
    )
    await user.click(screen.getByText('Project Alpha'))
    expect(onSearch).toHaveBeenCalledWith('Project Alpha')
  })

  it('shows suggestions list when suggestions prop is non-empty', () => {
    render(
      <SearchBar
        query="pro"
        onQueryChange={vi.fn()}
        onSearch={vi.fn()}
        suggestions={['Project Alpha', 'Project Beta']}
        isSearching={false}
      />
    )
    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    expect(screen.getByText('Project Beta')).toBeInTheDocument()
  })
})
