import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ErrorFallback } from '@/components/layout/ErrorFallback'

function ThrowingComponent(): never {
  throw new Error('Test error')
}

describe('ErrorFallback', () => {
  it('renders error message and dashboard link', () => {
    // Suppress React error boundary console.error noise
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <ThrowingComponent />,
          errorElement: <ErrorFallback />,
        },
      ],
      { initialEntries: ['/'] }
    )

    render(<RouterProvider router={router} />)

    expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument()
    expect(screen.getByText('Test error')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go to Dashboard' })).toBeInTheDocument()
  })
})
