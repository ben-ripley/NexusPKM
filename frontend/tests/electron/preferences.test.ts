// @vitest-environment node

import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { AppPreferences } from '../../electron/notification-utils'
import { loadPreferences, savePreferences } from '../../electron/preferences'

describe('loadPreferences', () => {
  let tmpDir: string

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexuspkm-prefs-test-'))
  })

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true })
  })

  it('returns defaults when file does not exist', async () => {
    await expect(loadPreferences(tmpDir)).resolves.toEqual({ autoLaunch: false, closeToTray: true })
  })

  it('returns stored preferences when file exists', async () => {
    const stored: AppPreferences = { autoLaunch: true, closeToTray: false }
    fs.writeFileSync(path.join(tmpDir, 'preferences.json'), JSON.stringify(stored))
    await expect(loadPreferences(tmpDir)).resolves.toEqual(stored)
  })

  it('falls back to defaults for fields with non-boolean values', async () => {
    fs.writeFileSync(
      path.join(tmpDir, 'preferences.json'),
      JSON.stringify({ autoLaunch: 'yes', closeToTray: 1 }),
    )
    await expect(loadPreferences(tmpDir)).resolves.toEqual({ autoLaunch: false, closeToTray: true })
  })

  it('falls back to defaults when file contains invalid JSON', async () => {
    fs.writeFileSync(path.join(tmpDir, 'preferences.json'), 'not valid json')
    await expect(loadPreferences(tmpDir)).resolves.toEqual({ autoLaunch: false, closeToTray: true })
  })

  it('falls back per-field when only some fields are present', async () => {
    fs.writeFileSync(path.join(tmpDir, 'preferences.json'), JSON.stringify({ autoLaunch: true }))
    await expect(loadPreferences(tmpDir)).resolves.toEqual({ autoLaunch: true, closeToTray: true })
  })
})

describe('savePreferences', () => {
  let tmpDir: string

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexuspkm-prefs-test-'))
  })

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true })
  })

  it('writes preferences that can be read back and returns true', async () => {
    const prefs: AppPreferences = { autoLaunch: true, closeToTray: false }
    const saved = await savePreferences(tmpDir, prefs)
    expect(saved).toBe(true)
    await expect(loadPreferences(tmpDir)).resolves.toEqual(prefs)
  })

  it('overwrites an existing preferences file', async () => {
    await savePreferences(tmpDir, { autoLaunch: false, closeToTray: true })
    await savePreferences(tmpDir, { autoLaunch: true, closeToTray: false })
    await expect(loadPreferences(tmpDir)).resolves.toEqual({ autoLaunch: true, closeToTray: false })
  })

  it('returns false and does not throw when the directory does not exist', async () => {
    const result = await savePreferences('/nonexistent/path/that/does/not/exist', {
      autoLaunch: false,
      closeToTray: true,
    })
    expect(result).toBe(false)
  })
})
