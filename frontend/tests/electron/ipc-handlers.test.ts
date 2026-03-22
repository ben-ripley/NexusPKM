// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from 'vitest'

// vi.hoisted runs before all imports (including vi.mock factories), ensuring
// these mocks are initialised before electron is resolved.
const mocks = vi.hoisted(() => {
  const notificationShow = vi.fn()
  // Must use a regular function (not arrow) so the mock can be called with 'new'.
  // The constructor sets .show on `this`, which ipc-handlers.ts then calls.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const NotificationCtor: any = vi.fn(function (this: any) {
    this.show = notificationShow
  })
  NotificationCtor.isSupported = vi.fn().mockReturnValue(true)

  return {
    getAllWindows: vi.fn(),
    handle: vi.fn(),
    on: vi.fn(),
    notificationShow,
    NotificationCtor,
  }
})

vi.mock('electron', () => ({
  BrowserWindow: { getAllWindows: mocks.getAllWindows },
  ipcMain: { handle: mocks.handle, on: mocks.on },
  Notification: mocks.NotificationCtor,
}))

import { broadcastBackendStatus, registerIpcHandlers } from '../../electron/ipc-handlers'

// ---- helpers ----

function makeMockWindow(destroyed = false, webContentsDestroyed = false) {
  const send = vi.fn()
  return {
    isDestroyed: vi.fn().mockReturnValue(destroyed),
    webContents: { isDestroyed: vi.fn().mockReturnValue(webContentsDestroyed), send },
    send, // convenience ref for assertions
  }
}

// ---- broadcastBackendStatus ----

describe('broadcastBackendStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getAllWindows.mockReturnValue([makeMockWindow()])
  })

  it('sends backend-status event to all live windows', () => {
    const win = makeMockWindow()
    mocks.getAllWindows.mockReturnValue([win])
    broadcastBackendStatus('healthy')
    expect(win.webContents.send).toHaveBeenCalledWith('backend-status', 'healthy')
  })

  it('skips windows whose BrowserWindow is destroyed', () => {
    const win = makeMockWindow(true)
    mocks.getAllWindows.mockReturnValue([win])
    broadcastBackendStatus('healthy')
    expect(win.webContents.send).not.toHaveBeenCalled()
  })

  it('skips windows whose webContents are destroyed', () => {
    const win = makeMockWindow(false, true)
    mocks.getAllWindows.mockReturnValue([win])
    broadcastBackendStatus('healthy')
    expect(win.webContents.send).not.toHaveBeenCalled()
  })

  it('sends only to live windows when some are destroyed', () => {
    const liveWin = makeMockWindow(false)
    const deadWin = makeMockWindow(true)
    mocks.getAllWindows.mockReturnValue([deadWin, liveWin])
    broadcastBackendStatus('stopped')
    expect(liveWin.webContents.send).toHaveBeenCalledWith('backend-status', 'stopped')
    expect(deadWin.webContents.send).not.toHaveBeenCalled()
  })
})

// ---- registerIpcHandlers — get-backend-status ----

describe('registerIpcHandlers — get-backend-status', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getAllWindows.mockReturnValue([])
    registerIpcHandlers()
  })

  it('registers the get-backend-status handle', () => {
    expect(mocks.handle).toHaveBeenCalledWith('get-backend-status', expect.any(Function))
  })

  it('handle returns the current cached backend status', () => {
    broadcastBackendStatus('healthy')
    const handler = mocks.handle.mock.calls[0][1] as () => string
    expect(handler()).toBe('healthy')
  })

  it('handle reflects subsequent status transitions', () => {
    broadcastBackendStatus('error')
    const handler = mocks.handle.mock.calls[0][1] as () => string
    expect(handler()).toBe('error')

    broadcastBackendStatus('stopped')
    expect(handler()).toBe('stopped')
  })
})

// ---- registerIpcHandlers — notify ----

describe('registerIpcHandlers — notify', () => {
  type NotifyHandler = (event: unknown, title: unknown, body: unknown) => void
  let notifyHandler: NotifyHandler

  beforeEach(() => {
    vi.clearAllMocks()
    mocks.NotificationCtor.isSupported.mockReturnValue(true)
    mocks.getAllWindows.mockReturnValue([])
    registerIpcHandlers()
    notifyHandler = mocks.on.mock.calls[0][1] as NotifyHandler
  })

  it('registers the notify listener', () => {
    expect(mocks.on).toHaveBeenCalledWith('notify', expect.any(Function))
  })

  it('creates and shows a Notification for valid string params', () => {
    notifyHandler({}, 'Hello', 'World')
    expect(mocks.NotificationCtor).toHaveBeenCalledWith({ title: 'Hello', body: 'World' })
    expect(mocks.notificationShow).toHaveBeenCalled()
  })

  it('truncates long title and body before creating the Notification', () => {
    notifyHandler({}, 'a'.repeat(100), 'b'.repeat(400))
    expect(mocks.NotificationCtor).toHaveBeenCalledWith({
      title: 'a'.repeat(64),
      body: 'b'.repeat(256),
    })
  })

  it('drops the request silently when title is not a string', () => {
    notifyHandler({}, 42, 'body')
    expect(mocks.NotificationCtor).not.toHaveBeenCalled()
  })

  it('drops the request silently when body is not a string', () => {
    notifyHandler({}, 'title', null)
    expect(mocks.NotificationCtor).not.toHaveBeenCalled()
  })

  it('does nothing when Notification.isSupported() returns false', () => {
    mocks.NotificationCtor.isSupported.mockReturnValue(false)
    notifyHandler({}, 'title', 'body')
    expect(mocks.NotificationCtor).not.toHaveBeenCalled()
  })
})
