import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'electron-vite'
import path from 'path'

export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        input: path.resolve(__dirname, 'electron/main.ts'),
        output: { entryFileNames: 'index.js' },
      },
    },
  },
  preload: {
    build: {
      rollupOptions: {
        input: path.resolve(__dirname, 'electron/preload.ts'),
        // electron-vite 5 outputs ESM preload as <entryName>.mjs; pin the name
        // explicitly so getPreloadPath() in main.ts stays in sync.
        output: { entryFileNames: 'preload.mjs' },
      },
    },
  },
  renderer: {
    root: '.',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      rollupOptions: {
        input: './index.html',
      },
    },
  },
})
