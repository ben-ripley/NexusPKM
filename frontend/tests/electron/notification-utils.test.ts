// @vitest-environment node

import { describe, expect, it } from 'vitest'
import { sanitizeNotification } from '../../electron/notification-utils'

describe('sanitizeNotification', () => {
  it('returns params unchanged when both are valid strings within limits', () => {
    expect(sanitizeNotification('Hello', 'World')).toEqual({ title: 'Hello', body: 'World' })
  })

  it('returns null when title is not a string', () => {
    expect(sanitizeNotification(42, 'body')).toBeNull()
    expect(sanitizeNotification(null, 'body')).toBeNull()
    expect(sanitizeNotification(undefined, 'body')).toBeNull()
    expect(sanitizeNotification({}, 'body')).toBeNull()
  })

  it('returns null when body is not a string', () => {
    expect(sanitizeNotification('title', 0)).toBeNull()
    expect(sanitizeNotification('title', null)).toBeNull()
    expect(sanitizeNotification('title', [])).toBeNull()
  })

  it('truncates title to 64 characters', () => {
    const longTitle = 'a'.repeat(100)
    const result = sanitizeNotification(longTitle, 'body')
    expect(result?.title).toHaveLength(64)
    expect(result?.title).toBe('a'.repeat(64))
  })

  it('truncates body to 256 characters', () => {
    const longBody = 'b'.repeat(400)
    const result = sanitizeNotification('title', longBody)
    expect(result?.body).toHaveLength(256)
    expect(result?.body).toBe('b'.repeat(256))
  })

  it('preserves strings exactly at the length limits', () => {
    const title64 = 'x'.repeat(64)
    const body256 = 'y'.repeat(256)
    const result = sanitizeNotification(title64, body256)
    expect(result).toEqual({ title: title64, body: body256 })
  })
})
