import { app, BrowserWindow, ipcMain, Notification } from 'electron'
import {
  sanitizeNotification,
  DEFAULT_PREFERENCES,
  type BackendStatus,
  type AppPreferences,
} from './notification-utils'
import { loadPreferences, savePreferences } from './preferences'

let currentBackendStatus: BackendStatus = 'starting'
let preferencesCache: AppPreferences | null = null

const VALID_PREFERENCE_KEYS: readonly (keyof AppPreferences)[] = ['autoLaunch', 'closeToTray']

async function getPreferencesFromCache(): Promise<AppPreferences> {
  if (preferencesCache === null) {
    preferencesCache = await loadPreferences(app.getPath('userData'))
  }
  return preferencesCache
}

/**
 * Returns the current in-memory preferences, or defaults if not yet loaded.
 * Preferences are pre-loaded during startup via initPreferences(), so this
 * will return the correct value in all normal operation paths.
 */
export function getCurrentPreferences(): AppPreferences {
  return preferencesCache ?? DEFAULT_PREFERENCES
}

/**
 * Pre-loads preferences from disk into the in-memory cache.
 * Call once after registerIpcHandlers() during app startup so that
 * getCurrentPreferences() returns the persisted values before the first
 * IPC call arrives.
 */
export async function initPreferences(): Promise<void> {
  await getPreferencesFromCache()
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

  ipcMain.handle('set-preference', async (_event, key: unknown, value: unknown) => {
    if (typeof key !== 'string' || typeof value !== 'boolean') return
    if (!VALID_PREFERENCE_KEYS.includes(key as keyof AppPreferences)) return
    const current = await getPreferencesFromCache()
    const updated: AppPreferences = { ...current, [key]: value }
    // Save to disk first; only update the in-memory cache if the write succeeds
    // to keep the cache consistent with the persisted state.
    const saved = await savePreferences(app.getPath('userData'), updated)
    if (saved) {
      preferencesCache = updated
      // Keep the OS login-item in sync whenever autoLaunch or closeToTray changes.
      // openAsHidden ensures the app starts silently in the tray (macOS) when
      // both autoLaunch and closeToTray are enabled.
      if (key === 'autoLaunch' || key === 'closeToTray') {
        app.setLoginItemSettings({
          openAtLogin: updated.autoLaunch,
          openAsHidden: updated.autoLaunch && updated.closeToTray,
        })
      }
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
