import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from '@testing-library/react'

describe('useThemeStore', () => {
  beforeEach(() => {
    localStorage.clear()
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

  it('system theme applies dark class when OS prefers dark', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: query.includes('dark'),
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
    const { useThemeStore } = await import('@/stores/theme')
    act(() => {
      useThemeStore.getState().setTheme('system')
    })
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('resolvedTheme returns the effective theme', async () => {
    const { useThemeStore } = await import('@/stores/theme')
    act(() => {
      useThemeStore.getState().setTheme('dark')
    })
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
  })
})
