import { Menu, Tray } from 'electron'

/**
 * Creates the system tray icon with a context menu.
 *
 * @param iconPath - Absolute path to the tray icon image.
 * @param onShow   - Called when the user selects "Show NexusPKM" or double-clicks.
 * @param onQuickChat - Called when the user selects "Quick Chat".
 * @param onQuit   - Called when the user selects "Quit".
 */
export function createTray(
  iconPath: string,
  onShow: () => void,
  onQuickChat: () => void,
  onQuit: () => void,
): Tray {
  const tray = new Tray(iconPath)
  tray.setToolTip('NexusPKM')

  const menu = Menu.buildFromTemplate([
    { label: 'Show NexusPKM', click: onShow },
    { label: 'Quick Chat', click: onQuickChat },
    { type: 'separator' },
    { label: 'Quit', click: onQuit },
  ])
  tray.setContextMenu(menu)
  tray.on('double-click', onShow)

  return tray
}
