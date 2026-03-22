import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import type { AppPreferences, BackendStatus } from './notification-utils'

contextBridge.exposeInMainWorld('electron', {
  platform: process.platform,

  /**
   * Subscribe to backend lifecycle status changes.
   * Returns a cleanup function that removes the listener.
   */
  onBackendStatus(callback: (status: BackendStatus) => void): () => void {
    const handler = (_e: IpcRendererEvent, raw: unknown) => {
      // Narrow the IPC value at runtime so a future main-process change cannot
      // silently propagate an unexpected string to the renderer.
      const isKnown =
        raw === 'starting' || raw === 'healthy' || raw === 'error' || raw === 'stopped'
      if (!isKnown) {
        console.warn('[preload] unexpected backend-status value from main process:', raw)
      }
      const status: BackendStatus = isKnown ? raw : 'starting'
      callback(status)
    }
    ipcRenderer.on('backend-status', handler)
    return () => {
      ipcRenderer.removeListener('backend-status', handler)
    }
  },

  /**
   * Query the current backend status (useful on initial load to avoid
   * missing broadcasts that fired before the renderer was ready).
   */
  getBackendStatus(): Promise<BackendStatus> {
    return ipcRenderer.invoke('get-backend-status').then((value: unknown): BackendStatus => {
      if (
        value === 'starting' ||
        value === 'healthy' ||
        value === 'error' ||
        value === 'stopped'
      ) {
        return value
      }
      return 'starting'
    })
  },

  /**
   * Show a native OS notification via the main process.
   * Fire-and-forget: inputs are sanitised in the main process.
   */
  notify(title: string, body: string): void {
    ipcRenderer.send('notify', title, body)
  },

  /** Retrieve persisted user preferences from the main process. */
  getPreferences(): Promise<AppPreferences> {
    return ipcRenderer.invoke('get-preferences') as Promise<AppPreferences>
  },

  /** Persist a single preference change. Applies side-effects (e.g. auto-launch) in main. */
  setPreference(key: keyof AppPreferences, value: boolean): Promise<void> {
    return ipcRenderer.invoke('set-preference', key, value) as Promise<void>
  },

  /**
   * Subscribe to navigation requests from the main process (e.g. tray Quick Chat).
   * Returns a cleanup function that removes the listener.
   */
  onNavigate(callback: (routePath: string) => void): () => void {
    const handler = (_e: IpcRendererEvent, routePath: unknown) => {
      if (typeof routePath === 'string') callback(routePath)
    }
    ipcRenderer.on('navigate', handler)
    return () => {
      ipcRenderer.removeListener('navigate', handler)
    }
  },
})
