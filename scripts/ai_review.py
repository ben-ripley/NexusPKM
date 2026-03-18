#!/usr/bin/env python3
"""AI PR reviewer — fetches the diff, sends to Claude via Bedrock, upserts a review comment.

The script posts exactly one comment per PR, identified by the AI_REVIEW_MARKER sentinel.
On subsequent pushes the existing comment is edited rather than creating a new one.

Local mode (--local):
    Diffs the current branch against origin/main and prints the review to stdout.
    Requires only AWS_DEFAULT_REGION (and optionally BEDROCK_MODEL_ID) to be set.
    Use this before creating a PR to catch issues early.

PR mode (default):
    Fetches the diff from the GitHub API and upserts a review comment on the PR.
    Requires REPO, PR_NUMBER, GITHUB_TOKEN, and AWS_DEFAULT_REGION.
"""

import argparse
import os
import subprocess
import sys

import anthropic
import httpx
import structlog

MAX_DIFF_CHARS = 100_000
MAX_TOKENS = 8192
# Bedrock cross-region inference profile (us.* prefix) — override via BEDROCK_MODEL_ID env var
DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
# HTML sentinel used to find and update the existing review comment.
# GitHub renders <!-- … --> as invisible, but the API still returns it in `body`,
# so this works as a unique marker for locating and PATCHing the existing comment.
AI_REVIEW_MARKER = "<!-- ai-review -->"
# GitHub REST API base URL — override for GitHub Enterprise via GITHUB_API_URL env var.
# Tests can override this with monkeypatch.setattr(ai_review, "GITHUB_API_BASE", ...).
GITHUB_API_BASE = os.environ.get("GITHUB_API_URL", "https://api.github.com")

# structlog.get_logger() returns a lazy proxy; processors are only applied when a log
# method is invoked, so this is safe to call before structlog.configure() in main().
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


def _require_env(name: str, default: str | None = None) -> str:
    """Return an env var value, falling back to default, or exit with a structured error."""
    value = os.environ.get(name) or default
    if not value:
        log.error("missing_required_env_var", name=name)
        sys.exit(1)
    return value


def _parse_next_link(link_header: str) -> str | None:
    """Extract the 'next' page URL from a GitHub Link response header, or return None.

    GitHub paginates list endpoints via RFC 5988 Link headers, e.g.:
    ``<https://api.github.com/...?page=2>; rel="next", <...>; rel="last"``
    """
    for part in link_header.split(","):
        url_part, _, rel_part = part.strip().partition(";")
        if rel_part.strip() == 'rel="next"':
            return url_part.strip().strip("<>")
    return None


def _truncate_diff(diff: str) -> str:
    """Truncate diff to MAX_DIFF_CHARS and append a notice if it was trimmed."""
    if len(diff) <= MAX_DIFF_CHARS:
        return diff
    log.info("diff_truncated", original=len(diff), limit=MAX_DIFF_CHARS)
    return diff[:MAX_DIFF_CHARS] + "\n\n[diff truncated due to size]"


def _call_claude(diff: str, model: str, aws_region: str) -> str:
    """Send diff to Claude via Bedrock and return the review text."""
    log.info("sending_to_claude", chars=len(diff), model=model)
    bedrock = anthropic.AnthropicBedrock(aws_region=aws_region, timeout=60.0)
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

    return first_block.text


def get_local_diff() -> str:
    """Return the git diff of the current branch against origin/main."""
    result = subprocess.run(
        ["git", "diff", "origin/main...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


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
    """Return the comment ID of an existing AI review comment, or None.

    Follows GitHub's Link-header pagination so that PRs with more than 100
    issue comments are handled correctly.  The GitHub API caps ``per_page``
    at 100; subsequent pages are discovered via the ``rel="next"`` Link header.
    """
    url: str | None = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    params: dict[str, int] | None = {"per_page": 100}
    while url:
        response = client.get(url, params=params, timeout=30)
        response.raise_for_status()
        for comment in response.json():
            if AI_REVIEW_MARKER in comment["body"]:
                return int(comment["id"])
        # The next-page URL from the Link header already includes all query params.
        url = _parse_next_link(response.headers.get("link", ""))
        params = None
    return None


def upsert_pr_comment(
    client: httpx.Client, repo: str, pr_number: str, body: str
) -> None:
    """Create the review comment, or update it if one already exists."""
    try:
        comment_id = find_existing_review_comment(client, repo, pr_number)
    except httpx.HTTPStatusError as exc:
        log.error("comment_list_failed", status=exc.response.status_code)
        sys.exit(1)
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="AI PR diff reviewer powered by Claude via AWS Bedrock"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "Review the local branch diff against origin/main and print to stdout. "
            "Requires AWS_DEFAULT_REGION. Does not need REPO/PR_NUMBER/GITHUB_TOKEN."
        ),
    )
    args = parser.parse_args(argv)

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ]
    )

    aws_region = _require_env("AWS_DEFAULT_REGION")
    model = _require_env("BEDROCK_MODEL_ID", DEFAULT_MODEL)

    if args.local:
        log.info("fetching_local_diff")
        try:
            diff = get_local_diff()
        except subprocess.CalledProcessError as exc:
            log.error("git_diff_failed", error=str(exc))
            sys.exit(1)

        if not diff.strip():
            log.info("empty_diff_skipping")
            return

        diff = _truncate_diff(diff)
        review_text = _call_claude(diff, model, aws_region)
        print(review_text)
        log.info("review_complete")
        return

    # PR mode
    repo = _require_env("REPO")
    pr_number = _require_env("PR_NUMBER")
    github_token = _require_env("GITHUB_TOKEN")

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

        diff = _truncate_diff(diff)
        review_text = _call_claude(diff, model, aws_region)

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
