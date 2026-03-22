import fs from 'fs'
import path from 'path'
import { DEFAULT_PREFERENCES, type AppPreferences } from './notification-utils'

export type { AppPreferences }

const PREFS_FILE = 'preferences.json'

/**
 * Reads AppPreferences from `{dataDir}/preferences.json`.
 * Returns defaults for any missing or invalid field; never throws.
 */
export async function loadPreferences(dataDir: string): Promise<AppPreferences> {
  try {
    const raw = await fs.promises.readFile(path.join(dataDir, PREFS_FILE), 'utf-8')
    const parsed = JSON.parse(raw) as Record<string, unknown>
    return {
      autoLaunch:
        typeof parsed['autoLaunch'] === 'boolean'
          ? parsed['autoLaunch']
          : DEFAULT_PREFERENCES.autoLaunch,
      closeToTray:
        typeof parsed['closeToTray'] === 'boolean'
          ? parsed['closeToTray']
          : DEFAULT_PREFERENCES.closeToTray,
    }
  } catch {
    return { ...DEFAULT_PREFERENCES }
  }
}

/**
 * Writes AppPreferences to `{dataDir}/preferences.json`.
 * Returns true on success, false if the write fails (e.g. read-only filesystem, disk full).
 * Never throws.
 */
export async function savePreferences(dataDir: string, prefs: AppPreferences): Promise<boolean> {
  try {
    await fs.promises.writeFile(
      path.join(dataDir, PREFS_FILE),
      JSON.stringify(prefs, null, 2),
      'utf-8',
    )
    return true
  } catch (err) {
    process.stderr.write(`[preferences] Failed to save preferences: ${String(err)}\n`)
    return false
  }
}
