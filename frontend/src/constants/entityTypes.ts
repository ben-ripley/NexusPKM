export const ALL_ENTITY_TYPES = [
  'person',
  'project',
  'topic',
  'decision',
  'action_item',
  'meeting',
] as const

export type EntityType = (typeof ALL_ENTITY_TYPES)[number]
