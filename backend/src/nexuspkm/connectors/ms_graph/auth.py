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
from typing import TypedDict

import structlog
from cryptography.fernet import Fernet
from msal import PublicClientApplication, SerializableTokenCache
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# MSAL response shapes
# ---------------------------------------------------------------------------


class DeviceFlowDict(TypedDict, total=True):
    """Required fields always present in MSAL's initiate_device_flow response.

    This type is part of the public API — callers receive it from
    ``initiate_device_code_flow()`` and pass it back to ``poll_for_token()``.
    """

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
        # Note: calling initiate_device_code_flow a second time before polling
        # overwrites these fields; the abandoned flow's app/cache are released.
        self._pending_app: PublicClientApplication | None = None
        self._pending_cache: SerializableTokenCache | None = None

    # ------------------------------------------------------------------
    # Internal helpers  (sync — must only be called inside run_in_executor)
    # ------------------------------------------------------------------

    def _get_or_create_key(self) -> bytes:
        """Load the Fernet key from disk, generating it on first run.

        The key file is created atomically with ``O_CREAT | O_EXCL`` at mode
        0o600, so no TOCTOU window exists where the key is world-readable.

        Two TOCTOU edge cases are handled explicitly:
        - The fast-path ``read_bytes()`` can raise ``FileNotFoundError`` if
          the file is deleted between the ``exists()`` check and the read;
          this falls through to the atomic create path.
        - If ``O_EXCL`` raises ``FileExistsError`` (concurrent create), the
          existing key written by the winner is read instead.
        """
        if self._key_file.exists():
            try:
                return self._key_file.read_bytes()
            except FileNotFoundError:
                pass  # Deleted between exists() and read — fall through to create.

        self._token_dir.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        try:
            fd = os.open(self._key_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        except FileExistsError:
            # Another process created the file concurrently; read its key.
            return self._key_file.read_bytes()

        try:
            os.write(fd, key)
        finally:
            os.close(fd)

        logger.info("ms_graph_auth.key_generated", path=str(self._key_file))
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
        Uses ``os.write``/``os.close`` directly so the file descriptor is
        always closed in a ``finally`` block, avoiding any fd leak.
        The temp file is unlinked if the rename fails.
        """
        key = self._get_or_create_key()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(cache.serialize().encode())
        self._token_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = self._cache_file.with_suffix(".tmp")
        fd = os.open(tmp_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(fd, encrypted)
        finally:
            os.close(fd)
        try:
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

        Raises:
            ValueError: if MS_TENANT_ID or MS_CLIENT_ID env vars are not set.
        """
        loop = asyncio.get_running_loop()

        def _silent_acquire() -> bool:
            app, cache = self._build_app()
            accounts = app.get_accounts()
            if not accounts:
                return False

            result: _TokenResultDict | None = app.acquire_token_silent(
                self.SCOPES, account=accounts[0]
            )
            if result and "access_token" in result:
                self._save_token_cache(cache)
                logger.info("ms_graph_auth.silent_token_acquired")
                return True

            logger.info("ms_graph_auth.silent_token_failed_reauth_required")
            return False

        return await loop.run_in_executor(None, _silent_acquire)

    async def initiate_device_code_flow(self) -> tuple[DeviceCodeInfo, DeviceFlowDict]:
        """Start a device code flow.

        Stores the MSAL app instance internally so that ``poll_for_token``
        can use the same instance, ensuring consistent cache state.

        If called a second time before ``poll_for_token`` completes, the
        previous pending flow's app and cache are silently replaced.

        Returns:
            A tuple of (DeviceCodeInfo, flow_dict). Pass flow_dict to
            ``poll_for_token()`` to complete authentication.

        Raises:
            ValueError: if MS_TENANT_ID or MS_CLIENT_ID env vars are not set.
        """
        loop = asyncio.get_running_loop()

        def _initiate() -> tuple[DeviceCodeInfo, DeviceFlowDict]:
            app, cache = self._build_app()
            # Store for reuse in poll_for_token
            self._pending_app = app
            self._pending_cache = cache
            flow: DeviceFlowDict = app.initiate_device_flow(scopes=self.SCOPES)
            info = DeviceCodeInfo(
                user_code=flow["user_code"],
                verification_uri=flow["verification_uri"],
                expires_in=flow["expires_in"],
                message=flow["message"],
            )
            logger.info(
                "ms_graph_auth.device_flow_initiated",
                verification_uri=info.verification_uri,
            )
            return info, flow

        return await loop.run_in_executor(None, _initiate)

    async def poll_for_token(self, flow: DeviceFlowDict) -> bool:
        """Block until the user authenticates or the flow expires.

        Reuses the MSAL app instance from ``initiate_device_code_flow`` when
        available, ensuring the resulting token is saved to the same cache.

        Args:
            flow: The flow dict returned by ``initiate_device_code_flow()``.

        Returns:
            True if authentication succeeded and the token was saved.
            False if authentication failed or was declined.

        Raises:
            ValueError: if MS_TENANT_ID or MS_CLIENT_ID env vars are not set
                and no pending app is available.
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

        Raises:
            ValueError: if MS_TENANT_ID or MS_CLIENT_ID env vars are not set.
        """
        loop = asyncio.get_running_loop()

        def _get_token() -> str | None:
            app, cache = self._build_app()
            accounts = app.get_accounts()
            if not accounts:
                return None

            result: _TokenResultDict | None = app.acquire_token_silent(
                self.SCOPES, account=accounts[0]
            )
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

        Raises:
            ValueError: if MS_TENANT_ID or MS_CLIENT_ID env vars are not set.
        """
        loop = asyncio.get_running_loop()

        def _check() -> bool:
            app, _ = self._build_app()
            return len(app.get_accounts()) > 0

        return await loop.run_in_executor(None, _check)
