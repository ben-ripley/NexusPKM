import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { ENTITY_TYPE_COLORS } from '@/constants/entityTypes'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Convert a snake_case source type value to a display label.
 *  e.g. "obsidian_note" → "Obsidian Note"
 */
export function formatSourceType(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/** Hex colors for source types — reuses entity type colors so both filter legends share the same palette. */
export const SOURCE_TYPE_COLORS: Record<string, string> = {
  obsidian_note:    ENTITY_TYPE_COLORS.decision,     // #8b5cf6 purple
  teams_transcript: ENTITY_TYPE_COLORS.person,       // #3b82f6 blue
  outlook_email:    ENTITY_TYPE_COLORS.action_item,  // #ef4444 red
  outlook_calendar: ENTITY_TYPE_COLORS.project,      // #10b981 green
  jira_issue:       ENTITY_TYPE_COLORS.meeting,      // #06b6d4 cyan
  apple_note:       ENTITY_TYPE_COLORS.topic,        // #f59e0b amber
}

const SOURCE_TYPE_COLOR_DEFAULT = '#94a3b8'

export function sourceTypeColor(value: string): string {
  return SOURCE_TYPE_COLORS[value] ?? SOURCE_TYPE_COLOR_DEFAULT
}

/** Tailwind classes for the source type badge, keyed by source_type value. */
const SOURCE_TYPE_BADGE: Record<string, string> = {
  obsidian_note:     'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  teams_transcript:  'bg-blue-100   text-blue-700   dark:bg-blue-900/30   dark:text-blue-400',
  outlook_email:     'bg-red-100    text-red-700    dark:bg-red-900/30    dark:text-red-400',
  outlook_calendar:  'bg-teal-100   text-teal-700   dark:bg-teal-900/30   dark:text-teal-400',
  jira_issue:        'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  apple_note:        'bg-amber-100  text-amber-700  dark:bg-amber-900/30  dark:text-amber-400',
}

const SOURCE_TYPE_BADGE_DEFAULT = 'bg-secondary text-secondary-foreground'

export function sourceTypeBadgeClass(value: string): string {
  return SOURCE_TYPE_BADGE[value] ?? SOURCE_TYPE_BADGE_DEFAULT
}
