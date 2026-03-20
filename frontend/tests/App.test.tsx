import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

describe('App', () => {
  it('renders without crashing', async () => {
    const { default: App } = await import('../src/App')
    render(<App />)
    // Query something always visible regardless of viewport (not hidden sidebar text)
    expect(screen.getByPlaceholderText('Search knowledge base...')).toBeInTheDocument()
  })
})
