"""Tests for scripts/ai_review.py."""

from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

import ai_review


# ---------------------------------------------------------------------------
# get_pr_diff
# ---------------------------------------------------------------------------


def test_get_pr_diff_returns_diff_text() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, text="diff --git a/foo b/foo\n+added line")
    )
    client = httpx.Client(transport=transport)
    result = ai_review.get_pr_diff(client, "owner/repo", "42")
    assert result == "diff --git a/foo b/foo\n+added line"


def test_get_pr_diff_raises_on_http_error() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(404))
    client = httpx.Client(transport=transport)
    with pytest.raises(httpx.HTTPStatusError):
        ai_review.get_pr_diff(client, "owner/repo", "42")


# ---------------------------------------------------------------------------
# find_existing_review_comment
# ---------------------------------------------------------------------------


def test_find_existing_review_comment_returns_id_when_found() -> None:
    comments = [
        {"id": 1, "body": "some other comment"},
        {"id": 2, "body": f"{ai_review.AI_REVIEW_MARKER}\nreview body"},
    ]
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json=comments)
    )
    client = httpx.Client(transport=transport)
    result = ai_review.find_existing_review_comment(client, "owner/repo", "42")
    assert result == 2


def test_find_existing_review_comment_returns_none_when_absent() -> None:
    comments = [{"id": 1, "body": "just a regular comment"}]
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json=comments)
    )
    client = httpx.Client(transport=transport)
    result = ai_review.find_existing_review_comment(client, "owner/repo", "42")
    assert result is None


# ---------------------------------------------------------------------------
# upsert_pr_comment
# ---------------------------------------------------------------------------


def test_upsert_pr_comment_patches_existing_comment() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    with patch.object(ai_review, "find_existing_review_comment", return_value=99):
        ai_review.upsert_pr_comment(client, "owner/repo", "42", "new body")

    assert len(calls) == 1
    assert calls[0].method == "PATCH"
    assert "/comments/99" in str(calls[0].url)


def test_upsert_pr_comment_posts_new_comment_when_none_exists() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json={})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    with patch.object(ai_review, "find_existing_review_comment", return_value=None):
        ai_review.upsert_pr_comment(client, "owner/repo", "42", "new body")

    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert "/issues/42/comments" in str(calls[0].url)


# ---------------------------------------------------------------------------
# main() — integration paths
# ---------------------------------------------------------------------------


def test_main_exits_early_on_empty_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")

    with (
        patch.object(ai_review, "get_pr_diff", return_value="   "),
        patch.object(ai_review, "upsert_pr_comment") as mock_upsert,
        patch("anthropic.AnthropicBedrock"),
    ):
        ai_review.main()

    mock_upsert.assert_not_called()


def test_main_truncates_large_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")

    large_diff = "x" * (ai_review.MAX_DIFF_CHARS + 1000)

    mock_message = MagicMock()
    mock_message.stop_reason = "end_turn"
    mock_message.content = [MagicMock(spec=["text", "__class__"])]
    mock_message.content[0].__class__ = anthropic.types.TextBlock
    mock_message.content[0].text = "review text"

    captured: list[str] = []

    def fake_upsert(
        _client: httpx.Client, _repo: str, _pr: str, body: str
    ) -> None:
        captured.append(body)

    with (
        patch.object(ai_review, "get_pr_diff", return_value=large_diff),
        patch.object(ai_review, "upsert_pr_comment", side_effect=fake_upsert),
        patch("anthropic.AnthropicBedrock") as mock_bedrock,
    ):
        mock_bedrock.return_value.messages.create.return_value = mock_message
        ai_review.main()

    # The prompt sent to Claude must contain the truncation notice
    call_args = mock_bedrock.return_value.messages.create.call_args
    prompt_content = call_args.kwargs["messages"][0]["content"]
    assert "[diff truncated due to size]" in prompt_content


def test_main_uses_default_model_when_env_var_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "")  # empty — should fall back

    mock_message = MagicMock()
    mock_message.stop_reason = "end_turn"
    mock_message.content = [MagicMock(spec=["text", "__class__"])]
    mock_message.content[0].__class__ = anthropic.types.TextBlock
    mock_message.content[0].text = "review"

    with (
        patch.object(ai_review, "get_pr_diff", return_value="some diff"),
        patch.object(ai_review, "upsert_pr_comment"),
        patch("anthropic.AnthropicBedrock") as mock_bedrock,
    ):
        mock_bedrock.return_value.messages.create.return_value = mock_message
        ai_review.main()

    call_args = mock_bedrock.return_value.messages.create.call_args
    assert call_args.kwargs["model"] == ai_review.DEFAULT_MODEL


def test_main_exits_on_bedrock_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")

    exc = anthropic.APIConnectionError(
        message="connection failed",
        request=httpx.Request("POST", "https://bedrock.amazonaws.com"),
    )

    with (
        patch.object(ai_review, "get_pr_diff", return_value="some diff"),
        patch("anthropic.AnthropicBedrock") as mock_bedrock,
    ):
        mock_bedrock.return_value.messages.create.side_effect = exc
        with pytest.raises(SystemExit) as exc_info:
            ai_review.main()

    assert exc_info.value.code == 1
