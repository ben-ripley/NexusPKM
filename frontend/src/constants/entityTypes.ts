export const ALL_ENTITY_TYPES = [
  'person',
  'project',
  'topic',
  'decision',
  'action_item',
  'meeting',
] as const

export type EntityType = (typeof ALL_ENTITY_TYPES)[number]

export const ENTITY_TYPE_COLORS: Record<string, string> = {
  person:      '#3b82f6',
  project:     '#10b981',
  topic:       '#f59e0b',
  decision:    '#8b5cf6',
  action_item: '#ef4444',
  meeting:     '#06b6d4',
}
