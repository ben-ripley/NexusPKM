"""Unit tests for Microsoft Graph OAuth2 authentication module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexuspkm.connectors.ms_graph.auth import DeviceCodeInfo, MicrosoftGraphAuth


@pytest.fixture
def token_dir(tmp_path: Path) -> Path:
    """Provide a temporary token directory."""
    d = tmp_path / ".tokens"
    d.mkdir()
    return d


@pytest.fixture
def auth(token_dir: Path) -> MicrosoftGraphAuth:
    """MicrosoftGraphAuth instance with temp token dir."""
    return MicrosoftGraphAuth(token_dir)


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
    # Should be a valid Fernet key (32 bytes URL-safe base64 encoded → 44 chars)
    Fernet(key)  # raises if invalid


def test_get_or_create_key_loads_existing_key(token_dir: Path) -> None:
    """Second call returns the same key without regenerating."""
    auth = MicrosoftGraphAuth(token_dir)
    key1 = auth._get_or_create_key()
    key2 = auth._get_or_create_key()
    assert key1 == key2


# ---------------------------------------------------------------------------
# Token cache persistence
# ---------------------------------------------------------------------------


def test_load_token_cache_returns_empty_when_no_file(token_dir: Path) -> None:
    """Loading cache when no file exists returns an empty cache without error."""
    auth = MicrosoftGraphAuth(token_dir)
    cache = auth._load_token_cache()
    # An empty cache has no accounts
    from msal import SerializableTokenCache

    assert isinstance(cache, SerializableTokenCache)


def test_save_and_load_token_cache_roundtrip(token_dir: Path) -> None:
    """Encrypted cache written to disk can be read back correctly."""
    from msal import SerializableTokenCache

    auth = MicrosoftGraphAuth(token_dir)

    # Fake a populated cache by deserializing a known-good serialized state
    raw_cache_state = (
        '{"AccessToken": {}, "RefreshToken": {}, "IdToken": {}, "Account": {}, "AppMetadata": {}}'
    )
    cache = SerializableTokenCache()
    cache.deserialize(raw_cache_state)

    auth._save_token_cache(cache)
    assert (token_dir / "ms_graph.json").exists()

    loaded = auth._load_token_cache()
    assert loaded.serialize() == cache.serialize()


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
        mock_build.return_value = mock_app
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
        mock_build.return_value = mock_app
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
        mock_build.return_value = mock_app
        result = await auth.authenticate()
    assert result is False


# ---------------------------------------------------------------------------
# initiate_device_code_flow()
# ---------------------------------------------------------------------------


def test_initiate_device_code_flow_returns_device_code_info(token_dir: Path) -> None:
    """Returns a DeviceCodeInfo with human-readable fields and the raw flow dict."""
    auth = MicrosoftGraphAuth(token_dir)
    flow_dict = {
        "user_code": "ABCD1234",
        "verification_uri": "https://microsoft.com/devicelogin",
        "expires_in": 900,
        "message": "Go to https://microsoft.com/devicelogin and enter ABCD1234",
    }
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.initiate_device_flow.return_value = flow_dict
        mock_build.return_value = mock_app

        info, raw_flow = auth.initiate_device_code_flow()

    assert isinstance(info, DeviceCodeInfo)
    assert info.user_code == "ABCD1234"
    assert info.verification_uri == "https://microsoft.com/devicelogin"
    assert info.expires_in == 900
    assert info.message == flow_dict["message"]
    assert raw_flow is flow_dict


# ---------------------------------------------------------------------------
# poll_for_token()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_for_token_returns_true_on_success_and_saves_cache(
    token_dir: Path,
) -> None:
    """Returns True and saves cache when MSAL returns a token dict."""
    auth = MicrosoftGraphAuth(token_dir)
    flow = {"user_code": "ABCD1234"}
    token_result = {"access_token": "tok123", "token_type": "Bearer"}

    with (
        patch.object(auth, "_build_app") as mock_build,
        patch.object(auth, "_save_token_cache") as mock_save,
    ):
        mock_app = MagicMock()
        mock_app.acquire_token_by_device_flow.return_value = token_result
        mock_build.return_value = mock_app

        result = await auth.poll_for_token(flow)

    assert result is True
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_poll_for_token_returns_false_on_error(token_dir: Path) -> None:
    """Returns False when MSAL response contains an error key."""
    auth = MicrosoftGraphAuth(token_dir)
    flow = {"user_code": "ABCD1234"}
    error_result = {"error": "authorization_declined", "error_description": "User declined"}

    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.acquire_token_by_device_flow.return_value = error_result
        mock_build.return_value = mock_app

        result = await auth.poll_for_token(flow)

    assert result is False


# ---------------------------------------------------------------------------
# get_access_token()
# ---------------------------------------------------------------------------


def test_get_access_token_returns_none_when_no_accounts(token_dir: Path) -> None:
    """Returns None when cache has no accounts."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = []
        mock_build.return_value = mock_app
        result = auth.get_access_token()
    assert result is None


def test_get_access_token_returns_token_when_silent_succeeds(token_dir: Path) -> None:
    """Returns the access_token string when silent acquisition succeeds."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build, patch.object(auth, "_save_token_cache"):
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "tok999"}
        mock_build.return_value = mock_app
        result = auth.get_access_token()
    assert result == "tok999"


# ---------------------------------------------------------------------------
# is_authenticated()
# ---------------------------------------------------------------------------


def test_is_authenticated_false_when_no_accounts(token_dir: Path) -> None:
    """Returns False when app cache has no accounts."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = []
        mock_build.return_value = mock_app
        assert auth.is_authenticated() is False


def test_is_authenticated_true_when_account_cached(token_dir: Path) -> None:
    """Returns True when at least one account is in the cache."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.object(auth, "_build_app") as mock_build:
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_build.return_value = mock_app
        assert auth.is_authenticated() is True


# ---------------------------------------------------------------------------
# _build_app() — env var validation
# ---------------------------------------------------------------------------


def test_build_app_raises_when_env_vars_missing(token_dir: Path) -> None:
    """Raises ValueError when MS_TENANT_ID or MS_CLIENT_ID are not set."""
    auth = MicrosoftGraphAuth(token_dir)
    with patch.dict("os.environ", {}, clear=True), pytest.raises(ValueError, match="MS_TENANT_ID"):
        auth._build_app()
