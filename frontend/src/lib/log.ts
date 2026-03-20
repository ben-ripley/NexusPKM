const PREFIX = 'nexuspkm'

export const log = {
  warn: (msg: string, ...args: unknown[]) => {
    console.warn(`[${PREFIX}] ${msg}`, ...args)
  },
  error: (msg: string, ...args: unknown[]) => {
    console.error(`[${PREFIX}] ${msg}`, ...args)
  },
}
