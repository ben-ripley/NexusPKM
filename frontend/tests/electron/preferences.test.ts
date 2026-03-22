// @vitest-environment node

import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { loadPreferences, savePreferences, type AppPreferences } from '../../electron/preferences'

describe('loadPreferences', () => {
  let tmpDir: string

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexuspkm-prefs-test-'))
  })

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true })
  })

  it('returns defaults when file does not exist', () => {
    expect(loadPreferences(tmpDir)).toEqual({ autoLaunch: false, closeToTray: true })
  })

  it('returns stored preferences when file exists', () => {
    const stored: AppPreferences = { autoLaunch: true, closeToTray: false }
    fs.writeFileSync(path.join(tmpDir, 'preferences.json'), JSON.stringify(stored))
    expect(loadPreferences(tmpDir)).toEqual(stored)
  })

  it('falls back to defaults for fields with non-boolean values', () => {
    fs.writeFileSync(
      path.join(tmpDir, 'preferences.json'),
      JSON.stringify({ autoLaunch: 'yes', closeToTray: 1 }),
    )
    expect(loadPreferences(tmpDir)).toEqual({ autoLaunch: false, closeToTray: true })
  })

  it('falls back to defaults when file contains invalid JSON', () => {
    fs.writeFileSync(path.join(tmpDir, 'preferences.json'), 'not valid json')
    expect(loadPreferences(tmpDir)).toEqual({ autoLaunch: false, closeToTray: true })
  })

  it('falls back per-field when only some fields are present', () => {
    fs.writeFileSync(path.join(tmpDir, 'preferences.json'), JSON.stringify({ autoLaunch: true }))
    expect(loadPreferences(tmpDir)).toEqual({ autoLaunch: true, closeToTray: true })
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

  it('writes preferences that can be read back', () => {
    const prefs: AppPreferences = { autoLaunch: true, closeToTray: false }
    savePreferences(tmpDir, prefs)
    expect(loadPreferences(tmpDir)).toEqual(prefs)
  })

  it('overwrites an existing preferences file', () => {
    savePreferences(tmpDir, { autoLaunch: false, closeToTray: true })
    savePreferences(tmpDir, { autoLaunch: true, closeToTray: false })
    expect(loadPreferences(tmpDir)).toEqual({ autoLaunch: true, closeToTray: false })
  })
})
