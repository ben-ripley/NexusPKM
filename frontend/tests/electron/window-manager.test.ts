// @vitest-environment node

import { describe, expect, it, vi } from 'vitest'
import { setupCloseToTray, showAndFocusWindow } from '../../electron/window-manager'

type CloseEvent = { preventDefault: ReturnType<typeof vi.fn> }

function makeMockWindow() {
  const closeHandlers: ((e: CloseEvent) => void)[] = []
  const win = {
    on: vi.fn((event: string, handler: (e: CloseEvent) => void) => {
      if (event === 'close') closeHandlers.push(handler)
    }),
    hide: vi.fn(),
    show: vi.fn(),
    focus: vi.fn(),
    restore: vi.fn(),
    isMinimized: vi.fn().mockReturnValue(false),
    triggerClose(): ReturnType<typeof vi.fn> {
      const preventDefault = vi.fn()
      for (const handler of closeHandlers) handler({ preventDefault })
      return preventDefault
    },
  }
  return win
}

describe('setupCloseToTray', () => {
  it('hides the window and cancels close when closeToTray is true', () => {
    const win = makeMockWindow()
    setupCloseToTray(win as never, () => true, () => false)
    const preventDefault = win.triggerClose()
    expect(win.hide).toHaveBeenCalledOnce()
    expect(preventDefault).toHaveBeenCalledOnce()
  })

  it('does not prevent close when closeToTray is false', () => {
    const win = makeMockWindow()
    setupCloseToTray(win as never, () => false, () => false)
    const preventDefault = win.triggerClose()
    expect(win.hide).not.toHaveBeenCalled()
    expect(preventDefault).not.toHaveBeenCalled()
  })

  it('does not prevent close when the app is shutting down, even if closeToTray is true', () => {
    const win = makeMockWindow()
    setupCloseToTray(win as never, () => true, () => true)
    const preventDefault = win.triggerClose()
    expect(win.hide).not.toHaveBeenCalled()
    expect(preventDefault).not.toHaveBeenCalled()
  })

  it('re-evaluates both getters on each close event', () => {
    let closeToTray = true
    let shuttingDown = false
    const win = makeMockWindow()
    setupCloseToTray(win as never, () => closeToTray, () => shuttingDown)

    win.triggerClose()
    expect(win.hide).toHaveBeenCalledTimes(1)

    shuttingDown = true
    win.triggerClose()
    expect(win.hide).toHaveBeenCalledTimes(1) // not called again during shutdown
  })
})

describe('showAndFocusWindow', () => {
  it('shows and focuses the window', () => {
    const win = makeMockWindow()
    showAndFocusWindow(win as never)
    expect(win.show).toHaveBeenCalledOnce()
    expect(win.focus).toHaveBeenCalledOnce()
  })

  it('restores a minimized window before showing it', () => {
    const win = makeMockWindow()
    win.isMinimized.mockReturnValue(true)
    showAndFocusWindow(win as never)
    // restore must be called before show
    const restoreOrder = win.restore.mock.invocationCallOrder[0]
    const showOrder = win.show.mock.invocationCallOrder[0]
    expect(restoreOrder).toBeLessThan(showOrder)
  })

  it('does not call restore when window is not minimized', () => {
    const win = makeMockWindow()
    showAndFocusWindow(win as never)
    expect(win.restore).not.toHaveBeenCalled()
  })
})
