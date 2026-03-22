import type { Configuration } from 'electron-builder'

/**
 * electron-builder configuration for NexusPKM macOS distribution.
 *
 * Code signing (optional — unsigned builds work for local use):
 *   CSC_LINK             Path or HTTPS URL to the .p12 signing certificate
 *   CSC_KEY_PASSWORD     Password for the .p12 certificate
 *
 * Notarization (required for public/App Store distribution):
 *   APPLE_ID                    Apple developer account email
 *   APPLE_APP_SPECIFIC_PASSWORD App-specific password for notarytool
 *   APPLE_TEAM_ID               Apple Developer Team ID
 *
 * Without signing env vars the app builds unsigned, which works for local use
 * but will trigger macOS Gatekeeper warnings for end users.
 */
const config: Configuration = {
  appId: 'com.nexuspkm.app',
  productName: 'NexusPKM',

  // Inject the compiled main entry so electron-builder resolves it correctly
  // after electron-vite outputs to out/main/index.js.
  extraMetadata: {
    main: 'out/main/index.js',
  },

  directories: {
    output: 'release',
    buildResources: 'build',
  },

  // Include only the compiled main and preload bundles.
  // The renderer is served by the FastAPI backend at runtime (ADR-011).
  files: ['out/main/**', 'out/preload/**', 'package.json'],

  // Copy icon.png into the packaged app's Resources so the main process can
  // load it at runtime for the tray (process.resourcesPath + '/build/icon.png').
  // icon.icns is consumed by electron-builder during packaging only and does not
  // need to be present in the installed app bundle.
  extraResources: [{ from: 'build', to: 'build', filter: ['icon.png'] }],

  mac: {
    target: [{ target: 'dmg', arch: ['arm64', 'x64'] }],
    icon: 'build/icon.icns',
    category: 'public.app-category.productivity',
  },

  dmg: {
    contents: [
      { x: 130, y: 220, type: 'file' },
      { x: 410, y: 220, type: 'link', path: '/Applications' },
    ],
  },
}

export default config
