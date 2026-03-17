#!/usr/bin/env python3
"""AI PR reviewer — fetches the diff, sends to Claude, posts a structured review comment."""

import json
import os
import sys
import urllib.error
import urllib.request

import anthropic

MAX_DIFF_CHARS = 100_000
# Bedrock cross-region inference profile ID — override via BEDROCK_MODEL_ID env var if needed
DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6-20251101-v1:0"

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


def get_pr_diff(repo: str, pr_number: str, token: str) -> str:
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def post_pr_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    data = json.dumps({"body": body}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    urllib.request.urlopen(req)


def main() -> None:
    repo = os.environ["REPO"]
    pr_number = os.environ["PR_NUMBER"]
    github_token = os.environ["GITHUB_TOKEN"]
    model = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL)

    print(f"Fetching diff for PR #{pr_number} in {repo}...")
    try:
        diff = get_pr_diff(repo, pr_number, github_token)
    except urllib.error.HTTPError as exc:
        print(f"Failed to fetch PR diff: {exc}", file=sys.stderr)
        sys.exit(1)

    if not diff.strip():
        print("Empty diff — nothing to review.")
        return

    if len(diff) > MAX_DIFF_CHARS:
        print(f"Diff is {len(diff)} chars; truncating to {MAX_DIFF_CHARS}.")
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[diff truncated due to size]"

    print(f"Sending {len(diff)} chars to Claude via Bedrock ({model})...")
    # AnthropicBedrock reads AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    # from the environment automatically (standard boto3 credential chain).
    client = anthropic.AnthropicBedrock()
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": REVIEW_PROMPT.format(diff=diff)}],
    )

    first_block = message.content[0]
    if not isinstance(first_block, anthropic.types.TextBlock):
        print("Unexpected response type from Claude.", file=sys.stderr)
        sys.exit(1)
    review_text = first_block.text
    comment = f"<!-- ai-review -->\n{review_text}\n\n*🤖 AI review by [{model}](https://anthropic.com) via AWS Bedrock*"

    print("Posting review comment to PR...")
    try:
        post_pr_comment(repo, pr_number, github_token, comment)
    except urllib.error.HTTPError as exc:
        print(f"Failed to post comment: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
