import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

describe('App', () => {
  it('renders without crashing', async () => {
    const { default: App } = await import('../src/App')
    render(<App />)
    expect(screen.getByText('NexusPKM')).toBeInTheDocument()
  })
})
