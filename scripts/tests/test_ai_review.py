"""Tests for scripts/ai_review.py."""

from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest
from anthropic.types import TextBlock

import ai_review


# ---------------------------------------------------------------------------
# _parse_next_link
# ---------------------------------------------------------------------------


def test_parse_next_link_returns_url_when_present() -> None:
    header = '<https://api.github.com/repos/o/r/issues/1/comments?page=2>; rel="next", <https://api.github.com/repos/o/r/issues/1/comments?page=5>; rel="last"'
    result = ai_review._parse_next_link(header)
    assert result == "https://api.github.com/repos/o/r/issues/1/comments?page=2"


def test_parse_next_link_returns_none_when_absent() -> None:
    header = '<https://api.github.com/repos/o/r/issues/1/comments?page=1>; rel="first"'
    assert ai_review._parse_next_link(header) is None


def test_parse_next_link_returns_none_for_empty_header() -> None:
    assert ai_review._parse_next_link("") is None


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


def test_find_existing_review_comment_follows_pagination() -> None:
    """Marker on page 2 must still be found."""
    page2_url = f"{ai_review.GITHUB_API_BASE}/repos/owner/repo/issues/42/comments?page=2&per_page=100"

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(
                200,
                json=[{"id": 3, "body": f"{ai_review.AI_REVIEW_MARKER}\nold review"}],
            )
        return httpx.Response(
            200,
            json=[{"id": 1, "body": "comment"}, {"id": 2, "body": "other"}],
            headers={"link": f'<{page2_url}>; rel="next"'},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = ai_review.find_existing_review_comment(client, "owner/repo", "42")
    assert result == 3


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


def _mock_bedrock_message(text: str = "review text") -> MagicMock:
    """Return a realistic mock Bedrock message with an actual TextBlock."""
    mock_message = MagicMock()
    mock_message.stop_reason = "end_turn"
    mock_message.content = [TextBlock(text=text, type="text")]
    return mock_message


def test_main_exits_early_on_empty_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

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
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    large_diff = "x" * (ai_review.MAX_DIFF_CHARS + 1000)

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
        mock_bedrock.return_value.messages.create.return_value = _mock_bedrock_message()
        ai_review.main()

    call_args = mock_bedrock.return_value.messages.create.call_args
    prompt_content = call_args.kwargs["messages"][0]["content"]
    assert "[diff truncated due to size]" in prompt_content


def test_main_uses_default_model_when_env_var_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "")  # empty — should fall back to DEFAULT_MODEL

    with (
        patch.object(ai_review, "get_pr_diff", return_value="some diff"),
        patch.object(ai_review, "upsert_pr_comment"),
        patch("anthropic.AnthropicBedrock") as mock_bedrock,
    ):
        mock_bedrock.return_value.messages.create.return_value = _mock_bedrock_message()
        ai_review.main()

    call_args = mock_bedrock.return_value.messages.create.call_args
    assert call_args.kwargs["model"] == ai_review.DEFAULT_MODEL


def test_main_passes_aws_region_to_bedrock_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    with (
        patch.object(ai_review, "get_pr_diff", return_value="some diff"),
        patch.object(ai_review, "upsert_pr_comment"),
        patch("anthropic.AnthropicBedrock") as mock_bedrock,
    ):
        mock_bedrock.return_value.messages.create.return_value = _mock_bedrock_message()
        ai_review.main()

    mock_bedrock.assert_called_once_with(aws_region="eu-west-1", timeout=60.0)


def test_main_exits_when_aws_region_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        ai_review.main()

    assert exc_info.value.code == 1


def test_main_exits_on_bedrock_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

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
