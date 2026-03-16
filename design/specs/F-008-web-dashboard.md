# F-008: Web Dashboard

**Spec Version:** 1.0
**Date:** 2026-03-16
**ADR Reference:** ADR-005

## Overview

The main landing page of NexusPKM, providing an at-a-glance view of the knowledge base. Includes recent activity, connector status, knowledge graph summary, quick search, and entry points to chat and detailed exploration.

## User Stories

- As a user, I want to see recent activity across all my data sources at a glance
- As a user, I want to know the sync status of each connector (healthy, syncing, error)
- As a user, I want a visual overview of my knowledge graph (key entities and connections)
- As a user, I want quick access to chat and search from the dashboard
- As a user, I want to see upcoming items and pending action items

## Functional Requirements

### FR-1: Application Shell

Global layout wrapping all pages:
- **Top bar**: app logo/name, global search bar, theme toggle (dark/light), settings gear
- **Left sidebar**: navigation links — Dashboard, Chat, Search, Graph Explorer, Settings
- **Content area**: page-specific content
- Responsive: sidebar collapsible on smaller screens

Navigation structure:
| Page | Path | Icon |
|---|---|---|
| Dashboard | `/` | Home |
| Chat | `/chat` | MessageSquare |
| Search | `/search` | Search |
| Graph Explorer | `/graph` | Network |
| Settings | `/settings` | Settings |

### FR-2: Dashboard Components

#### Activity Feed
- Chronological list of recent knowledge base changes
- Items: new documents ingested, entities discovered, relationships created
- Each item shows: icon (by source type), title, timestamp, brief description
- Limit: 20 most recent items, "View all" link
- Auto-updates via polling (30-second interval)

#### Connector Status Panel
- Card per configured connector
- Each card shows: connector name, icon, status badge (active/syncing/error/disabled), last sync time, document count
- Quick action: manual sync trigger button
- Error state shows brief error message with link to settings

#### Knowledge Base Stats
- Total documents, entities, relationships
- Breakdown by source type (pie chart or bar chart)
- Growth trend (documents ingested over time)

#### Quick Search
- Search bar with autocomplete (same component as global search)
- Recent searches list

#### Upcoming Items (if calendar data available)
- Next 5 upcoming calendar events with meeting prep context
- Pending action items sorted by priority

#### Knowledge Graph Mini-View
- Small interactive graph showing top entities and recent connections
- Clickable to navigate to full Graph Explorer
- Shows: top 20 most-connected entities, relationships added this week

### FR-3: Theme System

- Dark and light mode
- System preference detection with manual override
- Theme stored in localStorage
- Tailwind dark mode via `class` strategy
- Consistent color palette across all pages

### FR-4: Settings Page

- **Provider Configuration**: current LLM/embedding providers, health status, switch provider
- **Connector Management**: enable/disable connectors, configure settings, view logs
- **Sync Management**: manual sync triggers, sync history, error logs
- **Preferences**: theme, notification settings, default search settings
- **About**: version, storage usage, knowledge base statistics

## Non-Functional Requirements

- Dashboard load time < 2 seconds (all data from API)
- Activity feed auto-refresh without full page reload
- Theme switch must be instantaneous (no flash of wrong theme on load)
- Accessible: WCAG 2.1 AA compliance for all interactive elements

## UI/UX Requirements

### Visual Design
- Clean, modern aesthetic using shadcn/ui components
- Consistent spacing using Tailwind's spacing scale
- Card-based layout for dashboard sections
- Subtle animations on transitions and state changes
- Graph visualization uses force-directed layout with zoom/pan

### Responsive Behavior
- Desktop (1280px+): full sidebar + multi-column dashboard
- Tablet (768-1279px): collapsible sidebar, stacked dashboard cards
- Below 768px: not a priority (local desktop app)

## API Endpoints Required

| Method | Path | Description |
|---|---|---|
| GET | `/api/dashboard/activity` | Recent activity feed |
| GET | `/api/dashboard/stats` | Knowledge base statistics |
| GET | `/api/connectors/status` | All connector statuses |
| GET | `/api/dashboard/upcoming` | Upcoming calendar items |

## Testing Strategy

### Frontend Tests
- Test dashboard component rendering with mock API data
- Test activity feed auto-refresh
- Test connector status card states (active, syncing, error, disabled)
- Test theme toggle persistence
- Test navigation routing
- Test responsive layout breakpoints

### Integration Tests
- Test dashboard loads with real API backend
- Test connector sync trigger from dashboard

## Dependencies

- F-002 (Knowledge Engine Core) — for stats endpoints
- F-001 (LLM Provider Abstraction) — for provider health in settings
- Backend API must be running

## Acceptance Criteria

- [ ] Dashboard displays activity feed with recent changes
- [ ] Connector status cards show current sync state for each connector
- [ ] Knowledge base stats show document/entity/relationship counts
- [ ] Quick search works from dashboard
- [ ] Dark/light theme toggle works and persists across sessions
- [ ] Navigation between all pages works via sidebar
- [ ] Settings page allows viewing and updating provider and connector configuration
- [ ] Dashboard loads in < 2 seconds
- [ ] Graph mini-view renders top entities interactively
