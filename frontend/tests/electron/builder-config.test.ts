// @vitest-environment node

import { describe, expect, it } from 'vitest'
import config from '../../electron-builder.config'

describe('electron-builder.config', () => {
  it('has the correct app ID', () => {
    expect(config.appId).toBe('com.nexuspkm.app')
  })

  it('has the correct product name', () => {
    expect(config.productName).toBe('NexusPKM')
  })

  it('targets macOS dmg', () => {
    const mac = config.mac as { target: Array<{ target: string }> } | undefined
    expect(mac).toBeDefined()
    expect(Array.isArray(mac?.target)).toBe(true)
    const targets = mac?.target.map((t) => t.target)
    expect(targets).toContain('dmg')
  })

  it('points to the electron-vite main output', () => {
    const meta = config.extraMetadata as Record<string, unknown> | undefined
    expect(meta?.main).toBe('out/main/index.js')
  })

  it('includes out/ and dist/ in files', () => {
    const files = config.files as string[] | undefined
    expect(files?.some((f) => String(f).startsWith('out/'))).toBe(true)
    expect(files?.some((f) => String(f).startsWith('dist/'))).toBe(true)
  })

  it('outputs to dist-electron directory', () => {
    const dirs = config.directories as { output?: string } | undefined
    expect(dirs?.output).toBe('dist-electron')
  })
})
