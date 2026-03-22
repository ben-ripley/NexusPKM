import type { BrowserWindow } from 'electron'

/**
 * Attaches a `close` event listener that hides the window instead of
 * closing it when the `closeToTray` preference is enabled.
 *
 * Both getters are re-evaluated on every close event so preference changes
 * and shutdown state take effect immediately without re-registering.
 *
 * @param getIsShuttingDown - Returns true when the app is in the process of
 *   quitting. The hide-to-tray behaviour is suppressed during shutdown so that
 *   "Quit" from the tray menu (or any other quit path) is not blocked.
 */
export function setupCloseToTray(
  win: BrowserWindow,
  getCloseToTray: () => boolean,
  getIsShuttingDown: () => boolean,
): void {
  win.on('close', (event) => {
    if (!getIsShuttingDown() && getCloseToTray()) {
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
