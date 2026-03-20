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
  let icon: Electron.NativeImage
  try {
    icon = nativeImage.createFromPath(
      path.join(app.getAppPath(), '..', 'assets', 'tray-icon.png'),
    )
  } catch {
    icon = nativeImage.createEmpty()
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
