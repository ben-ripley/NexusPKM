# ADR-011: Desktop Application Packaging

**Status:** Accepted
**Date:** 2026-03-20
**Deciders:** Project Team

## Context

NexusPKM is a local-first personal knowledge management application. During development, it runs as a web app served by Vite (frontend) and uvicorn (backend), requiring users to start both processes manually and access the app via a browser tab.

For a production-quality desktop experience, this approach has several limitations:
- Users must manually start/stop the backend server
- The app lives in a browser tab, competing with other tabs for attention
- No system tray presence, native notifications, or auto-launch on login
- No global keyboard shortcut for quick access
- The "open a terminal and run two commands" workflow feels like a developer tool, not a personal productivity app

Three options were evaluated:
- **Option A: Tauri** — Rust-based, smaller binary (~20MB), but requires Rust toolchain, limited Node.js ecosystem access, and less mature than Electron
- **Option B: Electron** — Chromium-based, larger binary (~140MB), but mature ecosystem, excellent Node.js integration, straightforward Vite integration, proven for desktop apps
- **Option C: Stay web-only** — No packaging overhead, but poor UX for a local desktop tool

## Decision

Wrap the React SPA in **Electron**. The Electron main process manages the FastAPI backend lifecycle as a child process.

### Architecture

```
┌─────────────────────────────────────────────────┐
│                  Electron App                    │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │           Main Process (Node.js)           │  │
│  │                                            │  │
│  │  - Window management                       │  │
│  │  - System tray                             │  │
│  │  - Native notifications                    │  │
│  │  - Auto-launch configuration               │  │
│  │  - Global keyboard shortcut                │  │
│  │  - Backend lifecycle management            │  │
│  │    (spawn uvicorn, health check, shutdown) │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │       Renderer Process (Chromium)          │  │
│  │                                            │  │
│  │  React SPA (unchanged from web version)    │  │
│  │  Loads http://127.0.0.1:{port}             │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │       Child Process (FastAPI/uvicorn)      │  │
│  │                                            │  │
│  │  Backend server on 127.0.0.1:{port}        │  │
│  │  Managed by main process                   │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Key Technical Choices

| Concern | Choice | Rationale |
|---|---|---|
| Build integration | electron-vite | Purpose-built for Vite + Electron, handles main/preload/renderer builds |
| Packaging | electron-builder | Mature, supports .dmg (macOS), .exe/.msi (Windows), .AppImage (Linux) |
| Backend lifecycle | Child process (spawn) | Simple, no IPC overhead, backend remains a standalone FastAPI server |
| Health monitoring | Poll `/health` endpoint | Reuses existing health endpoint, no custom IPC needed |
| IPC | contextBridge + preload | Secure pattern for renderer-to-main communication |

### Backend Lifecycle

1. **App launch**: Main process spawns `uvicorn nexuspkm.main:app` as a child process
2. **Health polling**: Main process polls `GET /health` until backend is ready (show splash/loading screen)
3. **Window load**: Once healthy, renderer loads `http://127.0.0.1:{port}`
4. **Port conflict**: If the default port is in use, detect and show a user-friendly error
5. **Graceful shutdown**: On app quit, send SIGTERM to backend child process, wait for exit, then force-kill after timeout

## Consequences

### Positive
- Native desktop presence: Dock icon, system tray, window management
- Auto-launch on login for always-available knowledge access
- Global keyboard shortcut (Cmd+Shift+K) for instant access
- Native notifications for sync events and entity discoveries
- Backend lifecycle is transparent to the user — no manual server management
- React SPA code is unchanged — web fallback preserved (`npm run dev` still works)
- Mature ecosystem with extensive documentation and community support

### Negative
- Adds ~140MB to the distributable (Chromium + Node.js runtime)
- Electron updates require attention for security patches (Chromium CVEs)
- macOS code signing and notarization required for distribution outside the App Store
- Additional build complexity (electron-builder configuration)

### Risks
- Backend startup time may add perceived latency — mitigate with a splash/loading screen
- Port conflicts with other local services — mitigate with detection and configurable port
- Electron security: renderer process must not have direct Node.js access — enforce via contextBridge/preload pattern
