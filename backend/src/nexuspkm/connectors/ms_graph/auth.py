"""Microsoft Graph OAuth2 authentication via Device Code Flow.

Handles token acquisition, encrypted storage, silent refresh, and
re-authentication prompting when the refresh token has expired.

Token storage layout:
    <token_dir>/token.key       — Fernet symmetric key (file permissions: 0o600)
    <token_dir>/ms_graph.json   — Fernet-encrypted MSAL SerializableTokenCache

Note: the private helpers ``_get_or_create_key``, ``_load_token_cache``, and
``_save_token_cache`` perform blocking filesystem I/O and must only be called
from within a ``run_in_executor`` closure, never directly from async code.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from cryptography.fernet import Fernet
from msal import PublicClientApplication, SerializableTokenCache
from pydantic import BaseModel
from typing_extensions import TypedDict

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# MSAL response shapes
# ---------------------------------------------------------------------------


class _DeviceFlowDict(TypedDict, total=True):
    """Required fields always present in MSAL's initiate_device_flow response."""

    user_code: str
    device_code: str
    verification_uri: str
    expires_in: int
    interval: int
    message: str


class _TokenResultDict(TypedDict, total=False):
    """Subset of the dict returned by MSAL token acquisition methods."""

    access_token: str
    token_type: str
    expires_in: int
    error: str
    error_description: str


# ---------------------------------------------------------------------------
# Public data models
# ---------------------------------------------------------------------------


class DeviceCodeInfo(BaseModel):
    """Human-readable device code flow initiation data."""

    user_code: str
    verification_uri: str
    expires_in: int
    message: str


# ---------------------------------------------------------------------------
# Auth class
# ---------------------------------------------------------------------------


class MicrosoftGraphAuth:
    """Manages Microsoft Graph OAuth2 authentication for a single user."""

    SCOPES = [
        "OnlineMeetingTranscript.Read",
        "OnlineMeeting.Read",
        "User.Read",
        "offline_access",
    ]

    def __init__(self, token_dir: Path) -> None:
        self._token_dir = token_dir
        self._key_file = token_dir / "token.key"
        self._cache_file = token_dir / "ms_graph.json"
        # Preserved across initiate_device_code_flow → poll_for_token to ensure
        # the same MSAL app instance (and matching cache) is used for both calls.
        self._pending_app: PublicClientApplication | None = None
        self._pending_cache: SerializableTokenCache | None = None

    # ------------------------------------------------------------------
    # Internal helpers  (sync — must only be called inside run_in_executor)
    # ------------------------------------------------------------------

    def _get_or_create_key(self) -> bytes:
        """Load the Fernet key from disk, generating it on first run.

        The key file is created atomically with 0o600 permissions to avoid a
        TOCTOU window where the key is transiently world-readable.
        ``FileExistsError`` from ``O_EXCL`` is handled by reading the existing
        key written by a concurrent caller.
        """
        if self._key_file.exists():
            return self._key_file.read_bytes()

        self._token_dir.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        try:
            fd = os.open(self._key_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
            logger.info("ms_graph_auth.key_generated", path=str(self._key_file))
        except FileExistsError:
            # Another process created the file between exists() and open().
            # Fall back to reading the key it wrote.
            key = self._key_file.read_bytes()
        return key

    def _load_token_cache(self) -> SerializableTokenCache:
        """Return a populated MSAL token cache, or an empty one if no file exists."""
        cache = SerializableTokenCache()
        if not self._cache_file.exists():
            return cache

        try:
            key = self._get_or_create_key()
            fernet = Fernet(key)
            encrypted = self._cache_file.read_bytes()
            serialized = fernet.decrypt(encrypted).decode()
            cache.deserialize(serialized)
        except Exception:
            logger.warning(
                "ms_graph_auth.cache_load_failed",
                path=str(self._cache_file),
                exc_info=True,
            )

        return cache

    def _save_token_cache(self, cache: SerializableTokenCache) -> None:
        """Encrypt the MSAL token cache and persist it to disk.

        Written via a temp file + atomic rename with 0o600 permissions.
        The temp file is cleaned up in a finally block if rename fails.
        """
        key = self._get_or_create_key()
        fernet = Fernet(key)
        serialized = cache.serialize()
        encrypted = fernet.encrypt(serialized.encode())
        self._token_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = self._cache_file.with_suffix(".tmp")
        fd = os.open(tmp_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(encrypted)
            tmp_file.rename(self._cache_file)
        except Exception:
            with contextlib.suppress(OSError):
                tmp_file.unlink(missing_ok=True)
            raise

    def _build_app(self) -> tuple[PublicClientApplication, SerializableTokenCache]:
        """Construct an MSAL PublicClientApplication with the loaded token cache.

        Returns a ``(app, cache)`` tuple so callers can save the same cache
        instance after token acquisition without unsafe casting.

        Reads ``MS_TENANT_ID`` and ``MS_CLIENT_ID`` from environment variables.

        Raises:
            ValueError: if either required environment variable is missing.
        """
        tenant_id = os.environ.get("MS_TENANT_ID")
        client_id = os.environ.get("MS_CLIENT_ID")

        if not tenant_id:
            raise ValueError("MS_TENANT_ID environment variable is required")
        if not client_id:
            raise ValueError("MS_CLIENT_ID environment variable is required")

        cache = self._load_token_cache()
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = PublicClientApplication(client_id, authority=authority, token_cache=cache)
        return app, cache

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Attempt a silent token acquisition using cached credentials.

        Returns:
            True if a valid access token was obtained silently.
            False if re-authentication via device code flow is required.
        """
        loop = asyncio.get_running_loop()

        def _silent_acquire() -> bool:
            app, cache = self._build_app()
            accounts = app.get_accounts()
            if not accounts:
                return False

            result: _TokenResultDict = app.acquire_token_silent(self.SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_token_cache(cache)
                logger.info("ms_graph_auth.silent_token_acquired")
                return True

            logger.info("ms_graph_auth.silent_token_failed_reauth_required")
            return False

        return await loop.run_in_executor(None, _silent_acquire)

    async def initiate_device_code_flow(self) -> tuple[DeviceCodeInfo, _DeviceFlowDict]:
        """Start a device code flow.

        Stores the MSAL app instance internally so that ``poll_for_token``
        can use the same instance, ensuring consistent cache state.

        Returns:
            A tuple of (DeviceCodeInfo, flow_dict). Pass flow_dict to
            ``poll_for_token()`` to complete authentication.
        """
        loop = asyncio.get_running_loop()

        def _initiate() -> tuple[DeviceCodeInfo, _DeviceFlowDict]:
            app, cache = self._build_app()
            # Store for reuse in poll_for_token
            self._pending_app = app
            self._pending_cache = cache
            flow: _DeviceFlowDict = app.initiate_device_flow(scopes=self.SCOPES)
            info = DeviceCodeInfo(
                user_code=flow["user_code"],
                verification_uri=flow["verification_uri"],
                expires_in=flow["expires_in"],
                message=flow["message"],
            )
            logger.info(
                "ms_graph_auth.device_flow_initiated",
                user_code=info.user_code,
                verification_uri=info.verification_uri,
            )
            return info, flow

        return await loop.run_in_executor(None, _initiate)

    async def poll_for_token(self, flow: _DeviceFlowDict) -> bool:
        """Block until the user authenticates or the flow expires.

        Reuses the MSAL app instance from ``initiate_device_code_flow`` when
        available, ensuring the resulting token is saved to the same cache.

        Args:
            flow: The flow dict returned by ``initiate_device_code_flow()``.

        Returns:
            True if authentication succeeded and the token was saved.
            False if authentication failed or was declined.
        """
        loop = asyncio.get_running_loop()

        def _blocking_poll() -> bool:
            if self._pending_app is not None and self._pending_cache is not None:
                app = self._pending_app
                cache = self._pending_cache
                self._pending_app = None
                self._pending_cache = None
            else:
                app, cache = self._build_app()

            result: _TokenResultDict = app.acquire_token_by_device_flow(flow)
            if "error" in result:
                logger.warning(
                    "ms_graph_auth.device_flow_failed",
                    error=result.get("error"),
                    description=result.get("error_description"),
                )
                return False

            self._save_token_cache(cache)
            logger.info("ms_graph_auth.device_flow_succeeded")
            return True

        return await loop.run_in_executor(None, _blocking_poll)

    async def get_access_token(self) -> str | None:
        """Return a current valid access token, or None if unavailable.

        Performs a silent refresh if needed. Does not initiate device code flow.
        """
        loop = asyncio.get_running_loop()

        def _get_token() -> str | None:
            app, cache = self._build_app()
            accounts = app.get_accounts()
            if not accounts:
                return None

            result: _TokenResultDict = app.acquire_token_silent(self.SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_token_cache(cache)
                return str(result["access_token"])

            return None

        return await loop.run_in_executor(None, _get_token)

    async def has_cached_account(self) -> bool:
        """Return True if a cached account exists.

        Note: a cached account does not guarantee a valid token — the token may
        need a silent refresh, which can fail if the refresh token has expired.
        Use ``get_access_token()`` when you need a confirmed valid token.
        """
        loop = asyncio.get_running_loop()

        def _check() -> bool:
            app, _ = self._build_app()
            return len(app.get_accounts()) > 0

        return await loop.run_in_executor(None, _check)
