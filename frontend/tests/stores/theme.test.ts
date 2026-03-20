import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from '@testing-library/react'

describe('useThemeStore', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('defaults to system theme', async () => {
    const { useThemeStore } = await import('@/stores/theme')
    expect(useThemeStore.getState().theme).toBe('system')
  })

  it('setTheme updates theme to dark', async () => {
    const { useThemeStore } = await import('@/stores/theme')
    act(() => {
      useThemeStore.getState().setTheme('dark')
    })
    expect(useThemeStore.getState().theme).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('setTheme updates theme to light', async () => {
    const { useThemeStore } = await import('@/stores/theme')
    act(() => {
      useThemeStore.getState().setTheme('light')
    })
    expect(useThemeStore.getState().theme).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('persists theme to localStorage', async () => {
    const { useThemeStore } = await import('@/stores/theme')
    act(() => {
      useThemeStore.getState().setTheme('dark')
    })
    const stored = JSON.parse(
      localStorage.getItem('nexuspkm-theme') ?? '{}'
    )
    expect(stored.state.theme).toBe('dark')
  })

  it('does not persist resolvedTheme to localStorage', async () => {
    const { useThemeStore } = await import('@/stores/theme')
    act(() => {
      useThemeStore.getState().setTheme('dark')
    })
    const stored = JSON.parse(
      localStorage.getItem('nexuspkm-theme') ?? '{}'
    )
    expect(stored.state).not.toHaveProperty('resolvedTheme')
  })

  it('system theme applies dark class when OS prefers dark', async () => {
    // Override matchMedia to report dark preference
    const originalMatchMedia = window.matchMedia
    window.matchMedia = vi.fn((query: string) => ({
      matches: query.includes('dark'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as typeof window.matchMedia

    vi.resetModules()
    const { useThemeStore } = await import('@/stores/theme')
    act(() => {
      useThemeStore.getState().setTheme('system')
    })
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    window.matchMedia = originalMatchMedia
  })

  it('resolvedTheme returns the effective theme', async () => {
    const { useThemeStore } = await import('@/stores/theme')
    act(() => {
      useThemeStore.getState().setTheme('dark')
    })
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
  })

  it('subscribeToSystemTheme updates resolvedTheme when OS preference changes', async () => {
    let changeHandler: (() => void) | undefined
    const originalMatchMedia = window.matchMedia
    let currentMatches = false

    window.matchMedia = vi.fn((query: string) => ({
      matches: currentMatches && query.includes('dark'),
      media: query,
      addEventListener: vi.fn((_event: string, handler: () => void) => {
        changeHandler = handler
      }),
      removeEventListener: vi.fn(),
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as typeof window.matchMedia

    vi.resetModules()
    const { useThemeStore, subscribeToSystemTheme } = await import('@/stores/theme')

    // Set to system theme and subscribe
    act(() => {
      useThemeStore.getState().setTheme('system')
    })
    const cleanup = subscribeToSystemTheme()

    expect(useThemeStore.getState().resolvedTheme).toBe('light')

    // Simulate OS switching to dark
    currentMatches = true
    act(() => {
      changeHandler?.()
    })
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    cleanup()
    window.matchMedia = originalMatchMedia
  })

  it('subscribeToSystemTheme does not update when theme is not system', async () => {
    let changeHandler: (() => void) | undefined
    const originalMatchMedia = window.matchMedia
    let currentMatches = false

    window.matchMedia = vi.fn((query: string) => ({
      matches: currentMatches && query.includes('dark'),
      media: query,
      addEventListener: vi.fn((_event: string, handler: () => void) => {
        changeHandler = handler
      }),
      removeEventListener: vi.fn(),
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as typeof window.matchMedia

    vi.resetModules()
    const { useThemeStore, subscribeToSystemTheme } = await import('@/stores/theme')

    // Set to explicit light theme
    act(() => {
      useThemeStore.getState().setTheme('light')
    })
    const cleanup = subscribeToSystemTheme()

    // Simulate OS switching to dark — should be ignored
    currentMatches = true
    act(() => {
      changeHandler?.()
    })
    expect(useThemeStore.getState().resolvedTheme).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    cleanup()
    window.matchMedia = originalMatchMedia
  })
})
