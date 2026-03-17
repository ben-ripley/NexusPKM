#!/usr/bin/env python3
"""AI PR reviewer — fetches the diff, sends to Claude via Bedrock, upserts a review comment.

The script posts exactly one comment per PR, identified by the AI_REVIEW_MARKER sentinel.
On subsequent pushes the existing comment is edited rather than creating a new one.
"""

import os
import sys

import anthropic
import httpx
import structlog

MAX_DIFF_CHARS = 100_000
MAX_TOKENS = 4096
# Bedrock cross-region inference profile (us.* prefix) — override via BEDROCK_MODEL_ID env var
DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
# HTML sentinel used to find and update the existing review comment.
# GitHub renders <!-- … --> as invisible, but the API still returns it in `body`,
# so this works as a unique marker for locating and PATCHing the existing comment.
AI_REVIEW_MARKER = "<!-- ai-review -->"
# GitHub REST API base URL — override for GitHub Enterprise via GITHUB_API_URL env var
GITHUB_API_BASE = os.environ.get("GITHUB_API_URL", "https://api.github.com")

log = structlog.get_logger()

REVIEW_PROMPT = """\
You are reviewing a pull request for NexusPKM, a Python/TypeScript personal knowledge \
management application.

Review the diff below for issues in these categories:

**Critical** — must be fixed before merge:
- Security vulnerabilities (hardcoded secrets, injection, XSS, etc.)
- Data-loss or correctness bugs
- Broken or missing tests for new behaviour
- Synchronous I/O in the Python backend

**Warning** — should be addressed:
- Architecture violations (e.g. `any` in TypeScript, `# type: ignore`, `print()` instead of \
structlog)
- Missing error handling for realistic failure modes
- Performance issues
- Spec non-compliance

**Info** — minor suggestions:
- Style, naming, or readability improvements
- Documentation gaps

Project conventions:
- Backend: Python 3.12, FastAPI (all handlers async), Pydantic v2, structlog, ruff + mypy strict
- Frontend: TypeScript (no `any`), React 18, shadcn/ui only, Zustand stores, TanStack Query hooks
- TDD: tests written before implementation
- Secrets via env vars only — never in config files or source code
- No hardcoded URLs

Format your response exactly as follows:

## AI Review

### Critical Issues
<issues or "None">

### Warnings
<issues or "None">

### Info
<suggestions or "None">

### Summary
<one or two sentences>

---
PR diff:

{diff}
"""


def get_pr_diff(client: httpx.Client, repo: str, pr_number: str) -> str:
    response = client.get(
        f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}",
        headers={"Accept": "application/vnd.github.v3.diff"},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def find_existing_review_comment(
    client: httpx.Client, repo: str, pr_number: str
) -> int | None:
    """Return the comment ID of an existing AI review comment, or None."""
    response = client.get(
        f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments",
        params={"per_page": 100},
        timeout=30,
    )
    response.raise_for_status()
    for comment in response.json():
        if AI_REVIEW_MARKER in comment["body"]:
            return int(comment["id"])
    return None


def upsert_pr_comment(
    client: httpx.Client, repo: str, pr_number: str, body: str
) -> None:
    """Create the review comment, or update it if one already exists."""
    comment_id = find_existing_review_comment(client, repo, pr_number)
    if comment_id is not None:
        log.info("updating_existing_comment", comment_id=comment_id)
        response = client.patch(
            f"{GITHUB_API_BASE}/repos/{repo}/issues/comments/{comment_id}",
            json={"body": body},
            timeout=30,
        )
    else:
        log.info("creating_new_comment")
        response = client.post(
            f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments",
            json={"body": body},
            timeout=30,
        )
    response.raise_for_status()


def main() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ]
    )

    repo = os.environ["REPO"]
    pr_number = os.environ["PR_NUMBER"]
    github_token = os.environ["GITHUB_TOKEN"]
    model = os.environ.get("BEDROCK_MODEL_ID") or DEFAULT_MODEL

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(headers=headers) as http:
        log.info("fetching_diff", repo=repo, pr=pr_number)
        try:
            diff = get_pr_diff(http, repo, pr_number)
        except httpx.HTTPStatusError as exc:
            log.error("diff_fetch_failed", status=exc.response.status_code)
            sys.exit(1)

        if not diff.strip():
            log.info("empty_diff_skipping")
            return

        if len(diff) > MAX_DIFF_CHARS:
            log.info("diff_truncated", original=len(diff), limit=MAX_DIFF_CHARS)
            diff = diff[:MAX_DIFF_CHARS] + "\n\n[diff truncated due to size]"

        log.info("sending_to_claude", chars=len(diff), model=model)
        bedrock = anthropic.AnthropicBedrock(timeout=60.0)
        try:
            message = bedrock.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": REVIEW_PROMPT.format(diff=diff)}],
            )
        except anthropic.APIError as exc:
            log.error("bedrock_api_error", error=str(exc))
            sys.exit(1)

        if message.stop_reason == "max_tokens":
            log.warning("response_truncated_by_max_tokens", model=model)

        first_block = message.content[0]
        if not isinstance(first_block, anthropic.types.TextBlock):
            log.error("unexpected_response_type", type=type(first_block).__name__)
            sys.exit(1)

        review_text = first_block.text
        comment = (
            f"{AI_REVIEW_MARKER}\n"
            f"{review_text}\n\n"
            f"*🤖 AI review by [{model}](https://anthropic.com) via AWS Bedrock*"
        )

        log.info("upserting_review_comment")
        try:
            upsert_pr_comment(http, repo, pr_number, comment)
        except httpx.HTTPStatusError as exc:
            log.error("comment_upsert_failed", status=exc.response.status_code)
            sys.exit(1)

    log.info("review_complete")


if __name__ == "__main__":
    main()
