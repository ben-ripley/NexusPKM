import * as net from 'net'

/**
 * Handles an unexpected backend process exit.
 * Calls `onUnexpectedStop` only when the app is not already shutting down
 * intentionally — suppresses spurious 'stopped' broadcasts during clean quits.
 */
export function handleBackendExit(
  code: number | null,
  isShuttingDown: boolean,
  onUnexpectedStop: () => void,
): void {
  if (!isShuttingDown) {
    process.stderr.write(`[main] Backend exited unexpectedly with code ${String(code)}\n`)
    onUnexpectedStop()
  }
}

/**
 * Checks whether a TCP port is already in use on 127.0.0.1.
 * Returns true if the port is occupied, false if it is free.
 */
export function isPortInUse(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.once('error', () => resolve(true))
    server.once('listening', () => {
      server.close(() => resolve(false))
    })
    server.listen(port, '127.0.0.1')
  })
}

/**
 * Polls `url` with GET until the response body contains `{status: "ok"}`.
 * Throws if the backend does not become healthy within `maxWaitMs` milliseconds.
 */
export async function waitForHealth(
  url: string,
  maxWaitMs: number,
  pollIntervalMs = 500,
): Promise<void> {
  const deadline = Date.now() + maxWaitMs

  while (Date.now() < deadline) {
    try {
      const resp = await fetch(url)
      if (resp.ok) {
        const data: unknown = await resp.json()
        if (
          typeof data === 'object' &&
          data !== null &&
          'status' in data &&
          (data as Record<string, unknown>).status === 'ok'
        ) {
          return
        }
      }
    } catch {
      // backend not ready yet — fall through to sleep
    }
    await new Promise<void>((r) => setTimeout(r, pollIntervalMs))
  }

  throw new Error(`Backend did not become healthy within ${maxWaitMs}ms`)
}
