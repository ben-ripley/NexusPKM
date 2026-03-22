export type BackendStatus = 'starting' | 'healthy' | 'error' | 'stopped'

/**
 * Validates and sanitises `title` / `body` received over the untrusted
 * renderer IPC channel before passing them to the OS notification daemon.
 *
 * Returns null when either argument is not a string (silently drops the
 * request so a compromised renderer cannot crash the notification daemon
 * with non-string values).  Long strings are truncated to prevent abuse.
 */
export function sanitizeNotification(
  title: unknown,
  body: unknown,
): { title: string; body: string } | null {
  if (typeof title !== 'string' || typeof body !== 'string') return null
  return {
    title: title.slice(0, 64),
    body: body.slice(0, 256),
  }
}
