// Type declarations for the contextBridge API exposed by electron/preload.ts
// Only available when running inside Electron; check `window.electron` before use.
interface Window {
  electron?: {
    platform: string

    notify: {
      sync: (source: string, count: number) => void
      entity: (entityName: string, relationshipCount: number) => void
    }

    settings: {
      setMinimizeToTray: (enabled: boolean) => void
      setAutoLaunch: (enabled: boolean) => void
    }

    onNavigate: (callback: (path: string) => void) => () => void
  }
}
