import type { BrowserWindow } from 'electron'

/**
 * Attaches a `close` event listener that hides the window instead of
 * closing it when the `closeToTray` preference is enabled.
 *
 * The getter is re-evaluated on every close event so preference changes
 * take effect immediately without re-registering the listener.
 */
export function setupCloseToTray(
  win: BrowserWindow,
  getCloseToTray: () => boolean,
): void {
  win.on('close', (event) => {
    if (getCloseToTray()) {
      event.preventDefault()
      win.hide()
    }
  })
}

/**
 * Brings a window to the foreground, restoring it from a minimised state
 * if necessary.
 */
export function showAndFocusWindow(win: BrowserWindow): void {
  if (win.isMinimized()) win.restore()
  win.show()
  win.focus()
}
