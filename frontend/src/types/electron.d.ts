/**
 * Global type declaration for the contextBridge API exposed by the Electron preload script.
 * When running as a web app (npm run dev), window.electron is undefined.
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

  /** Show a native OS notification. */
  notify(title: string, body: string): void
}

declare global {
  interface Window {
    /** Defined only when running inside Electron. */
    electron?: ElectronAPI
  }
}

export {}
