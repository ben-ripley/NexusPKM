import { contextBridge, ipcRenderer } from 'electron'

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
})
