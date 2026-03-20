import type { Configuration } from 'electron-builder'

const config: Configuration = {
  appId: 'com.nexuspkm.app',
  productName: 'NexusPKM',
  copyright: 'Copyright © 2026 NexusPKM',

  directories: {
    buildResources: 'assets',
    output: 'dist-electron',
  },

  files: [
    'out/**/*',        // electron-vite build output (main + preload)
    'dist/**/*',       // renderer build output
    '!**/*.map',
    '!**/node_modules',
  ],

  mac: {
    category: 'public.app-category.productivity',
    icon: 'assets/icon.icns',
    target: [{ target: 'dmg', arch: ['arm64', 'x64'] }],
    // Code signing: set CSC_LINK and CSC_KEY_PASSWORD env vars for distribution builds.
    // Leave unset for local dev/test builds (ad-hoc signing used automatically).
    hardenedRuntime: true,
    gatekeeperAssess: false,
    entitlements: 'assets/entitlements.mac.plist',
    entitlementsInherit: 'assets/entitlements.mac.plist',
  },

  dmg: {
    // electron-builder macro syntax — not a JS template literal; processed at build time
    title: 'NexusPKM ${version}',
    background: 'assets/dmg-background.png',
    icon: 'assets/icon.icns',
    iconSize: 80,
    contents: [
      { x: 130, y: 220, type: 'file' },
      { x: 410, y: 220, type: 'link', path: '/Applications' },
    ],
  },

  // Placeholder for Windows / Linux (future)
  win: {
    target: 'nsis',
    icon: 'assets/icon.ico',
  },
  linux: {
    target: 'AppImage',
    icon: 'assets/icon.png',
    category: 'Office',
  },

  // electron-vite outputs main to out/main/index.js
  extraMetadata: {
    main: 'out/main/index.js',
  },
}

export default config
