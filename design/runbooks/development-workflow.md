# NexusPKM Development Workflow

**Version:** 1.1
**Date:** 2026-03-16

## 1. Overview

NexusPKM follows a spec-driven, test-driven development process optimized for AI agent implementation with human oversight. This runbook defines the complete workflow from Jira issue to merged code.

## 2. Branch Naming Convention

```
feature/NXP-{issue-number}-{short-description}
```

Examples:
- `feature/NXP-42-llm-provider-abstraction`
- `feature/NXP-58-teams-connector`
- `feature/NXP-73-chat-websocket`

Rules:
- All lowercase
- Hyphens for word separation
- Short description max 5 words
- One branch per Jira story or subtask

## 3. Per-Task Development Workflow

### Step 1: Read the Jira Issue

- Fetch the assigned Jira issue via MCP
- Read: title, description, acceptance criteria, dependencies, spec reference
- Verify all dependencies are marked "Done"
- If dependencies are not complete → mark issue as "Blocked" and move to next available issue

### Step 2: Transition to In Progress and Assign

- Transition the issue to **In Progress**
- Assign to **Ben Ripley** (`557058:1765a43f-ad6f-42f2-a153-efe410493e6c`)

### Step 3: Clarify Requirements (only if uncertain)

- If and only if requirements are ambiguous or incomplete, ask the user before proceeding
- Do not ask about things that are clearly specified in the issue or design docs

### Step 4: Plan for Non-Trivial Work

- If the task requires creating or modifying more than a few files, enter **plan mode** first
- Present a plan listing: files to create/modify, test files, key design decisions, risks
- Get user approval before writing any code

### Step 5: Update Design Docs if Needed

- If the work introduces functionality not covered in `design/` (adrs/, architecture/, specs/), update the relevant design documentation before implementing

### Step 6: Create Feature Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/NXP-{id}-{description}
```

### Step 7: Write Tests First (TDD — Red)

Write failing tests BEFORE any implementation code:

**Backend (pytest):**
```bash
backend/tests/unit/test_{feature}.py
backend/tests/integration/test_{feature}_integration.py
```

**Frontend (vitest):**
```bash
frontend/tests/{feature}.test.tsx
```

Test requirements:
- Unit tests for all business logic, models, and utilities
- Integration tests for API endpoints and service interactions
- Edge cases: empty input, invalid data, error conditions
- Mock external dependencies (LLM, Graph API, etc.)

Verify tests **fail** before writing implementation.

### Step 8: Implement the Feature (TDD — Green)

- Write minimum code to make tests pass
- Follow existing patterns and conventions
- Reference the feature spec for data models, API contracts, and behavior
- Keep changes scoped to the issue — no unrelated refactoring

### Step 9: Refactor (TDD — Refactor)

- Clean up code for quality without changing behavior
- Re-run all tests to confirm nothing regressed

### Step 10: Review

Before committing, verify:
```bash
# Backend
cd backend && ruff check . && ruff format --check .
cd backend && mypy src/
cd backend && pytest

# Frontend
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run
```

If the application can be started, run it and verify integration behavior manually.

### Step 11: Run Local AI Review

Before committing, run the AI reviewer against the local diff to catch issues early:

```bash
python scripts/ai_review.py --local
```

Requires `AWS_DEFAULT_REGION` to be set (and optionally `BEDROCK_MODEL_ID`).
Does **not** require `REPO`, `PR_NUMBER`, or `GITHUB_TOKEN` — it diffs the current branch
against `origin/main` and prints the review to stdout.

- Address any **Critical** findings before committing.
- Use judgement on **Warnings** — fix or note in the commit message.
- **Info** items are optional.

This avoids the push → PR → wait → fix → push cycle for issues Claude would catch anyway.

### Step 12: Commit Locally

```bash
git add {specific files}
git commit -m "feat(NXP-{id}): {short description}

{One or two sentences summarizing what the change does and why.}"
```

Commit message rules:
- Include the Jira key: `feat(NXP-{id}):`, `fix(NXP-{id}):`, `chore(NXP-{id}):`, etc.
- No `Co-Authored-By` line
- Stage specific files — do not use `git add -A` blindly

### Step 13: Create Pull Request

```bash
git push -u origin feature/NXP-{id}-{description}

gh pr create --title "NXP-{id}: {description}" --body "$(cat <<'EOF'
## Summary
- {bullet points of key changes}

## Spec Reference
- {link to spec file in design/specs/}

## Jira Issue
- NXP-{id}

## Test Plan
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed
- [ ] Documentation updated

## Checklist
- [ ] Tests written before implementation (TDD)
- [ ] All acceptance criteria met
- [ ] No unrelated changes included
EOF
)"
```

### Step 14: Transition Jira to In Review

- Transition the Jira issue to **In Review** (transition ID `31`)

### Step 15: User Reviews and Merges

- User reviews the PR
- If approved → merge to `main`
- If changes requested → address feedback, push, return to Step 10

### Step 16: AI Review (Automated)

The PR triggers the `ai-review.yml` GitHub Action:
1. Action fetches the PR diff
2. Claude API reviews for: architecture compliance, security, bugs, test coverage, spec adherence
3. Review posted as a PR comment
4. If critical issues found → fix and push (returns to Step 10)

### Step 17: Mark Jira Issue Complete

After PR is merged:
- Transition Jira issue to **Done** (transition ID `41`)
- Update any dependent issues that are now unblocked

## 4. TDD Process Detail

### Backend TDD Cycle

```
1. Write a failing test
   → pytest backend/tests/unit/test_feature.py -x
   → Verify it FAILS (red)

2. Write minimum code to pass
   → pytest backend/tests/unit/test_feature.py -x
   → Verify it PASSES (green)

3. Refactor if needed
   → pytest backend/tests/ -x
   → Verify ALL tests still pass

4. Repeat for next requirement
```

### Frontend TDD Cycle

```
1. Write a failing test
   → npx vitest run tests/feature.test.tsx
   → Verify it FAILS

2. Write minimum code to pass
   → Verify it PASSES

3. Refactor
   → npx vitest run
   → Verify ALL tests pass
```

### What to Test

| Layer | Test | Scope |
|---|---|---|
| Models | Pydantic validation, serialization | Unit |
| Services | Business logic, data transformation | Unit |
| API endpoints | Request/response, status codes | Integration |
| Connectors | Data fetching, transformation | Unit (mocked) |
| Components | Rendering, user interaction | Unit |
| Pages | Full page rendering with mock data | Integration |

## 5. Git Worktree Usage

Worktrees allow parallel development of multiple features:

### Create a Worktree

```bash
# From main repo
git worktree add ../NexusPKM-feature-42 -b feature/NXP-42-description
cd ../NexusPKM-feature-42
```

### List Active Worktrees

```bash
git worktree list
```

### Remove a Worktree (after merge)

```bash
git worktree remove ../NexusPKM-feature-42
```

### Important Notes

- Each worktree has its own `data/` directory (gitignored)
- Each worktree needs its own `config/` files (copied from examples)
- Do NOT share `data/` directories between worktrees
- The `design/` directory is shared via git — changes to specs should be committed to `main`

## 6. Handling Blocked Dependencies

When an issue depends on an incomplete issue:
1. Mark the blocked issue as "Blocked" in Jira
2. Add a comment linking to the blocking issue
3. Move to the next unblocked issue in the backlog
4. When the blocking issue is completed → unblock and resume

## 7. Definition of Done Checklist

An issue is "Done" when ALL of the following are true:

- [ ] All acceptance criteria from the Jira issue are met
- [ ] Tests written BEFORE implementation (TDD)
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] No regressions in existing tests
- [ ] Feature documented in `docs/`
- [ ] PR submitted with spec reference and test plan
- [ ] AI review passes with no critical findings
- [ ] PR reviewed and merged by user
- [ ] Jira issue transitioned to "Done"
- [ ] No TODO comments left in code (except tracked Jira issues)

## 8. CI Pipeline Checks

Every PR must pass:

| Check | Tool | Failure Action |
|---|---|---|
| Backend lint | ruff | Fix lint errors |
| Backend types | mypy | Fix type errors |
| Backend tests | pytest | Fix failing tests |
| Frontend lint | eslint | Fix lint errors |
| Frontend types | tsc --noEmit | Fix type errors |
| Frontend tests | vitest | Fix failing tests |
| Frontend build | vite build | Fix build errors |
| AI review | Claude API | Address critical findings |
