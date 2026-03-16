# ADR-007: Development Process

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Project Team

## Context

NexusPKM will be developed primarily by AI agents (Claude Code) with human oversight limited to:
1. Approving generated implementation plans
2. Reviewing and merging pull requests

This requires maximum clarity in specifications and a highly structured workflow that minimizes ambiguity.

## Decision

Adopt a **spec-driven, test-driven development process** with the following workflow:

### Per-Task Workflow

1. **Read**: Agent reads the Jira issue (Epic > Story > SubTask)
2. **Plan**: Agent generates an implementation plan and interviews the user if requirements are insufficient
3. **Branch**: Create a feature branch (`feature/NXP-{issue-number}-{short-description}`)
4. **Test**: Write tests first (TDD) — pytest for backend, vitest for frontend
5. **Implement**: Write the code to make tests pass
6. **Document**: Add/update documentation in `docs/`
7. **PR**: Submit a pull request with summary, test plan, and spec reference
8. **Review**: GitHub Action triggers AI review (architecture, security, bugs, test coverage, spec adherence)
9. **Merge**: User reviews and merges the PR
10. **Close**: Jira issue is marked complete

### Specification Hierarchy

- **ADRs** (`design/adrs/`): Architectural decisions — the "why" behind technology and pattern choices
- **Feature Specs** (`design/specs/`): Detailed functional specs — the "what" for each feature
- **Implementation Plan** (`design/implementation-plan.md`): Jira-ready issues — the "how" and "when"
- **User Docs** (`docs/`): End-user documentation — the "how to use"

### Testing Strategy

| Layer | Tool | Coverage Target |
|---|---|---|
| Backend unit tests | pytest | All business logic, models, utilities |
| Backend integration tests | pytest + httpx | API endpoints, connector mocks, engine operations |
| Frontend unit tests | vitest + Testing Library | Components, hooks, utilities |
| Frontend integration tests | vitest | Page-level rendering, API interactions |
| E2E tests | Playwright (future) | Critical user flows |

### Branch Strategy

- `main` — stable, deployable at all times
- `feature/NXP-{id}-{description}` — one branch per Jira story/subtask
- Branch protection on `main`: require PR, require passing CI, require AI review
- No direct commits to `main`

### Jira Workflow

- **Epic**: high-level feature area (e.g., "Knowledge Engine", "V1 Connectors")
- **Story**: implementable feature unit (e.g., "Implement Teams Transcript Connector")
- **SubTask**: atomic work item (e.g., "Implement MS Graph OAuth2 authentication")
- Issues include: description, acceptance criteria, dependencies, complexity estimate, spec reference

## Consequences

### Positive
- AI agents have unambiguous instructions for every task
- TDD ensures code correctness from the start
- Every feature is traceable: Jira issue → spec → branch → PR → docs
- Structured workflow enables progressive automation toward full autonomy

### Negative
- High upfront specification effort before any code is written
- Rigid process may slow down exploration and prototyping
- Jira issue management adds overhead

### Risks
- Specs may not anticipate all implementation challenges — agents should flag blockers rather than guessing
- TDD for AI-heavy features (entity extraction, chat) requires carefully designed test fixtures
