import { app, Menu, nativeImage, Tray, type MenuItemConstructorOptions } from 'electron'
import path from 'path'

let tray: Tray | null = null

export interface TrayCallbacks {
  onShow: () => void
  onQuickChat: () => void
}

export function buildTrayMenuTemplate(callbacks: TrayCallbacks): MenuItemConstructorOptions[] {
  return [
    {
      label: 'Show NexusPKM',
      click: () => callbacks.onShow(),
    },
    {
      label: 'Quick Chat',
      click: () => callbacks.onQuickChat(),
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => app.quit(),
    },
  ]
}

export function createTray(callbacks: TrayCallbacks): Tray {
  // createFromPath returns an empty image (not an exception) when the file is missing
  const icon = nativeImage.createFromPath(
    path.join(app.getAppPath(), '..', 'assets', 'tray-icon.png'),
  )
  if (icon.isEmpty()) {
    process.stderr.write(
      '[tray] Warning: tray-icon.png not found — tray icon will be blank. ' +
        'Add assets/tray-icon.png to fix this.\n',
    )
  }

  tray = new Tray(icon)
  tray.setToolTip('NexusPKM')

  const menu = Menu.buildFromTemplate(buildTrayMenuTemplate(callbacks))
  tray.setContextMenu(menu)

  return tray
}

export function destroyTray(): void {
  tray?.destroy()
  tray = null
}
