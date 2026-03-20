import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

contextBridge.exposeInMainWorld('electron', {
  platform: process.platform,

  notify: {
    sync: (source: string, count: number) =>
      ipcRenderer.send('notify:sync', source, count),
    entity: (entityName: string, relationshipCount: number) =>
      ipcRenderer.send('notify:entity', entityName, relationshipCount),
  },

  settings: {
    setMinimizeToTray: (enabled: boolean) =>
      ipcRenderer.send('settings:minimize-to-tray', enabled),
    setAutoLaunch: (enabled: boolean) =>
      ipcRenderer.send('settings:auto-launch', enabled),
  },

  // Main process can request navigation (e.g. Quick Chat tray button).
  // Returns an unsubscribe function so the renderer can clean up on unmount.
  onNavigate: (callback: (path: string) => void): (() => void) => {
    const listener = (_event: IpcRendererEvent, path: string): void => callback(path)
    ipcRenderer.on('navigate', listener)
    return () => {
      ipcRenderer.removeListener('navigate', listener)
    }
  },
})
