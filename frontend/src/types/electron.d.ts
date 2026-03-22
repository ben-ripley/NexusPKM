/**
 * Global type declaration for the contextBridge API exposed by the Electron preload script.
 * When running as a web app (npm run dev), window.electron is undefined.
 *
 * BackendStatus and AppPreferences are imported from their canonical definitions
 * in electron/ so this declaration stays in sync automatically.
 */

import type { BackendStatus } from '../../electron/notification-utils'
import type { AppPreferences } from '../../electron/preferences'

interface ElectronAPI {
  /** The OS platform string (e.g. 'darwin', 'win32'). */
  readonly platform: string

  /**
   * Subscribe to backend lifecycle status changes.
   * Returns a cleanup function that unsubscribes the listener.
   */
  readonly onBackendStatus: (callback: (status: BackendStatus) => void) => () => void

  /**
   * Query the current backend status. Use this on component mount to get
   * the initial state without missing events that fired before render.
   */
  readonly getBackendStatus: () => Promise<BackendStatus>

  /** Show a native OS notification. Fire-and-forget. */
  readonly notify: (title: string, body: string) => void

  /** Retrieve persisted user preferences. */
  readonly getPreferences: () => Promise<AppPreferences>

  /** Persist a single preference change. */
  readonly setPreference: (key: keyof AppPreferences, value: boolean) => Promise<void>

  /**
   * Subscribe to navigation requests from the main process (e.g. tray Quick Chat).
   * Returns a cleanup function that removes the listener.
   */
  readonly onNavigate: (callback: (path: string) => void) => () => void
}

declare global {
  interface Window {
    /** Defined only when running inside Electron. */
    electron?: ElectronAPI
  }
}

export {}
