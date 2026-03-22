import { app, BrowserWindow, ipcMain, Notification } from 'electron'
import { sanitizeNotification, type BackendStatus } from './notification-utils'
import { loadPreferences, savePreferences, type AppPreferences } from './preferences'

let currentBackendStatus: BackendStatus = 'starting'
let preferencesCache: AppPreferences | null = null

const VALID_PREFERENCE_KEYS: readonly (keyof AppPreferences)[] = ['autoLaunch', 'closeToTray']

function getPreferencesFromCache(): AppPreferences {
  if (preferencesCache === null) {
    preferencesCache = loadPreferences(app.getPath('userData'))
  }
  return preferencesCache
}

/**
 * Returns the current in-memory preferences (loading from disk on first call).
 * Use this in main.ts to read preferences without going through IPC.
 */
export function getCurrentPreferences(): AppPreferences {
  return getPreferencesFromCache()
}

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
 *
 * Safe to call more than once — existing registrations for these channels
 * are removed before re-registering to avoid duplicate-handler errors.
 */
export function registerIpcHandlers(): void {
  // Remove any previous registrations so this function is idempotent.
  ipcMain.removeHandler('get-backend-status')
  ipcMain.removeHandler('get-preferences')
  ipcMain.removeHandler('set-preference')
  ipcMain.removeAllListeners('notify')

  // Renderer can call this on mount to get current status without missing
  // broadcasts that fired before the renderer was ready.
  ipcMain.handle('get-backend-status', () => currentBackendStatus)

  ipcMain.handle('get-preferences', () => getPreferencesFromCache())

  ipcMain.handle('set-preference', (_event, key: unknown, value: unknown) => {
    if (typeof key !== 'string' || typeof value !== 'boolean') return
    if (!VALID_PREFERENCE_KEYS.includes(key as keyof AppPreferences)) return
    const updated: AppPreferences = { ...getPreferencesFromCache(), [key]: value }
    savePreferences(app.getPath('userData'), updated)
    preferencesCache = updated
    if (key === 'autoLaunch') {
      app.setLoginItemSettings({ openAtLogin: value })
    }
  })

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

/**
 * Reset module state to initial values.
 * @internal For use in test files only — must not be imported in production code.
 */
export function _resetForTesting(): void {
  currentBackendStatus = 'starting'
  preferencesCache = null
}
