import { Notification } from 'electron'

export interface SyncNotificationOptions {
  source: string
  count: number
}

export interface EntityNotificationOptions {
  entityName: string
  relationshipCount: number
}

export function showSyncNotification(options: SyncNotificationOptions): void {
  const { source, count } = options
  new Notification({
    title: `${source} sync complete`,
    body: `${count} new item${count !== 1 ? 's' : ''} ingested`,
  }).show()
}

export function showEntityNotification(options: EntityNotificationOptions): void {
  const { entityName, relationshipCount } = options
  new Notification({
    title: `New entity: ${entityName}`,
    body: `Discovered ${relationshipCount} relationship${relationshipCount !== 1 ? 's' : ''}`,
  }).show()
}
