import '@testing-library/jest-dom'

// Only set up browser globals in jsdom environment (not in Node/Electron tests)
if (typeof window !== 'undefined') {
  // Provide a default matchMedia mock for jsdom (needed by theme store and sidebar)
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  })

  // Mock localStorage for Node 22+ jsdom compatibility
  const localStorageMock = (() => {
    let store: Record<string, string> = {}
    return {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => {
        store[key] = value
      },
      removeItem: (key: string) => {
        delete store[key]
      },
      clear: () => {
        store = {}
      },
      get length() {
        return Object.keys(store).length
      },
      key: (index: number) => Object.keys(store)[index] ?? null,
    }
  })()

  Object.defineProperty(window, 'localStorage', {
    writable: true,
    value: localStorageMock,
  })
}
