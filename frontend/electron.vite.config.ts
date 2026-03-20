import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'electron-vite'
import path from 'path'

export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        input: 'electron/main.ts',
      },
    },
  },
  preload: {
    build: {
      rollupOptions: {
        input: 'electron/preload.ts',
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
