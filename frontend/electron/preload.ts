import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

type BackendStatus = 'starting' | 'healthy' | 'error' | 'stopped'

contextBridge.exposeInMainWorld('electron', {
  platform: process.platform,

  /**
   * Subscribe to backend lifecycle status changes.
   * Returns a cleanup function that removes the listener.
   */
  onBackendStatus(callback: (status: BackendStatus) => void): () => void {
    const handler = (_e: IpcRendererEvent, status: BackendStatus) => callback(status)
    ipcRenderer.on('backend-status', handler)
    return () => {
      ipcRenderer.removeListener('backend-status', handler)
    }
  },

  /**
   * Show a native OS notification via the main process.
   */
  notify(title: string, body: string): void {
    ipcRenderer.send('notify', title, body)
  },
})
