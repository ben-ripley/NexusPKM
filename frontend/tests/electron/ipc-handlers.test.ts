// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from 'vitest'

// vi.hoisted runs before all imports (including vi.mock factories), ensuring
// these mocks are initialised before electron is resolved.
const mocks = vi.hoisted(() => {
  const notificationShow = vi.fn()

  // Must use a regular function (not arrow) so the mock can be called with
  // `new`.  The constructor sets .show on `this`, which ipc-handlers calls.
  type NotificationInstance = { show: () => void }
  type NotificationLike = {
    new (opts: { title: string; body: string }): NotificationInstance
    isSupported: ReturnType<typeof vi.fn>
  }
  const NotificationCtor = vi.fn(function (this: NotificationInstance) {
    this.show = notificationShow
  }) as unknown as NotificationLike
  NotificationCtor.isSupported = vi.fn().mockReturnValue(true)

  return {
    getAllWindows: vi.fn(),
    handle: vi.fn(),
    on: vi.fn(),
    removeHandler: vi.fn(),
    removeAllListeners: vi.fn(),
    notificationShow,
    NotificationCtor,
  }
})

vi.mock('electron', () => ({
  BrowserWindow: { getAllWindows: mocks.getAllWindows },
  ipcMain: {
    handle: mocks.handle,
    on: mocks.on,
    removeHandler: mocks.removeHandler,
    removeAllListeners: mocks.removeAllListeners,
  },
  Notification: mocks.NotificationCtor,
}))

import {
  _resetForTesting,
  broadcastBackendStatus,
  registerIpcHandlers,
} from '../../electron/ipc-handlers'

// ---- helpers ----

function makeMockWindow(destroyed = false, webContentsDestroyed = false) {
  const send = vi.fn()
  return {
    isDestroyed: vi.fn().mockReturnValue(destroyed),
    webContents: { isDestroyed: vi.fn().mockReturnValue(webContentsDestroyed), send },
  }
}

// ---- broadcastBackendStatus ----

describe('broadcastBackendStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetForTesting()
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
    _resetForTesting()
    mocks.getAllWindows.mockReturnValue([])
    registerIpcHandlers()
  })

  it('removes any previous handler before registering', () => {
    expect(mocks.removeHandler).toHaveBeenCalledWith('get-backend-status')
  })

  it('registers the get-backend-status handle', () => {
    expect(mocks.handle).toHaveBeenCalledWith('get-backend-status', expect.any(Function))
  })

  it('handle returns starting as the default before any broadcast', () => {
    const handler = mocks.handle.mock.calls.find(
      (args: unknown[]) => args[0] === 'get-backend-status',
    )?.[1] as (() => string) | undefined
    expect(handler?.()).toBe('starting')
  })

  it('handle returns the current cached backend status after a broadcast', () => {
    broadcastBackendStatus('healthy')
    const handler = mocks.handle.mock.calls.find(
      (args: unknown[]) => args[0] === 'get-backend-status',
    )?.[1] as (() => string) | undefined
    expect(handler?.()).toBe('healthy')
  })

  it('handle reflects subsequent status transitions', () => {
    const handler = mocks.handle.mock.calls.find(
      (args: unknown[]) => args[0] === 'get-backend-status',
    )?.[1] as (() => string) | undefined
    broadcastBackendStatus('error')
    expect(handler?.()).toBe('error')
    broadcastBackendStatus('stopped')
    expect(handler?.()).toBe('stopped')
  })
})

// ---- registerIpcHandlers — notify ----

describe('registerIpcHandlers — notify', () => {
  type NotifyHandler = (event: unknown, title: unknown, body: unknown) => void

  function getNotifyHandler(): NotifyHandler {
    const entry = mocks.on.mock.calls.find((args: unknown[]) => args[0] === 'notify')
    return entry?.[1] as NotifyHandler
  }

  beforeEach(() => {
    vi.clearAllMocks()
    _resetForTesting()
    mocks.NotificationCtor.isSupported.mockReturnValue(true)
    mocks.getAllWindows.mockReturnValue([])
    registerIpcHandlers()
  })

  it('removes previous listeners before registering', () => {
    expect(mocks.removeAllListeners).toHaveBeenCalledWith('notify')
  })

  it('registers the notify listener', () => {
    expect(mocks.on).toHaveBeenCalledWith('notify', expect.any(Function))
  })

  it('creates and shows a Notification for valid string params', () => {
    getNotifyHandler()({}, 'Hello', 'World')
    expect(mocks.NotificationCtor).toHaveBeenCalledWith({ title: 'Hello', body: 'World' })
    expect(mocks.notificationShow).toHaveBeenCalled()
  })

  it('truncates long title and body before creating the Notification', () => {
    getNotifyHandler()({}, 'a'.repeat(100), 'b'.repeat(400))
    expect(mocks.NotificationCtor).toHaveBeenCalledWith({
      title: 'a'.repeat(64),
      body: 'b'.repeat(256),
    })
  })

  it('drops the request silently when title is not a string', () => {
    getNotifyHandler()({}, 42, 'body')
    expect(mocks.NotificationCtor).not.toHaveBeenCalled()
  })

  it('drops the request silently when body is not a string', () => {
    getNotifyHandler()({}, 'title', null)
    expect(mocks.NotificationCtor).not.toHaveBeenCalled()
  })

  it('does nothing when Notification.isSupported() returns false', () => {
    mocks.NotificationCtor.isSupported.mockReturnValue(false)
    getNotifyHandler()({}, 'title', 'body')
    expect(mocks.NotificationCtor).not.toHaveBeenCalled()
  })
})
