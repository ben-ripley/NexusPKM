import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('ThemeToggle', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      length: 0,
      key: vi.fn(() => null),
    })
    document.documentElement.classList.remove('dark')

    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }))
    )

    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders a theme toggle button', async () => {
    const { ThemeToggle } = await import(
      '@/components/layout/ThemeToggle'
    )
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: /theme/i })).toBeInTheDocument()
  })

  it('cycles theme on click: system -> light -> dark -> system', async () => {
    const { ThemeToggle } = await import(
      '@/components/layout/ThemeToggle'
    )
    const { useThemeStore } = await import('@/stores/theme')
    const user = userEvent.setup()

    render(<ThemeToggle />)
    const button = screen.getByRole('button', { name: /theme/i })

    // system (default) -> light
    expect(useThemeStore.getState().theme).toBe('system')
    await user.click(button)
    expect(useThemeStore.getState().theme).toBe('light')

    // light -> dark
    await user.click(button)
    expect(useThemeStore.getState().theme).toBe('dark')

    // dark -> system
    await user.click(button)
    expect(useThemeStore.getState().theme).toBe('system')
  })
})
