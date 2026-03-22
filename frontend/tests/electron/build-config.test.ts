// @vitest-environment node

import type { FileSet, MacConfiguration, TargetConfiguration } from 'electron-builder'
import { describe, expect, it } from 'vitest'
import config from '../../electron-builder.config'

describe('electron-builder config', () => {
  it('has correct appId', () => {
    expect(config.appId).toBe('com.nexuspkm.app')
  })

  it('has correct productName', () => {
    expect(config.productName).toBe('NexusPKM')
  })

  it('sets main entry to out/main/index.js', () => {
    // Must match the entryFileNames in electron.vite.config.ts for the main bundle.
    expect(config.extraMetadata?.['main']).toBe('out/main/index.js')
  })

  it('outputs to release/ directory', () => {
    expect(config.directories?.output).toBe('release')
  })

  it('includes main and preload bundles in packaged files', () => {
    // Narrow to array before asserting membership so type mismatches surface clearly.
    expect(Array.isArray(config.files)).toBe(true)
    const files = config.files as string[]
    expect(files).toContain('out/main/**')
    expect(files).toContain('out/preload/**')
  })

  it('does not bundle the renderer (served by FastAPI at runtime per ADR-011)', () => {
    expect(Array.isArray(config.files)).toBe(true)
    const files = config.files as string[]
    expect(files).not.toContain('out/renderer/**')
  })

  it('copies only icon.png to packaged app Resources for runtime tray use', () => {
    expect(config.extraResources).toBeDefined()
    const [resource] = config.extraResources as FileSet[]
    expect(resource.filter).toEqual(['icon.png'])
  })

  it('places icon.png under build/ in the packaged Resources directory', () => {
    // main process reads: process.resourcesPath + '/build/icon.png'
    expect(config.extraResources).toBeDefined()
    const [resource] = config.extraResources as FileSet[]
    expect(resource.from).toBe('build')
    expect(resource.to).toBe('build')
  })

  it('targets macOS DMG for both arm64 and x64', () => {
    const mac = config.mac as MacConfiguration
    const [target] = mac.target as TargetConfiguration[]
    expect(target.target).toBe('dmg')
    expect(target.arch).toEqual(['arm64', 'x64'])
  })

  it('references the macOS icon at build/icon.icns', () => {
    const mac = config.mac as MacConfiguration
    expect(mac.icon).toBe('build/icon.icns')
  })

  it('uses productivity category for macOS', () => {
    const mac = config.mac as MacConfiguration
    expect(mac.category).toBe('public.app-category.productivity')
  })
})
