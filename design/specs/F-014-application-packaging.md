# F-014: Application Packaging (Electron Desktop Wrapper)

**Spec Version:** 1.0
**Date:** 2026-03-22
**ADR Reference:** ADR-011

## Overview

Wrap the NexusPKM React SPA in an Electron desktop application for macOS. The Electron main process manages the FastAPI/uvicorn backend as a child process, providing a native desktop experience without requiring users to manually start any servers.

**Scope (v1):**
- macOS `.dmg` installer
- System tray, global shortcut, native notifications, auto-launch on login
- Web fallback (`npm run dev`) must continue to work unchanged — no modifications to renderer/React code

**Out of scope (v1):**
- Windows/Linux packaging (tooling supports it; activate later by uncommenting targets in electron-builder config)
- App Store distribution (requires notarization; stubs for signing env vars are provided)

## User Stories

- As a user, I want to launch NexusPKM from my Dock/Applications folder so I don't need to open a terminal
- As a user, I want the backend to start automatically and silently so I don't need to manage server processes
- As a user, I want a system tray icon so I can quickly access or quit the app
- As a user, I want a global keyboard shortcut (Cmd+Shift+K) to open NexusPKM instantly from anywhere
- As a user, I want native macOS notifications when the sync completes or new entities are discovered

## Functional Requirements

### FR-1: Electron Scaffolding

Build configuration using `electron-vite`, producing three separate bundles:
- **main** — Node.js process entry point (`frontend/electron/main/index.ts`)
- **preload** — Sandboxed bridge script (`frontend/electron/preload/index.ts`)
- **renderer** — React SPA (existing Vite config, unchanged)

**Dev mode** (`npm run electron:dev`):
- electron-vite starts the renderer Vite dev server (HMR enabled)
- Main process loads renderer from `http://localhost:5173`
- Backend spawned as child process (same as production)

**Production mode** (`npm run electron:build` / `npm run electron:dist`):
- Renderer is built to `dist/renderer/`
- Main process loads renderer from built files via `file://`
- Backend bundled/extracted alongside the Electron app

**electron-vite config** (`frontend/electron-vite.config.ts`):
```typescript
// Configures main, preload, renderer build targets
// main + preload: CommonJS output targeting Node.js
// renderer: Vite SPA build (reuses existing vite.config.ts plugins)
```

### FR-2: Backend Process Lifecycle

Managed by `frontend/electron/backend-manager.ts`:

**Startup sequence:**
1. Find the `uvicorn` executable (bundled in production; on `PATH` in development)
2. Detect an available port starting from `8000` (skip if already in use)
3. Spawn `uvicorn nexuspkm.main:app --host 127.0.0.1 --port {port}` as a child process
4. Show `splash.html` in the BrowserWindow while waiting
5. Poll `GET http://127.0.0.1:{port}/health` every 500ms
6. On healthy response: hide splash, load renderer
7. On timeout (>10s): show error dialog ("Backend failed to start. See logs for details.")

**Port conflict handling:**
- If default port `8000` is occupied, try `8001`, `8002`, up to `8010`
- If all ports are occupied, show error dialog and quit

**Graceful shutdown (on app `before-quit`):**
1. Send `SIGTERM` to the backend child process
2. Wait up to 5 seconds for clean exit
3. If still running after 5s, send `SIGKILL`
4. Allow app to quit after child process exits

**Error handling:**
- Backend crash (non-zero exit after startup): show native error notification, offer "Restart Backend" action
- Emit `backend-status` IPC events throughout: `starting | healthy | error | stopped`

### FR-3: IPC Bridge

Implemented in `frontend/electron/preload/index.ts` using `contextBridge.exposeInMainWorld`.

**Security requirements:**
- `nodeIntegration: false` (renderer has no Node.js access)
- `contextIsolation: true` (preload context is isolated from renderer)
- All renderer-to-main communication goes through the typed `window.electron` API

**Exposed API (`window.electron`):**

```typescript
interface ElectronAPI {
  // Backend status events — subscribe to lifecycle updates
  onBackendStatus(callback: (status: BackendStatus) => void): () => void;

  // Native notification
  notify(title: string, body: string): void;

  // Preferences — auto-launch and minimize-to-tray toggles
  getPreferences(): Promise<AppPreferences>;
  setPreference(key: keyof AppPreferences, value: boolean): Promise<void>;
}

type BackendStatus = 'starting' | 'healthy' | 'error' | 'stopped';

interface AppPreferences {
  autoLaunch: boolean;
  closeToTray: boolean;
}
```

IPC handlers registered in `frontend/electron/ipc-handlers.ts`:
- `ipcMain.handle('get-preferences', ...)` — reads from `electron-store` or defaults
- `ipcMain.handle('set-preference', ...)` — persists preference, applies `app.setLoginItemSettings` for `autoLaunch`
- `ipcMain.on('notify', ...)` — calls `new Notification(...)` in main process

### FR-4: Desktop Integration

#### System Tray (`frontend/electron/tray.ts`)
- Tray icon loaded from `build/icon.png` (16×16 or 22×22 for macOS menubar)
- Context menu:
  - **Show NexusPKM** — bring main window to front (`mainWindow.show()`)
  - **Quick Chat** — bring window to front and navigate to `/chat`
  - **Quit** — graceful shutdown sequence
- Double-click tray icon: show main window

#### Minimize to Tray (`frontend/electron/window-manager.ts`)
- On `window.close` event: if `closeToTray` preference is `true`, call `event.preventDefault()` + `mainWindow.hide()` instead of closing
- If `closeToTray` is `false`: normal close (app stays in Dock until Quit from tray/menu)

#### Global Keyboard Shortcut
- Register `CommandOrControl+Shift+K` via `globalShortcut.register`
- Action: if window is hidden → show and focus; if visible → hide (toggle)
- Unregistered on app `will-quit`

#### Auto-Launch on Login
- Controlled via `app.setLoginItemSettings({ openAtLogin: value })`
- Defaults to `false` on first install
- Exposed as `autoLaunch` preference via IPC bridge
- Surfaced in the Settings page (NXP-81 / F-008 FR-4)

### FR-5: Build & Distribution

**electron-builder config** (`frontend/electron-builder.config.ts`):
```typescript
// productName: "NexusPKM"
// appId: "com.nexuspkm.app"
// directories: { output: "release/" }
// mac: { target: "dmg", icon: "build/icon.icns", category: "public.app-category.productivity" }
// dmg: { contents: [ { x: 130, y: 220 }, { x: 410, y: 220, type: "link", path: "/Applications" } ] }
// Code signing: CSC_LINK / CSC_KEY_PASSWORD env vars (stubs; unsigned builds work locally)
```

**Required assets:**
- `build/icon.icns` — macOS app icon (1024×1024 source recommended)
- `build/icon.png` — tray icon (22×22 minimum)

**npm scripts** (`frontend/package.json`):
| Script | Description |
|---|---|
| `electron:dev` | `electron-vite dev` — dev mode with HMR |
| `electron:build` | `electron-vite build` — production build only |
| `electron:dist` | `electron-vite build && electron-builder` — build + package to .dmg |

**`npm run dev` (web fallback)** must remain unchanged — plain `vite` command, no Electron involved.

## Non-Functional Requirements

- Backend must respond to `/health` within 10 seconds of app launch; if not, show error dialog and offer retry/quit
- Renderer process must not have direct Node.js access (`nodeIntegration: false`, `contextIsolation: true`)
- `npm run dev` web mode must work without Electron installed
- App bundle size: < 300MB installed (Electron ~140MB + app)
- Memory: main process overhead < 50MB (renderer inherits existing React app profile)

## File Structure

All Electron source lives under `frontend/electron/` to keep it collocated with the frontend:

```
frontend/
├── electron/
│   ├── main/
│   │   └── index.ts              # Main process entry — app lifecycle, window creation
│   ├── preload/
│   │   └── index.ts              # contextBridge API exposed to renderer
│   ├── backend-manager.ts        # Spawn, health-poll, shutdown logic
│   ├── ipc-handlers.ts           # ipcMain handler registration
│   ├── splash.html               # Loading screen shown while backend starts
│   ├── tray.ts                   # System tray icon and context menu
│   └── window-manager.ts         # Show/hide, minimize-to-tray behaviour
├── electron-vite.config.ts       # electron-vite build configuration
├── electron-builder.config.ts    # electron-builder packaging configuration
├── package.json                  # Existing; electron:dev/build/dist scripts already present
└── src/                          # React SPA — unchanged from web version
build/
├── icon.icns                     # macOS app icon
└── icon.png                      # Tray icon
```

## Testing Strategy

### Unit Tests (`frontend/tests/electron/`)

**`backend-lifecycle.test.ts`** (already stubbed in codebase):
- Backend manager spawns the correct uvicorn command
- Health polling resolves when `/health` returns 200
- Health polling times out after 10s and emits `error` status
- Graceful shutdown sends SIGTERM, waits, then SIGKILL on timeout
- Port conflict detection tries next available port

**`ipc-handlers.test.ts`**:
- `get-preferences` returns defaults on first run
- `set-preference autoLaunch true` calls `app.setLoginItemSettings`
- `notify` creates a native Notification

### Build Smoke Test (CI)
- `npm run electron:build` must complete without errors (does not require packaging to .dmg)
- Validates that main, preload, and renderer bundles are produced

### Manual Verification (pre-release)
- App launches from .dmg, backend starts, renderer loads
- Global shortcut toggles window
- Tray menu: Show, Quick Chat, Quit all work
- Close window with `closeToTray: true` → app stays in tray
- `npm run dev` still opens in browser (web fallback unaffected)

## Dependencies

- **F-008** — Application shell must exist (renderer loaded by Electron is the built React SPA)
- **NXP-13** — Frontend project setup (Vite config, TypeScript config, package.json) must be in place

## Acceptance Criteria

- [ ] `frontend/electron-vite.config.ts` configures main, preload, and renderer build targets
- [ ] `npm run electron:dev` starts the app in development mode with HMR
- [ ] `npm run electron:dist` produces a macOS `.dmg` installer
- [ ] App launch: Electron main process spawns uvicorn, polls `/health`, shows renderer when healthy
- [ ] Splash/loading screen displayed while backend is starting
- [ ] Error dialog shown if backend does not become healthy within 10 seconds
- [ ] Backend receives SIGTERM on app quit; SIGKILL sent after 5-second timeout if still running
- [ ] Port conflict: next available port selected automatically (8000–8010)
- [ ] `window.electron.onBackendStatus` emits status transitions in renderer
- [ ] System tray shows icon with Show / Quick Chat / Quit menu items
- [ ] Minimize-to-tray behaviour controlled by `closeToTray` preference
- [ ] Global shortcut Cmd+Shift+K (Mac) / Ctrl+Shift+K (Windows/Linux) toggles window visibility
- [ ] Auto-launch preference persists via `app.setLoginItemSettings`
- [ ] `nodeIntegration: false` and `contextIsolation: true` enforced in BrowserWindow config
- [ ] `npm run dev` web mode works without Electron (no regression)
- [ ] All unit tests in `frontend/tests/electron/` pass
