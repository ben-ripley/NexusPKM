/**
 * Global type declaration for the contextBridge API exposed by the Electron preload script.
 * When running as a web app (npm run dev), window.electron is undefined.
 *
 * BackendStatus mirrors the canonical definition in electron/notification-utils.ts.
 */

type BackendStatus = 'starting' | 'healthy' | 'error' | 'stopped'

interface ElectronAPI {
  /** The OS platform string (e.g. 'darwin', 'win32'). */
  readonly platform: string

  /**
   * Subscribe to backend lifecycle status changes.
   * Returns a cleanup function that unsubscribes the listener.
   */
  onBackendStatus(callback: (status: BackendStatus) => void): () => void

  /**
   * Query the current backend status. Use this on component mount to get
   * the initial state without missing events that fired before render.
   */
  getBackendStatus(): Promise<BackendStatus>

  /** Show a native OS notification. Fire-and-forget. */
  notify(title: string, body: string): void
}

declare global {
  interface Window {
    /** Defined only when running inside Electron. */
    electron?: ElectronAPI
  }
}

export {}
