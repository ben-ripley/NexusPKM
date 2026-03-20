// @vitest-environment node

import { afterEach, describe, expect, it, vi } from 'vitest'

const { MockNotification, mockShow } = vi.hoisted(() => {
  const mockShow = vi.fn()
  // Must use a regular function (not arrow) so it can be called with `new`
  const MockNotification = vi.fn(function () {
    return { show: mockShow }
  })
  return { MockNotification, mockShow }
})

vi.mock('electron', () => ({
  Notification: MockNotification,
}))

import { showSyncNotification, showEntityNotification } from '../../electron/notifications'

describe('showSyncNotification', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('creates a Notification with sync title and calls show', () => {
    showSyncNotification({ source: 'Teams', count: 5 })
    expect(MockNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringContaining('Teams') as string,
        body: expect.stringContaining('5') as string,
      }),
    )
    expect(mockShow).toHaveBeenCalledOnce()
  })

  it('handles singular item count gracefully', () => {
    showSyncNotification({ source: 'Outlook', count: 1 })
    expect(MockNotification).toHaveBeenCalledWith(
      expect.objectContaining({ body: expect.stringContaining('1') as string }),
    )
    expect(mockShow).toHaveBeenCalledOnce()
  })
})

describe('showEntityNotification', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('creates a Notification with entity title and calls show', () => {
    showEntityNotification({ entityName: 'Alice', relationshipCount: 3 })
    expect(MockNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringContaining('Alice') as string,
      }),
    )
    expect(mockShow).toHaveBeenCalledOnce()
  })
})
