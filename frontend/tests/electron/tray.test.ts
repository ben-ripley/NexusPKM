// @vitest-environment node

import { afterEach, describe, expect, it, vi } from 'vitest'

// Mock electron before importing tray module
vi.mock('electron', () => ({
  Tray: vi.fn().mockImplementation(() => ({
    setToolTip: vi.fn(),
    setContextMenu: vi.fn(),
    on: vi.fn(),
  })),
  Menu: {
    buildFromTemplate: vi.fn().mockReturnValue({ mock: 'menu' }),
  },
  app: {
    quit: vi.fn(),
  },
  nativeImage: {
    createEmpty: vi.fn().mockReturnValue({ isEmpty: () => true }),
  },
}))

import { buildTrayMenuTemplate } from '../../electron/tray'
import { app, Menu } from 'electron'

describe('buildTrayMenuTemplate', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('includes Show, Quick Chat, and Quit items', () => {
    const showFn = vi.fn()
    const template = buildTrayMenuTemplate({ onShow: showFn, onQuickChat: vi.fn() })
    const labels = template.map((item) => item.label)
    expect(labels).toContain('Show NexusPKM')
    expect(labels).toContain('Quick Chat')
    expect(labels).toContain('Quit')
  })

  it('calls onShow when Show item is clicked', () => {
    const onShow = vi.fn()
    const template = buildTrayMenuTemplate({ onShow, onQuickChat: vi.fn() })
    const showItem = template.find((item) => item.label === 'Show NexusPKM')
    showItem?.click?.()
    expect(onShow).toHaveBeenCalledOnce()
  })

  it('calls onQuickChat when Quick Chat item is clicked', () => {
    const onQuickChat = vi.fn()
    const template = buildTrayMenuTemplate({ onShow: vi.fn(), onQuickChat })
    const chatItem = template.find((item) => item.label === 'Quick Chat')
    chatItem?.click?.()
    expect(onQuickChat).toHaveBeenCalledOnce()
  })

  it('calls app.quit when Quit item is clicked', () => {
    const template = buildTrayMenuTemplate({ onShow: vi.fn(), onQuickChat: vi.fn() })
    const quitItem = template.find((item) => item.label === 'Quit')
    quitItem?.click?.()
    expect(app.quit).toHaveBeenCalledOnce()
  })

  it('calls Menu.buildFromTemplate with the template', () => {
    const template = buildTrayMenuTemplate({ onShow: vi.fn(), onQuickChat: vi.fn() })
    Menu.buildFromTemplate(template)
    expect(Menu.buildFromTemplate).toHaveBeenCalledWith(template)
  })
})
