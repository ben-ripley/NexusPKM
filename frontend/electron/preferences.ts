import fs from 'fs'
import path from 'path'

export interface AppPreferences {
  autoLaunch: boolean
  closeToTray: boolean
}

const DEFAULTS: AppPreferences = {
  autoLaunch: false,
  closeToTray: true,
}

const PREFS_FILE = 'preferences.json'

/**
 * Reads AppPreferences from `{dataDir}/preferences.json`.
 * Returns defaults for any missing or invalid field; never throws.
 */
export function loadPreferences(dataDir: string): AppPreferences {
  try {
    const raw = fs.readFileSync(path.join(dataDir, PREFS_FILE), 'utf-8')
    const parsed = JSON.parse(raw) as Record<string, unknown>
    return {
      autoLaunch:
        typeof parsed['autoLaunch'] === 'boolean' ? parsed['autoLaunch'] : DEFAULTS.autoLaunch,
      closeToTray:
        typeof parsed['closeToTray'] === 'boolean' ? parsed['closeToTray'] : DEFAULTS.closeToTray,
    }
  } catch {
    return { ...DEFAULTS }
  }
}

/**
 * Writes AppPreferences to `{dataDir}/preferences.json`.
 */
export function savePreferences(dataDir: string, prefs: AppPreferences): void {
  fs.writeFileSync(path.join(dataDir, PREFS_FILE), JSON.stringify(prefs, null, 2), 'utf-8')
}
