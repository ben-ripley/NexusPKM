import { app, BrowserWindow, dialog } from 'electron'
import { spawn, type ChildProcess } from 'child_process'
import path from 'path'
import { isPortInUse, waitForHealth } from './backend-lifecycle'
import { broadcastBackendStatus, registerIpcHandlers } from './ipc-handlers'

const BACKEND_PORT = parseInt(process.env['NEXUSPKM_BACKEND_PORT'] ?? '8000', 10)
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/health`
const BACKEND_TIMEOUT_MS = 10_000
const BACKEND_TIMEOUT_S = BACKEND_TIMEOUT_MS / 1000

let backendProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let isShuttingDown = false

function getPreloadPath(): string {
  return path.join(__dirname, '../preload/index.js')
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

  const devServerUrl = process.env['MAIN_WINDOW_VITE_DEV_SERVER_URL']
  // In production the FastAPI backend serves the compiled React bundle at its root (ADR-011).
  // In development electron-vite sets MAIN_WINDOW_VITE_DEV_SERVER_URL to the Vite dev server.
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

  // Notify renderer if the backend exits unexpectedly after startup.
  // The isShuttingDown guard suppresses the broadcast for intentional quits
  // (the once listener is still invoked, but the side-effects are skipped).
  proc.once('exit', (code) => {
    if (!isShuttingDown) {
      process.stderr.write(`[main] Backend exited unexpectedly with code ${String(code)}\n`)
      backendProcess = null
      broadcastBackendStatus('stopped')
    }
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

app
  .whenReady()
  .then(async () => {
    registerIpcHandlers()

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
    // Status cached as 'starting'; broadcast goes to zero renderer windows
    // at this point (only splash is open and has no IPC listener).
    // Renderers that load later query current status via get-backend-status.
    broadcastBackendStatus('starting')

    try {
      await waitForHealth(HEALTH_URL, BACKEND_TIMEOUT_MS)
    } catch {
      broadcastBackendStatus('error')
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

    mainWindow = createMainWindow()
    mainWindow.once('ready-to-show', () => {
      splash.close()
      mainWindow?.show()
      broadcastBackendStatus('healthy')
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
    mainWindow = createMainWindow()
    mainWindow.show()
    mainWindow.on('closed', () => {
      mainWindow = null
    })
  }
})
