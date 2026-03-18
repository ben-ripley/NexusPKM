# Phase 0 — Project Infrastructure & DevOps Setup

**Jira Epic:** NXP-1
**Dependencies:** None

Set up the development environment, repository, CI/CD, and project management tooling.

---

## Stories

| Jira Key | Title | Subtasks |
|----------|-------|----------|
| NXP-10 | Configure Development Environment | NXP-16, NXP-17 |
| NXP-11 | Create GitHub Repository | NXP-18, NXP-19 |
| NXP-12 | Set Up Python Backend Project | NXP-20, NXP-21 |
| NXP-13 | Set Up Frontend Project | NXP-22 |
| NXP-14 | Create CI/CD Pipeline | NXP-23, NXP-24 |
| NXP-15 | Set Up Jira Project | NXP-25 |

## Subtasks

| Jira Key | Title | Parent |
|----------|-------|--------|
| NXP-16 | Create Claude Code Settings | NXP-10 |
| NXP-17 | Create CLAUDE.md Project Guide | NXP-10 |
| NXP-18 | Initialize Repository and Monorepo Structure | NXP-11 |
| NXP-19 | Configure Branch Protection | NXP-11 |
| NXP-20 | Initialize Python Project with uv | NXP-12 |
| NXP-21 | Configure Linting and Type Checking | NXP-12 |
| NXP-22 | Initialize Vite + React + TypeScript Project | NXP-13 |
| NXP-23 | Create CI Workflow | NXP-14 |
| NXP-24 | Create AI Review GitHub Action | NXP-14 |
| NXP-25 | Create Jira Project and Configure | NXP-15 |

## Key Outputs

- `.claude/settings.json`, `CLAUDE.md` — Claude Code configuration
- `backend/pyproject.toml` — Python project with FastAPI, uv, ruff, mypy
- `frontend/package.json` — React + TypeScript + Tailwind + shadcn/ui + Vite
- `.github/workflows/ci.yml` — lint, type check, test for both layers
- `.github/workflows/ai-review.yml` — automated PR review via Claude/Bedrock
- `scripts/ai_review.py` — AI review script (local and PR modes)
