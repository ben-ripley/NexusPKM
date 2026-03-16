# ADR-008: CI/CD and PR Review Process

**Status:** Accepted
**Date:** 2026-03-16
**Deciders:** Project Team

## Context

NexusPKM uses AI agents for implementation. To maintain code quality and catch issues before merge, we need:
- Automated CI (lint, test, build) on every PR
- AI-powered code review covering architecture, security, and correctness
- A path toward fully autonomous development (merge without human intervention)

## Decision

### CI Pipeline (GitHub Actions)

On every PR to `main`:

1. **Backend CI**: lint (ruff), type check (mypy), test (pytest), coverage report
2. **Frontend CI**: lint (eslint), type check (tsc), test (vitest), build (vite build)
3. **AI Review**: custom GitHub Action using Claude API

### Custom AI Review Action

A GitHub Action (`ai-review.yml`) that:

1. Triggers on PR creation and update
2. Fetches the PR diff via `gh api`
3. Sends the diff to Claude API with a structured review prompt
4. Reviews for:
   - **Architecture compliance**: does the code follow ADRs and established patterns?
   - **Security**: OWASP top 10 vulnerabilities (injection, XSS, auth issues, secrets in code)
   - **Bug detection**: logic errors, race conditions, error handling gaps
   - **Test coverage**: are new code paths tested? Are edge cases covered?
   - **Spec adherence**: does the implementation match the referenced feature spec?
5. Posts findings as a PR comment with severity levels (critical/warning/info)
6. Sets a check status (pass/fail based on critical findings)

### Implementation Approach

```yaml
# .github/workflows/ai-review.yml
name: AI Code Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Get PR diff
        run: gh pr diff ${{ github.event.pull_request.number }} > diff.txt
      - name: Run Claude review
        run: python scripts/ai_review.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - name: Post review comment
        run: gh pr comment ${{ github.event.pull_request.number }} --body-file review.md
```

### Future: Autonomous Merge Loop

Once confidence in the AI review is established:
1. If AI review passes with no critical findings AND all CI checks pass → auto-merge
2. Configurable: can require human approval for specific labels (e.g., `security-sensitive`)
3. Evaluate CodeRabbit and Ellipsis as supplementary reviewers

## Consequences

### Positive
- Every PR gets a consistent, thorough review regardless of human availability
- Security issues caught before merge
- Spec adherence is verified automatically
- Path toward full autonomy is built into the process from day one

### Negative
- Claude API costs per review (mitigated: diffs are typically small)
- AI review may produce false positives that slow down merges
- Custom action requires maintenance

### Risks
- AI review may miss subtle bugs that a human would catch — treat as a supplement, not a replacement, during the initial phase
- API rate limits could delay reviews on high-volume PR days
