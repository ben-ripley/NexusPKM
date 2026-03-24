# User Guide

This guide walks through everything you can do in NexusPKM once it's running and your connectors are syncing.

---

## Starting the application

### Electron desktop app (recommended)

**Development** (with hot module reloading):

```bash
cd frontend && npm run electron:dev
```

The backend is spawned automatically — no need to start it separately.

**Production** — install the `.dmg` and launch NexusPKM from your Applications folder:

```bash
cd frontend && npm run electron:dist
# Produces release/NexusPKM-{version}.dmg
```

### Web browser (fallback)

Run the backend and frontend separately, then open `http://localhost:5173`:

```bash
# Terminal 1
cd backend && uvicorn nexuspkm.main:app --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend && npm run dev
```

---

## Application layout

> **Screenshot placeholder:** Full application shell showing top bar, left sidebar, and content area

The application has a persistent shell with:

- **Top bar** — app logo, global search bar, notification bell, theme toggle (dark/light), settings gear
- **Left sidebar** — navigation: Dashboard, Chat, Search, Graph Explorer, Settings
- **Content area** — the current page

---

## Dashboard

The dashboard is the landing page. It gives you a quick health check and summary of your knowledge base.

> **Screenshot placeholder:** Dashboard with all panels visible

### Activity feed

A chronological list of recent events in the knowledge base — documents ingested, entities discovered, new relationships created, and contradictions flagged. Auto-refreshes every 30 seconds.

### Connector status panel

> **Screenshot placeholder:** Connector status cards (active, syncing, error
> states)

One card per configured connector. Each card shows:

- **Status badge**: `active` (green), `syncing` (yellow spinner), `error` (red), `disabled` (grey)
- **Last sync time** — how recently content was fetched
- **Document count** — total documents ingested from this source
- **Sync button** — trigger an immediate sync without waiting for the next scheduled run
- **Error message** (if in error state) with a link to Settings for reconfiguration

### Knowledge base stats

Total documents, entities, and relationships across all sources. A breakdown by source type shows where your knowledge is coming from.

### Quick search

A search bar with autocomplete. Results are the same as the full Search page but presented inline. Click a result to open it or navigate to the Search page for filters and facets.

### Upcoming items

If Outlook calendar sync is enabled, the next five calendar events are shown here with attendee summaries. Pending action items (from JIRA or extracted from documents) are listed below.

### Knowledge graph mini-view

A small interactive force-directed graph showing the top 20 most-connected entities. Drag nodes to explore, click to see details. Click "View full graph" to open the Graph Explorer.

---

## Chat

Chat is the primary way to query your knowledge base using natural language.

> **Screenshot placeholder:** Chat interface with a multi-turn conversation, source cards, and follow-up suggestions

### Asking a question

Type a question and press **Enter** (or **Shift+Enter** for a new line). The system runs a hybrid search (semantic + graph) over all your data, assembles relevant context, and streams a response from the LLM.

Example questions:
- "What did we decide about the API authentication approach?"
- "What action items does Jane have open?"
- "Summarise the last three meetings with the platform team."
- "What's the current status of Project Atlas?"

### Source citations

Every answer includes numbered citations — `[1]`, `[2]`, etc. — linked to the exact source. Source cards appear below the answer showing:

- Source type (Teams meeting, email, JIRA ticket, Obsidian note, etc.)
- Title and date
- A relevant excerpt from the source
- A direct link to the original (where available)

Click a citation number to highlight the corresponding source card.

### Follow-up suggestions

After each response, 2–3 suggested follow-up questions appear as chips below the answer. These are generated from the entities and topics mentioned in the response. Click one to send it immediately.

### Chat sessions

Conversations are organised into sessions. The session list appears in the left panel within the Chat page.

- **New session** — start a fresh conversation; the session is auto-titled from your first message
- **Resume a session** — click any past session to continue from where you left off
- **Delete a session** — hover over a session and click the trash icon

Sessions persist across application restarts.

### Query modes

The chat interface supports three modes, toggled by a prefix in your message:

| Mode | How to use | What it does |
|---|---|---|
| Natural language (default) | Just type your question | Retrieves context and generates an LLM answer |
| `/search` | `/search teams transcripts about roadmap` | Vector search without LLM generation — returns raw matching chunks |
| `/graph` | `/graph MATCH (p:Person)-[:ATTENDED]->(m:Meeting) RETURN p.name, m.title` | Direct Cypher query against the graph database |

The `/graph` mode is for power users comfortable with Cypher. The `/search` mode is useful when you want raw results, not an LLM-synthesised answer.

### /graph query examples

The graph contains these node types: `Person`, `Project`, `Topic`, `Decision`,
`ActionItem`, `Meeting`, `Document`.

And these relationships: `ATTENDED`, `MENTIONED_IN`, `ASSIGNED_TO`,
`RELATED_TO`, `DECIDED_IN`, `WORKS_ON`, `TAGGED_WITH`, `OWNS`, `BLOCKS`,
`FOLLOWED_UP_BY`.

---

**Who attended a specific meeting?**
```
/graph MATCH (p:Person)-[:ATTENDED]->(m:Meeting)
  WHERE m.title CONTAINS 'Project Hercules'
  RETURN p.name ORDER BY p.name
```

---

**What action items are assigned to a person?**
```
/graph MATCH (a:ActionItem)-[:ASSIGNED_TO]->(p:Person)
  WHERE p.name = 'Jane Smith'
  RETURN a.description, a.status, a.due_date
  ORDER BY a.due_date
```

---

**What decisions were made in a meeting?**
```
/graph MATCH (d:Decision)-[:DECIDED_IN]->(m:Meeting)
  WHERE m.title CONTAINS 'Architecture Review'
  RETURN d.summary, d.made_at
```

---

**Which people work on a project?**
```
/graph MATCH (p:Person)-[:WORKS_ON]->(proj:Project)
  WHERE proj.name = 'Hercules'
  RETURN p.name, p.email
```

---

**What documents are tagged with a topic?**
```
/graph MATCH (doc:Document)-[:TAGGED_WITH]->(t:Topic)
  WHERE t.name = 'API design'
  RETURN doc.title, doc.source_type, doc.created_at
  ORDER BY doc.created_at DESC
  LIMIT 10
```

---

**Which action items are blocking other action items?**
```
/graph MATCH (blocker:ActionItem)-[:BLOCKS]->(blocked:ActionItem)
  RETURN blocker.description AS blocking, blocked.description AS blocked_by
```

---

**Multi-hop: what meetings have people who work on a project attended?**
```
/graph MATCH (p:Person)-[:WORKS_ON]->(proj:Project), (p)-[:ATTENDED]->(m:Meeting)
  WHERE proj.name = 'Hercules'
  RETURN p.name, m.title, m.date
  ORDER BY m.date DESC
```

---

**Aggregation: how many open action items does each person have?**
```
/graph MATCH (a:ActionItem)-[:ASSIGNED_TO]->(p:Person)
  WHERE a.status = 'open'
  RETURN p.name, count(a) AS open_items
  ORDER BY open_items DESC
```

---

**What documents mention a specific person?**
```
/graph MATCH (p:Person)-[:MENTIONED_IN]->(doc:Document)
  WHERE p.name = 'Jane Smith'
  RETURN doc.title, doc.source_type, doc.created_at
  ORDER BY doc.created_at DESC
```

---

**Who owns projects, and what are those projects?**
```
/graph MATCH (p:Person)-[:OWNS]->(proj:Project)
  RETURN p.name AS owner, proj.name AS project, proj.description
  ORDER BY p.name
```

---

## Search

The Search page provides faceted, filtered search over the full knowledge base.

> **Screenshot placeholder:** Search results page with filter sidebar and result cards

### Running a search

Type in the search bar at the top. Results appear immediately as you type (debounced 300ms). The search uses the same hybrid retrieval as chat — semantic similarity plus graph expansion — and returns matching document excerpts.

### Autocomplete suggestions

As you type, suggestions appear from:
- Recent searches
- Entity names in the knowledge graph
- Document titles

### Filtering results

The left sidebar contains filters that update results in real time:

| Filter | What it does |
|---|---|
| **Source type** | Limit to Teams, Obsidian, Outlook, JIRA, or Apple Notes |
| **Date range** | Restrict results to a time window |
| **Entity** | Show only documents involving a specific person, project, or topic |
| **Tag** | Filter by Obsidian tags, JIRA labels, or extracted topics |

"Clear all filters" removes all active filters at once.

### Result cards

Each result shows:
- Source type badge (coloured by connector)
- Title and timestamp
- A highlighted excerpt of the most relevant passage
- Relevance score indicator
- Matched entities found in this document
- Related document count (from graph expansion)

Expand a card to see the full excerpt and the related documents linked from the knowledge graph.

### Relevance scoring

Results are ranked by a combined score:

```
score = (semantic similarity × 0.6) + (graph connections × 0.3) + (recency × 0.1)
```

A document that's both semantically close to your query *and* highly connected to relevant entities in the graph ranks higher than one that only matches on one dimension.

---

## Graph Explorer

The Graph Explorer lets you browse and explore the knowledge graph visually.

> **Screenshot placeholder:** Graph Explorer with a force-directed graph, entity detail panel, and filter controls

### What the graph shows

Nodes represent entities: People, Projects, Topics, Decisions, Action Items, Meetings, and Documents. Edges represent relationships: who attended which meeting, who's assigned to what, which decisions were made where, etc.

### Navigation

- **Drag** — move nodes around the canvas
- **Scroll / pinch** — zoom in and out
- **Click a node** — opens a detail panel with the entity's properties,
  connections, and source documents
- **Click an edge** — shows the relationship type and the source context
  (the text excerpt that produced this relationship)

### Filtering the graph

Use the controls above the canvas to:
- Filter by entity type
- Show only entities connected to a specific person or project
- Limit to content from a specific date range or source connector

### Entity detail panel

Clicking a node opens a panel showing:
- Entity type and canonical name
- Known aliases (e.g. "John Smith", "jsmith@co.com", "@john")
- All properties (role, email, status, dates, etc.)
- All relationships with links to connected entities
- Source documents where this entity was found

From here you can navigate to related entities, or click through to the source document in Search or Chat.

---

## Notifications

The bell icon in the top bar shows a count of unread notifications. Click it to open the notification panel.

> **Screenshot placeholder:** Notification panel with meeting prep and
> contradiction alerts

### Notification types

| Type | What triggers it |
|---|---|
| **Meeting preparation** | 1 hour before a calendar event (configurable), NexusPKM assembles relevant context — past meetings with the same attendees, open action items, related JIRA tickets and notes |
| **Related content** | When a newly ingested document connects strongly to existing knowledge — e.g. a new email thread about the same project as a past meeting |
| **Contradiction** | When new information conflicts with existing knowledge — e.g. a deadline changed, or ownership of a project changed |

### Meeting preparation briefings

Meeting prep notifications are the most valuable feature for high-meeting-volume work. Open the notification before a meeting to see:

- Previous meetings with the same attendees
- Open action items assigned to attendees
- Related JIRA tickets
- Related notes and emails
- A suggested agenda generated by the LLM from the assembled context

### Contradiction alerts

When the system detects conflicting information:
- Both values and their sources are shown
- Severity is indicated (high for deadline/date conflicts, medium for status
  changes, low for description changes)
- You can **dismiss** (ignore), **resolve** (pick one value as correct), or
  **flag** (mark for manual follow-up)

### Configuring notifications

Go to **Settings → Notifications** to configure:
- Which notification types are enabled
- Meeting prep lead time (default: 60 minutes before the meeting)
- Minimum connection strength to trigger a related content alert (default: 0.7)

---

## Settings

Settings is accessible from the gear icon in the top bar or the sidebar.

> **Screenshot placeholder:** Settings page showing Provider, Connectors, and
> Preferences tabs

### Provider configuration

Shows the active LLM and embedding provider, model name, and health status. Switch providers here or edit `config/providers.yaml` directly. See [LLM Providers](llm-providers.md) for a full walkthrough.

### Connector management

Each connector has a settings card where you can:
- Enable or disable the connector
- Edit configuration (vault path, folder list, JQL filter, etc.)
- Trigger a manual sync
- View the connector's sync log (recent sync history and errors)
- View the connector's document count

### Sync management

- View the sync history for all connectors
- See when the last successful sync occurred and how many documents were processed
- Trigger a full re-sync (re-processes all documents from the source)

### Preferences

- **Theme**: dark or light mode (also accessible from the top bar toggle)
- **Notifications**: per-type toggles and thresholds (see Notifications above)
- **Default search settings**: default source type filter, default date window

### About

- Application version
- Storage usage breakdown (LanceDB vector store, Kuzu graph store, total)
- Full knowledge base statistics (documents, entities, relationships by type)

---

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `/` | Focus global search bar |
| `Enter` | Send chat message |
| `Shift+Enter` | New line in chat input |
| `Esc` | Close modal / panel |

---

## Tips for getting the most out of NexusPKM

**Let the initial sync complete before exploring.** Entity extraction runs asynchronously — the knowledge graph continues building after documents are indexed. The graph explorer and chat answers improve as extraction processes more documents.

**Use specific entity names in chat.** "What's the status of the Hercules project?" will trigger a graph traversal for the Hercules Project entity in addition to a vector search, producing more connected results.

**The `/search` mode is good for raw results.** If the LLM's answer misses something you know is in your data, use `/search` to see the raw matching chunks directly.

**Contradiction alerts are a feature, not an error.** When the system flags conflicting information, it means your data contains a real ambiguity worth resolving. Use the resolution flow to keep your knowledge base accurate.

**Set `email_lookback_date` before your first Outlook sync.** Without it, the connector will attempt to import everything. A 1–2 year window is usually the right balance between coverage and initial sync time.
