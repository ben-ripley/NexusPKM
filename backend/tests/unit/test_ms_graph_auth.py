"""Unit tests for Microsoft Graph OAuth2 authentication module."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from msal import SerializableTokenCache

from nexuspkm.connectors.ms_graph.auth import (
    AuthFlowContext,
    DeviceCodeInfo,
    MicrosoftGraphAuth,
)

_SKIP_WINDOWS_PERMS = pytest.mark.skipif(
    sys.platform == "win32", reason="Unix file permissions not enforced on Windows"
)


@pytest.fixture
def token_dir(tmp_path: Path) -> Path:
    """Provide a temporary token directory."""
    d = tmp_path / ".tokens"
    d.mkdir()
    return d


def _mock_build(mock_app: MagicMock) -> tuple[MagicMock, SerializableTokenCache]:
    """Return a (mock_app, real_cache) tuple for patching _build_app.

    A real SerializableTokenCache is used so has_state_changed behaves correctly.
    """
    return mock_app, SerializableTokenCache()


def _make_auth_flow_context(mock_app: MagicMock, flow_dict: dict[str, object]) -> AuthFlowContext:
    """Build an AuthFlowContext with a mock app for use in poll_for_token tests."""
    from nexuspkm.connectors.ms_graph.auth import DeviceFlowDict

    flow = DeviceFlowDict(
        user_code=str(flow_dict.get("user_code", "X")),
        device_code=str(flow_dict.get("device_code", "d")),
        verification_uri=str(flow_dict.get("verification_uri", "https://example.com")),
        expires_in=int(flow_dict.get("expires_in", 900)),  # type: ignore[arg-type]
        interval=int(flow_dict.get("interval", 5)),  # type: ignore[arg-type]
        message=str(flow_dict.get("message", "msg")),
    )
    return AuthFlowContext(flow=flow, app=mock_app, cache=SerializableTokenCache())


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------


def test_get_or_create_key_generates_on_first_run(token_dir: Path) -> None:
    """Key file is created on first call and contains valid Fernet key bytes."""
    from cryptography.fernet import Fernet

    auth = MicrosoftGraphAuth(token_dir)
    key = auth._get_or_create_key()
    key_file = token_dir / "token.key"
    assert key_file.exists()
    Fernet(key)  # raises if invalid


def test_get_or_create_key_loads_existing_key(token_dir: Path) -> None:
    """Second call returns the same key without regenerating."""
    auth = MicrosoftGraphAuth(token_dir)
    key1 = auth._get_or_create_key()
    key2 = auth._get_or_create_key()
    assert key1 == key2


@_SKIP_WINDOWS_PERMS
def test_key_file_created_with_restricted_permissions(token_dir: Path) -> None:
    """token.key is created with 0o600 permissions (owner read/write only)."""
    auth = MicrosoftGraphAuth(token_dir)
    auth._get_or_create_key()
    mode = stat.S_IMODE((token_dir / "token.key").stat().st_mode)
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_get_or_create_key_handles_concurrent_creation(token_dir: Path) -> None:
    """FileExistsError from O_EXCL (concurrent create) falls back to reading the winner's key."""
    from cryptography.fernet import Fernet

    auth = MicrosoftGraphAuth(token_dir)

    winner_key = Fernet.generate_key()
    (token_dir / "token.key").write_bytes(winner_key)

    real_os_open = os.open

    def raise_file_exists(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes] | int,
        flags: int,
        mode: int = 0o666,
    ) -> int:
        if flags & os.O_EXCL:
            raise FileExistsError
        return real_os_open(path, flags, mode)

    with patch("nexuspkm.connectors.ms_graph.auth.os.open", side_effect=raise_file_exists):
        key = auth._get_or_create_key()

    assert key == winner_key


# ---------------------------------------------------------------------------
# Token cache persistence
# ---------------------------------------------------------------------------


def test_load_token_cache_returns_empty_when_no_file(token_dir: Path) -> None:
    """Loading cache when no file exists returns an empty cache without error."""
    auth = MicrosoftGraphAuth(token_dir)
    cache = auth._load_token_cache()
    assert isinstance(cache, SerializableTokenCache)


def test_save_and_load_token_cache_roundtrip(token_dir: Path) -> None:
    """Encrypted cache written to disk can be read back correctly."""
    auth = MicrosoftGraphAuth(token_dir)

    raw_cache_state = (
        '{"AccessToken": {}, "RefreshToken": {}, "IdToken": {}, "Account": {}, "AppMetadata": {}}'
    )
    cache = SerializableTokenCache()
    cache.deserialize(raw_cache_state)

    auth._save_token_cache(cache)
    assert (token_dir / "ms_graph.json").exists()

    loaded = auth._load_token_cache()
    assert loaded.serialize() == cache.serialize()


@_SKIP_WINDOWS_PERMS
def test_cache_file_created_with_restricted_permissions(token_dir: Path) -> None:
    """ms_graph.json is created with 0o600 permissions (owner read/write only)."""
    auth = MicrosoftGraphAuth(token_dir)
    auth._save_token_cache(SerializableTokenCache())
    mode = stat.S_IMODE((token_dir / "ms_graph.json").stat().st_mode)
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_save_token_cache_cleans_up_tmp_file_on_rename_failure(token_dir: Path) -> None:
    """If rename fails, the .tmp file is deleted and the exception re-raised."""
    auth = MicrosoftGraphAuth(token_dir)
    cache = SerializableTokenCache()

    with (
        patch(
            "nexuspkm.connectors.ms_graph.auth.Path.rename", side_effect=OSError("rename failed")
        ),
        pytest.raises(OSError, match="rename failed"),
    ):
        auth._save_token_cache(cache)

    tmp_file = token_dir / "ms_graph.tmp"
    assert not tmp_file.exists()


# ---------------------------------------------------------------------------
# _build_app() — env var validation
# ---------------------------------------------------------------------------


def test_build_app_raises_when_env_vars_missing(token_dir: Path) -> None:
    """Raises ValueError when MS_TENANT_ID or MS_CLIENT_ID are not set."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.dict("os.environ", {}, clear=True), pytest.raises(ValueError, match="MS_TENANT_ID"):
        auth._build_app()


def test_build_app_raises_when_client_id_missing(token_dir: Path) -> None:
    """Raises ValueError when MS_CLIENT_ID is missing (MS_TENANT_ID is present)."""
    auth = MicrosoftGraphAuth(token_dir)
    with (
        patch.dict("os.environ", {"MS_TENANT_ID": "tenant-123"}, clear=True),
        pytest.raises(ValueError, match="MS_CLIENT_ID"),
    ):
        auth._build_app()


def test_build_app_raises_on_invalid_tenant_id_format(token_dir: Path) -> None:
    """Raises ValueError when MS_TENANT_ID contains path-traversal characters."""
    auth = MicrosoftGraphAuth(token_dir)
    with (
        patch.dict(
            "os.environ",
            {"MS_TENANT_ID": "../../etc/passwd", "MS_CLIENT_ID": "client-id"},
            clear=True,
        ),
        pytest.raises(ValueError, match="invalid format"),
    ):
        auth._build_app()


# ---------------------------------------------------------------------------
# authenticate()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_returns_false_when_no_cached_accounts(token_dir: Path) -> None:
    """Returns False when cache contains no accounts (re-auth needed)."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = []
        mock_build.return_value = _mock_build(mock_app)
        result = await auth.authenticate()
    assert result is False


@pytest.mark.asyncio
async def test_authenticate_returns_true_on_silent_success(token_dir: Path) -> None:
    """Returns True when acquire_token_silent succeeds."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build, patch.object(auth, "_save_token_cache"):
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "tok123"}
        app, cache = _mock_build(mock_app)
        cache.has_state_changed = True  # type: ignore[assignment]
        mock_build.return_value = (app, cache)
        result = await auth.authenticate()
    assert result is True


@pytest.mark.asyncio
async def test_authenticate_returns_false_on_silent_failure(token_dir: Path) -> None:
    """Returns False when acquire_token_silent returns None (token expired, refresh failed)."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = None
        mock_build.return_value = _mock_build(mock_app)
        result = await auth.authenticate()
    assert result is False


@pytest.mark.asyncio
async def test_authenticate_raises_valueerror_when_env_vars_missing(token_dir: Path) -> None:
    """ValueError from missing env vars propagates through the executor in authenticate()."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.dict("os.environ", {}, clear=True), pytest.raises(ValueError, match="MS_TENANT_ID"):
        await auth.authenticate()


# ---------------------------------------------------------------------------
# initiate_device_code_flow()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_device_code_flow_returns_device_code_info(token_dir: Path) -> None:
    """Returns a DeviceCodeInfo and AuthFlowContext with human-readable fields."""
    auth = MicrosoftGraphAuth(token_dir)
    flow_dict: dict[str, object] = {
        "user_code": "ABCD1234",
        "device_code": "device-code-xyz",
        "verification_uri": "https://microsoft.com/devicelogin",
        "expires_in": 900,
        "interval": 5,
        "message": "Go to https://microsoft.com/devicelogin and enter ABCD1234",
    }
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.initiate_device_flow.return_value = flow_dict
        mock_build.return_value = _mock_build(mock_app)

        info, ctx = await auth.initiate_device_code_flow()

    assert isinstance(info, DeviceCodeInfo)
    assert isinstance(ctx, AuthFlowContext)
    assert info.user_code == "ABCD1234"
    assert info.verification_uri == "https://microsoft.com/devicelogin"
    assert info.expires_in == 900
    assert info.message == flow_dict["message"]


@pytest.mark.asyncio
async def test_initiate_device_code_flow_raises_on_msal_error(token_dir: Path) -> None:
    """RuntimeError is raised when MSAL returns an error from initiate_device_flow."""
    auth = MicrosoftGraphAuth(token_dir)
    error_response: dict[str, object] = {
        "error": "invalid_client",
        "error_description": "Application not found",
    }
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.initiate_device_flow.return_value = error_response
        mock_build.return_value = _mock_build(mock_app)

        with pytest.raises(RuntimeError, match="Application not found"):
            await auth.initiate_device_code_flow()


@pytest.mark.asyncio
async def test_initiate_device_code_flow_raises_valueerror_when_env_vars_missing(
    token_dir: Path,
) -> None:
    """ValueError from missing env vars propagates through executor in initiate_device_code_flow."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.dict("os.environ", {}, clear=True), pytest.raises(ValueError, match="MS_TENANT_ID"):
        await auth.initiate_device_code_flow()


# ---------------------------------------------------------------------------
# poll_for_token()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_for_token_returns_true_on_success_and_saves_cache(
    token_dir: Path,
) -> None:
    """Returns True and saves cache when MSAL returns a token dict."""
    auth = MicrosoftGraphAuth(token_dir)
    mock_app = MagicMock()
    mock_app.acquire_token_by_device_flow.return_value = {
        "access_token": "tok123",
        "token_type": "Bearer",
    }
    ctx = _make_auth_flow_context(mock_app, {})

    with patch.object(auth, "_save_token_cache") as mock_save:
        result = await auth.poll_for_token(ctx)

    assert result is True
    mock_save.assert_called_once_with(ctx._cache)


@pytest.mark.asyncio
async def test_poll_for_token_uses_context_app_not_fresh_build(token_dir: Path) -> None:
    """poll_for_token uses the app from AuthFlowContext; _build_app is never called."""
    auth = MicrosoftGraphAuth(token_dir)
    mock_app = MagicMock()
    mock_app.acquire_token_by_device_flow.return_value = {"access_token": "tok123"}
    ctx = _make_auth_flow_context(mock_app, {})

    with patch.object(auth, "_build_app") as mock_build, patch.object(auth, "_save_token_cache"):
        await auth.poll_for_token(ctx)

    mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_poll_for_token_returns_false_on_error(token_dir: Path) -> None:
    """Returns False when MSAL response contains an error key."""
    auth = MicrosoftGraphAuth(token_dir)
    mock_app = MagicMock()
    mock_app.acquire_token_by_device_flow.return_value = {
        "error": "authorization_declined",
        "error_description": "User declined",
    }
    ctx = _make_auth_flow_context(mock_app, {})

    result = await auth.poll_for_token(ctx)
    assert result is False


# ---------------------------------------------------------------------------
# get_access_token()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_access_token_returns_none_when_no_accounts(token_dir: Path) -> None:
    """Returns None when cache has no accounts."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = []
        mock_build.return_value = _mock_build(mock_app)
        result = await auth.get_access_token()
    assert result is None


@pytest.mark.asyncio
async def test_get_access_token_returns_token_when_silent_succeeds(token_dir: Path) -> None:
    """Returns the access_token string when silent acquisition succeeds."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build, patch.object(auth, "_save_token_cache"):
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "tok999"}
        app, cache = _mock_build(mock_app)
        cache.has_state_changed = True  # type: ignore[assignment]
        mock_build.return_value = (app, cache)
        result = await auth.get_access_token()
    assert result == "tok999"


@pytest.mark.asyncio
async def test_get_access_token_raises_valueerror_when_env_vars_missing(token_dir: Path) -> None:
    """ValueError from missing env vars propagates through the executor in get_access_token()."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.dict("os.environ", {}, clear=True), pytest.raises(ValueError, match="MS_TENANT_ID"):
        await auth.get_access_token()


# ---------------------------------------------------------------------------
# has_cached_account()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_cached_account_false_when_no_accounts(token_dir: Path) -> None:
    """Returns False when app cache has no accounts."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = []
        mock_build.return_value = _mock_build(mock_app)
        assert await auth.has_cached_account() is False


@pytest.mark.asyncio
async def test_has_cached_account_true_when_account_cached(token_dir: Path) -> None:
    """Returns True when at least one account is in the cache."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_build.return_value = _mock_build(mock_app)
        assert await auth.has_cached_account() is True


# ---------------------------------------------------------------------------
# ValueError propagation through run_in_executor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_for_token_valueerror_propagates_when_no_context_and_env_missing(
    token_dir: Path,
) -> None:
    """ValueError from _build_app propagates when poll_for_token falls back to building an app."""
    auth = MicrosoftGraphAuth(token_dir)
    # Use a real (empty) context but override its _app to raise ValueError
    mock_app = MagicMock()
    mock_app.acquire_token_by_device_flow.side_effect = ValueError("MS_TENANT_ID required")
    ctx = _make_auth_flow_context(mock_app, {})
    with pytest.raises(ValueError, match="MS_TENANT_ID"):
        await auth.poll_for_token(ctx)


# ---------------------------------------------------------------------------
# DeviceFlowDict and AuthFlowContext are public types
# ---------------------------------------------------------------------------


def test_public_types_are_exported() -> None:
    """AuthFlowContext and DeviceFlowDict are accessible from the public package."""
    from nexuspkm.connectors.ms_graph import AuthFlowContext as _AFC  # noqa: F401
    from nexuspkm.connectors.ms_graph import DeviceFlowDict as _DFD  # noqa: F401
