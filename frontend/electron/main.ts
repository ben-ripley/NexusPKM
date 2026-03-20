import { app, BrowserWindow, dialog, globalShortcut, ipcMain } from 'electron'
import { spawn, type ChildProcess } from 'child_process'
import path from 'path'
import { isPortInUse, waitForHealth } from './backend-lifecycle'
import { createTray, destroyTray } from './tray'
import { showEntityNotification, showSyncNotification } from './notifications'

const rawPort = parseInt(process.env['NEXUSPKM_BACKEND_PORT'] ?? '8000', 10)
const BACKEND_PORT = Number.isFinite(rawPort) && rawPort > 0 ? rawPort : 8000
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/health`
const BACKEND_TIMEOUT_MS = 30_000
const BACKEND_TIMEOUT_S = BACKEND_TIMEOUT_MS / 1000

let backendProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let isShuttingDown = false
let minimizeToTray = false

function getPreloadPath(): string {
  return path.join(__dirname, '../preload/index.js')
}

function showOrCreateMainWindow(): void {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  } else if (backendProcess !== null) {
    mainWindow = createMainWindow()
    mainWindow.show()
    mainWindow.on('closed', () => {
      mainWindow = null
    })
  }
}

async function createSplashWindow(): Promise<BrowserWindow> {
  const splash = new BrowserWindow({
    width: 400,
    height: 200,
    frame: false,
    resizable: false,
    center: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  })

  const splashHtml = `data:text/html,<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><style>
body{margin:0;background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif;
display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;gap:16px}
h2{font-size:1.25rem;font-weight:600;margin:0}
.dot{animation:blink 1s infinite}.dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,100%{opacity:.2}50%{opacity:1}}
</style></head>
<body><h2>NexusPKM</h2><div>Starting<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></div></body>
</html>`

  await splash.loadURL(splashHtml)
  splash.show()
  return splash
}

function createMainWindow(): BrowserWindow {
  const preload = getPreloadPath()
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload,
    },
  })

  // Minimize to tray on close if the setting is enabled
  win.on('close', (event) => {
    if (minimizeToTray && !isShuttingDown) {
      event.preventDefault()
      win.hide()
    }
  })

  const devServerUrl = process.env['MAIN_WINDOW_VITE_DEV_SERVER_URL']
  const targetUrl = devServerUrl ?? `http://127.0.0.1:${BACKEND_PORT}`
  win.loadURL(targetUrl).catch((err: unknown) => {
    process.stderr.write(`[main] Failed to load URL ${targetUrl}: ${String(err)}\n`)
  })

  return win
}

function spawnBackend(): ChildProcess {
  const backendDir =
    process.env['NEXUSPKM_BACKEND_DIR'] ??
    path.join(app.getAppPath(), '..', 'backend')

  const isDev = !app.isPackaged
  const cmd = isDev ? 'uv' : 'uvicorn'
  const args = isDev
    ? ['run', 'uvicorn', 'nexuspkm.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)]
    : ['nexuspkm.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)]

  const proc = spawn(cmd, args, {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  })

  proc.stdout?.on('data', (data: Buffer) => {
    process.stdout.write(`[backend] ${data.toString()}`)
  })
  proc.stderr?.on('data', (data: Buffer) => {
    process.stderr.write(`[backend] ${data.toString()}`)
  })

  return proc
}

async function shutdownBackend(): Promise<void> {
  if (!backendProcess) return

  try {
    backendProcess.kill('SIGTERM')
  } catch {
    // Process already exited; nothing to do
    backendProcess = null
    return
  }

  await new Promise<void>((resolve) => {
    const timeout = setTimeout(() => {
      try {
        backendProcess?.kill('SIGKILL')
      } catch {
        // Already gone
      }
      resolve()
    }, 5000)

    backendProcess!.once('exit', () => {
      clearTimeout(timeout)
      resolve()
    })
  })

  backendProcess = null
}

function setupIpc(): void {
  // Allow renderer to send sync/entity notification events
  ipcMain.on('notify:sync', (_event, source: string, count: number) => {
    showSyncNotification({ source, count })
  })
  ipcMain.on('notify:entity', (_event, entityName: string, relationshipCount: number) => {
    showEntityNotification({ entityName, relationshipCount })
  })
  // Allow renderer to toggle minimize-to-tray behaviour
  ipcMain.on('settings:minimize-to-tray', (_event, enabled: boolean) => {
    minimizeToTray = enabled
  })
  // Allow renderer to enable/disable auto-launch on login
  ipcMain.on('settings:auto-launch', (_event, enabled: boolean) => {
    app.setLoginItemSettings({ openAtLogin: enabled })
  })
}

app
  .whenReady()
  .then(async () => {
    app.setLoginItemSettings({ openAtLogin: false }) // default off; renderer can enable via IPC

    const inUse = await isPortInUse(BACKEND_PORT)
    if (inUse) {
      await dialog.showMessageBox({
        type: 'error',
        title: 'Port Conflict',
        message: `Port ${BACKEND_PORT} is already in use.\n\nAnother instance of NexusPKM may already be running.`,
        buttons: ['OK'],
      })
      app.quit()
      return
    }

    const splash = await createSplashWindow()
    backendProcess = spawnBackend()

    try {
      await waitForHealth(HEALTH_URL, BACKEND_TIMEOUT_MS)
    } catch {
      splash.close()
      await dialog.showMessageBox({
        type: 'error',
        title: 'Backend Startup Failed',
        message: `NexusPKM backend failed to start within ${BACKEND_TIMEOUT_S} seconds.`,
        buttons: ['Quit'],
      })
      app.quit()
      return
    }

    setupIpc()

    createTray({
      onShow: showOrCreateMainWindow,
      onQuickChat: () => {
        showOrCreateMainWindow()
        mainWindow?.webContents.executeJavaScript('window.location.hash = "#/chat"').catch(() => {})
      },
    })

    globalShortcut.register('CommandOrControl+Shift+K', showOrCreateMainWindow)

    // Notify user if backend crashes after a successful startup
    backendProcess.on('exit', (code) => {
      if (!isShuttingDown) {
        process.stderr.write(`[main] Backend exited unexpectedly (code ${String(code)})\n`)
        dialog
          .showMessageBox({
            type: 'error',
            title: 'Backend Stopped',
            message: 'The NexusPKM backend stopped unexpectedly. The app will quit.',
            buttons: ['OK'],
          })
          .then(() => app.quit())
          .catch(() => app.quit())
      }
    })

    mainWindow = createMainWindow()
    mainWindow.once('ready-to-show', () => {
      splash.close()
      mainWindow?.show()
    })
    mainWindow.on('closed', () => {
      mainWindow = null
    })
  })
  .catch((err: unknown) => {
    process.stderr.write(`[main] Startup error: ${String(err)}\n`)
    app.quit()
  })

app.on('before-quit', (event) => {
  if (!isShuttingDown && backendProcess !== null) {
    event.preventDefault()
    isShuttingDown = true
    globalShortcut.unregisterAll()
    destroyTray()
    shutdownBackend()
      .then(() => app.quit())
      .catch(() => app.quit())
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  // On macOS, re-open window only if backend is still running
  if (BrowserWindow.getAllWindows().length === 0 && backendProcess !== null) {
    showOrCreateMainWindow()
  }
})
