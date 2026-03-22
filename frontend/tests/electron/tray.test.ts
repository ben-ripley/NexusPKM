// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const setToolTip = vi.fn()
  const setContextMenu = vi.fn()
  const on = vi.fn()

  type TrayInstance = { setToolTip: typeof setToolTip; setContextMenu: typeof setContextMenu; on: typeof on }

  const TrayConstructor = vi.fn(function (this: TrayInstance) {
    this.setToolTip = setToolTip
    this.setContextMenu = setContextMenu
    this.on = on
  }) as unknown as new (iconPath: string) => TrayInstance

  return {
    setToolTip,
    setContextMenu,
    on,
    TrayConstructor,
    buildFromTemplate: vi.fn(),
  }
})

vi.mock('electron', () => ({
  Tray: mocks.TrayConstructor,
  Menu: { buildFromTemplate: mocks.buildFromTemplate },
}))

import { createTray } from '../../electron/tray'

describe('createTray', () => {
  const onShow = vi.fn()
  const onQuickChat = vi.fn()
  const onQuit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mocks.buildFromTemplate.mockReturnValue('built-menu')
  })

  it('creates a Tray with the given icon path', () => {
    createTray('/path/to/icon.png', onShow, onQuickChat, onQuit)
    expect(mocks.TrayConstructor).toHaveBeenCalledWith('/path/to/icon.png')
  })

  it('sets tooltip to NexusPKM', () => {
    createTray('/icon.png', onShow, onQuickChat, onQuit)
    expect(mocks.setToolTip).toHaveBeenCalledWith('NexusPKM')
  })

  it('attaches the built context menu', () => {
    createTray('/icon.png', onShow, onQuickChat, onQuit)
    expect(mocks.setContextMenu).toHaveBeenCalledWith('built-menu')
  })

  it('builds a menu with Show NexusPKM, Quick Chat, separator, and Quit items', () => {
    createTray('/icon.png', onShow, onQuickChat, onQuit)
    const template: { label?: string; type?: string }[] = mocks.buildFromTemplate.mock
      .calls[0][0] as { label?: string; type?: string }[]
    expect(template[0].label).toBe('Show NexusPKM')
    expect(template[1].label).toBe('Quick Chat')
    expect(template[2].type).toBe('separator')
    expect(template[3].label).toBe('Quit')
  })

  it('registers double-click handler to call onShow', () => {
    createTray('/icon.png', onShow, onQuickChat, onQuit)
    expect(mocks.on).toHaveBeenCalledWith('double-click', onShow)
  })

  it('calls onShow when Show NexusPKM is clicked', () => {
    createTray('/icon.png', onShow, onQuickChat, onQuit)
    const template = mocks.buildFromTemplate.mock.calls[0][0] as { click: () => void }[]
    template[0].click()
    expect(onShow).toHaveBeenCalledOnce()
  })

  it('calls onQuickChat when Quick Chat is clicked', () => {
    createTray('/icon.png', onShow, onQuickChat, onQuit)
    const template = mocks.buildFromTemplate.mock.calls[0][0] as { click: () => void }[]
    template[1].click()
    expect(onQuickChat).toHaveBeenCalledOnce()
  })

  it('calls onQuit when Quit is clicked', () => {
    createTray('/icon.png', onShow, onQuickChat, onQuit)
    const template = mocks.buildFromTemplate.mock.calls[0][0] as { click: () => void }[]
    template[3].click()
    expect(onQuit).toHaveBeenCalledOnce()
  })
})
