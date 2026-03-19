"""Microsoft Graph OAuth2 authentication via Device Code Flow.

Handles token acquisition, encrypted storage, silent refresh, and
re-authentication prompting when the refresh token has expired.

Token storage layout:
    <token_dir>/token.key       — Fernet symmetric key (file permissions: 0o600)
    <token_dir>/ms_graph.json   — Fernet-encrypted MSAL SerializableTokenCache
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, cast

import structlog
from cryptography.fernet import Fernet
from msal import PublicClientApplication, SerializableTokenCache
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class DeviceCodeInfo(BaseModel):
    """Human-readable device code flow initiation data."""

    user_code: str
    verification_uri: str
    expires_in: int
    message: str


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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_key(self) -> bytes:
        """Load the Fernet key from disk, generating it on first run.

        The key file is created atomically with 0o600 permissions to avoid
        a TOCTOU window where the key is transiently world-readable.
        """
        if self._key_file.exists():
            return self._key_file.read_bytes()

        self._token_dir.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        # Atomic create with restricted permissions — avoids write+chmod race.
        fd = os.open(self._key_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
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

        Written atomically with 0o600 permissions to avoid a TOCTOU window
        where encrypted tokens are transiently world-readable.
        """
        key = self._get_or_create_key()
        fernet = Fernet(key)
        serialized = cache.serialize()
        encrypted = fernet.encrypt(serialized.encode())
        self._token_dir.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then rename for atomicity, with restricted perms.
        tmp_file = self._cache_file.with_suffix(".tmp")
        fd = os.open(tmp_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(encrypted)
        tmp_file.rename(self._cache_file)

    def _build_app(self) -> PublicClientApplication:
        """Construct an MSAL PublicClientApplication with the loaded token cache.

        Reads MS_TENANT_ID and MS_CLIENT_ID from environment variables.

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
        return PublicClientApplication(client_id, authority=authority, token_cache=cache)

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
            app = self._build_app()
            accounts = app.get_accounts()
            if not accounts:
                return False

            result = app.acquire_token_silent(self.SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_token_cache(cast(SerializableTokenCache, app.token_cache))
                logger.info("ms_graph_auth.silent_token_acquired")
                return True

            logger.info("ms_graph_auth.silent_token_failed_reauth_required")
            return False

        return await loop.run_in_executor(None, _silent_acquire)

    async def initiate_device_code_flow(self) -> tuple[DeviceCodeInfo, dict[str, Any]]:
        """Start a device code flow.

        Returns:
            A tuple of (DeviceCodeInfo, raw_flow_dict). Pass raw_flow_dict to
            poll_for_token() to complete authentication.
        """
        loop = asyncio.get_running_loop()

        def _initiate() -> tuple[DeviceCodeInfo, dict[str, Any]]:
            app = self._build_app()
            flow: dict[str, Any] = app.initiate_device_flow(scopes=self.SCOPES)
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

    async def poll_for_token(self, flow: dict[str, Any]) -> bool:
        """Block until the user authenticates or the flow expires.

        Args:
            flow: The raw flow dict returned by initiate_device_code_flow().

        Returns:
            True if authentication succeeded and the token was saved.
            False if authentication failed or was declined.
        """
        loop = asyncio.get_running_loop()

        def _blocking_poll() -> bool:
            app = self._build_app()
            result: dict[str, Any] = app.acquire_token_by_device_flow(flow)
            if "error" in result:
                logger.warning(
                    "ms_graph_auth.device_flow_failed",
                    error=result.get("error"),
                    description=result.get("error_description"),
                )
                return False

            self._save_token_cache(cast(SerializableTokenCache, app.token_cache))
            logger.info("ms_graph_auth.device_flow_succeeded")
            return True

        return await loop.run_in_executor(None, _blocking_poll)

    async def get_access_token(self) -> str | None:
        """Return a current valid access token, or None if unavailable.

        Performs a silent refresh if needed. Does not initiate device code flow.
        """
        loop = asyncio.get_running_loop()

        def _get_token() -> str | None:
            app = self._build_app()
            accounts = app.get_accounts()
            if not accounts:
                return None

            result = app.acquire_token_silent(self.SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_token_cache(cast(SerializableTokenCache, app.token_cache))
                return str(result["access_token"])

            return None

        return await loop.run_in_executor(None, _get_token)

    async def is_authenticated(self) -> bool:
        """Return True if a cached account exists (token may still need silent refresh)."""
        loop = asyncio.get_running_loop()

        def _check() -> bool:
            app = self._build_app()
            return len(app.get_accounts()) > 0

        return await loop.run_in_executor(None, _check)
