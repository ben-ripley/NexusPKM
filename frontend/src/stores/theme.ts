import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: Theme) => void
}

function getSystemTheme(): 'light' | 'dark' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function applyTheme(resolved: 'light' | 'dark') {
  if (resolved === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

function resolveTheme(theme: Theme): 'light' | 'dark' {
  return theme === 'system' ? getSystemTheme() : theme
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'system',
      resolvedTheme: getSystemTheme(),
      setTheme: (theme: Theme) => {
        const resolved = resolveTheme(theme)
        applyTheme(resolved)
        set({ theme, resolvedTheme: resolved })
      },
    }),
    {
      name: 'nexuspkm-theme',
      partialize: (state) => ({ theme: state.theme }),
      onRehydrateStorage: () => {
        return (state) => {
          if (state) {
            const resolved = resolveTheme(state.theme)
            applyTheme(resolved)
            state.resolvedTheme = resolved
          }
        }
      },
    }
  )
)

export function subscribeToSystemTheme() {
  const mql = window.matchMedia('(prefers-color-scheme: dark)')
  const handler = () => {
    const { theme } = useThemeStore.getState()
    if (theme === 'system') {
      const resolved = getSystemTheme()
      applyTheme(resolved)
      useThemeStore.setState({ resolvedTheme: resolved })
    }
  }
  mql.addEventListener('change', handler)
  return () => mql.removeEventListener('change', handler)
}
