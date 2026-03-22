import { BrowserWindow, ipcMain, Notification } from 'electron'
import { sanitizeNotification, type BackendStatus } from './notification-utils'

let currentBackendStatus: BackendStatus = 'starting'

/**
 * Sends a backend lifecycle status event to all live renderer windows and
 * caches the status so renderers that load later can query it via
 * the `get-backend-status` handle.
 */
export function broadcastBackendStatus(status: BackendStatus): void {
  currentBackendStatus = status
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed() && !win.webContents.isDestroyed()) {
      win.webContents.send('backend-status', status)
    }
  }
}

/**
 * Registers the IPC handles and listeners that bridge the main process
 * and renderer.  Call once inside `app.whenReady()`.
 */
export function registerIpcHandlers(): void {
  // Renderer can call this on mount to get current status without missing
  // broadcasts that fired before the renderer was ready.
  ipcMain.handle('get-backend-status', () => currentBackendStatus)

  // Sanitise inputs from the untrusted renderer context before passing to
  // the OS notification daemon.
  ipcMain.on('notify', (_event, title: unknown, body: unknown) => {
    const params = sanitizeNotification(title, body)
    if (params === null) return
    if (Notification.isSupported()) {
      const notification = new Notification({ title: params.title, body: params.body })
      notification.show()
    }
  })
}
