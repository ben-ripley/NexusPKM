// @vitest-environment node

import { afterEach, describe, expect, it, vi } from 'vitest'
import { handleBackendExit, waitForHealth } from '../../electron/backend-lifecycle'

const HEALTH_URL = 'http://127.0.0.1:8000/health'

describe('handleBackendExit', () => {
  it('calls onUnexpectedStop when the app is not shutting down', () => {
    const onStop = vi.fn()
    handleBackendExit(1, false, onStop)
    expect(onStop).toHaveBeenCalledOnce()
  })

  it('does not call onUnexpectedStop during intentional shutdown', () => {
    const onStop = vi.fn()
    handleBackendExit(0, true, onStop)
    expect(onStop).not.toHaveBeenCalled()
  })

  it('calls onUnexpectedStop when exit code is null (signal kill)', () => {
    const onStop = vi.fn()
    handleBackendExit(null, false, onStop)
    expect(onStop).toHaveBeenCalledOnce()
  })
})

describe('waitForHealth', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('resolves when health endpoint returns ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok' }),
      }),
    )

    await expect(waitForHealth(HEALTH_URL, 5000)).resolves.toBeUndefined()
  })

  it('rejects with timeout error when backend never responds', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Connection refused')))

    await expect(waitForHealth(HEALTH_URL, 100, 10)).rejects.toThrow(
      'Backend did not become healthy within 100ms',
    )
  })

  it('retries until success', async () => {
    let callCount = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
        callCount++
        if (callCount < 3) {
          throw new Error('not ready yet')
        }
        return { ok: true, json: async () => ({ status: 'ok' }) }
      }),
    )

    await expect(waitForHealth(HEALTH_URL, 5000, 10)).resolves.toBeUndefined()
    expect(callCount).toBe(3)
  })
})
