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
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import ClassVar, TypedDict

import structlog
from cryptography.fernet import Fernet, InvalidToken
from msal import PublicClientApplication, SerializableTokenCache
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# Tenant IDs are either UUIDs or domain-style names (e.g. contoso.onmicrosoft.com).
# This guards against path-traversal characters being interpolated into the authority URL.
_TENANT_ID_RE = re.compile(
    r"^(?:"
    r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"  # UUID
    r"|[a-zA-Z0-9][a-zA-Z0-9.\-]{0,253}"  # domain or named tenant
    r")$"
)


# ---------------------------------------------------------------------------
# MSAL response shapes
# ---------------------------------------------------------------------------


class DeviceFlowDict(TypedDict, total=True):
    """Required fields always present in a successful MSAL initiate_device_flow response."""

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


class AuthFlowContext:
    """Opaque context returned by ``initiate_device_code_flow``; pass it to ``poll_for_token``.

    Bundles the MSAL app, its token cache, and the device flow dict so that
    ``poll_for_token`` uses the exact same app instance that initiated the flow,
    eliminating any shared mutable state on ``MicrosoftGraphAuth``.

    Treat this as an opaque token — do not inspect or modify the internals.
    """

    __slots__ = ("_flow", "_app", "_cache")

    def __init__(
        self,
        flow: DeviceFlowDict,
        app: PublicClientApplication,
        cache: SerializableTokenCache,
    ) -> None:
        self._flow = flow
        self._app = app
        self._cache = cache


# ---------------------------------------------------------------------------
# Auth class
# ---------------------------------------------------------------------------


class MicrosoftGraphAuth:
    """Manages Microsoft Graph OAuth2 authentication for a single user."""

    SCOPES: ClassVar[tuple[str, ...]] = (
        "OnlineMeetingTranscript.Read",
        "OnlineMeeting.Read",
        "User.Read",
        "offline_access",
    )

    def __init__(self, token_dir: Path) -> None:
        self._token_dir = token_dir
        self._key_file = token_dir / "token.key"
        self._cache_file = token_dir / "ms_graph.json"

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
        """Return a populated MSAL token cache, or an empty one if no file exists.

        ``InvalidToken``, ``ValueError``, ``FileNotFoundError``, and
        ``PermissionError`` are swallowed (expected decryption/deserialization
        failures or unreadable cache file). All other exceptions propagate so
        unexpected errors are not silently masked.
        """
        cache = SerializableTokenCache()
        if not self._cache_file.exists():
            return cache

        try:
            key = self._get_or_create_key()
            fernet = Fernet(key)
            encrypted = self._cache_file.read_bytes()
            serialized = fernet.decrypt(encrypted).decode()
            cache.deserialize(serialized)
        except (InvalidToken, ValueError, FileNotFoundError, PermissionError):
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
        The temp file is unlinked if the write or rename fails.
        """
        key = self._get_or_create_key()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(cache.serialize().encode())
        self._token_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = self._cache_file.with_suffix(".tmp")
        write_succeeded = False
        fd = os.open(tmp_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            # fchmod ensures correct permissions even if the file pre-existed with
            # looser permissions (O_TRUNC does not update mode on existing files).
            os.fchmod(fd, 0o600)
            os.write(fd, encrypted)
            write_succeeded = True
        finally:
            os.close(fd)
            if not write_succeeded:
                with contextlib.suppress(OSError):
                    tmp_file.unlink(missing_ok=True)
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
            ValueError: if either required env var is missing or ``MS_TENANT_ID``
                contains characters that could be interpolated into the authority URL.
        """
        tenant_id = os.environ.get("MS_TENANT_ID")
        client_id = os.environ.get("MS_CLIENT_ID")

        if not tenant_id:
            raise ValueError("MS_TENANT_ID environment variable is required")
        if not _TENANT_ID_RE.match(tenant_id):
            raise ValueError(
                f"MS_TENANT_ID has an invalid format: {tenant_id!r}. "
                "Expected a UUID or a domain name."
            )
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

        Delegates to ``get_access_token`` and logs the outcome.

        Returns:
            True if a valid access token was obtained silently.
            False if re-authentication via device code flow is required.

        Raises:
            ValueError: if MS_TENANT_ID or MS_CLIENT_ID env vars are not set.
        """
        token = await self.get_access_token()
        if token is not None:
            logger.info("ms_graph_auth.silent_token_acquired")
            return True
        logger.info("ms_graph_auth.silent_token_failed_reauth_required")
        return False

    async def initiate_device_code_flow(self) -> tuple[DeviceCodeInfo, AuthFlowContext]:
        """Start a device code flow.

        The returned ``AuthFlowContext`` bundles the MSAL app, cache, and flow
        dict for use by ``poll_for_token``, avoiding any shared mutable state.

        Returns:
            A tuple of ``(DeviceCodeInfo, AuthFlowContext)``.
            Display ``DeviceCodeInfo.user_code`` and ``verification_uri`` to the
            user, then pass ``AuthFlowContext`` to ``poll_for_token()``.

        Raises:
            ValueError: if MS_TENANT_ID or MS_CLIENT_ID env vars are not set.
            RuntimeError: if MSAL returns an error from ``initiate_device_flow``.
        """
        loop = asyncio.get_running_loop()

        def _initiate() -> tuple[DeviceCodeInfo, AuthFlowContext]:
            app, cache = self._build_app()
            flow_raw: dict[str, object] = app.initiate_device_flow(scopes=self.SCOPES)

            if "error" in flow_raw:
                raise RuntimeError(
                    "Failed to initiate device code flow: "
                    f"{flow_raw.get('error_description') or flow_raw.get('error')}"
                )

            flow = DeviceFlowDict(
                user_code=str(flow_raw["user_code"]),
                device_code=str(flow_raw["device_code"]),
                verification_uri=str(flow_raw["verification_uri"]),
                expires_in=int(str(flow_raw["expires_in"])),
                interval=int(str(flow_raw["interval"])),
                message=str(flow_raw["message"]),
            )
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
            return info, AuthFlowContext(flow=flow, app=app, cache=cache)

        return await loop.run_in_executor(None, _initiate)

    async def poll_for_token(self, context: AuthFlowContext) -> bool:
        """Block until the user authenticates or the flow expires.

        Uses the MSAL app and cache from the supplied ``AuthFlowContext`` so
        that the resulting token is stored in the same cache that was in use
        when the flow was initiated.

        Args:
            context: The ``AuthFlowContext`` returned by
                ``initiate_device_code_flow()``.

        Returns:
            True if authentication succeeded and the token was saved.
            False if authentication failed or was declined.
        """
        loop = asyncio.get_running_loop()

        def _blocking_poll() -> bool:
            result: _TokenResultDict = context._app.acquire_token_by_device_flow(context._flow)
            if "error" in result:
                logger.warning(
                    "ms_graph_auth.device_flow_failed",
                    error=result.get("error"),
                    description=result.get("error_description"),
                )
                return False

            self._save_token_cache(context._cache)
            logger.info("ms_graph_auth.device_flow_succeeded")
            return True

        # Use a dedicated thread so the long-polling call (up to ``expires_in``
        # seconds, typically 15 min) does not tie up the shared default executor.
        # Note: if this coroutine is cancelled while awaiting, the executor's
        # __exit__ will block the event loop until the thread finishes (a known
        # Python limitation with run_in_executor + context managers).
        with ThreadPoolExecutor(max_workers=1) as pool:
            return await loop.run_in_executor(pool, _blocking_poll)

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
                if cache.has_state_changed:
                    self._save_token_cache(cache)
                return result["access_token"]

            return None

        return await loop.run_in_executor(None, _get_token)

    async def has_cached_account(self) -> bool:
        """Return True if a cached account exists.

        Note: a cached account does not guarantee a valid token — the token may
        need a silent refresh, which can fail if the refresh token has expired.
        Use ``get_access_token()`` when you need a confirmed valid token.

        This method offloads I/O to a thread pool via ``run_in_executor``.

        Raises:
            ValueError: if MS_TENANT_ID or MS_CLIENT_ID env vars are not set.
        """
        loop = asyncio.get_running_loop()

        def _check() -> bool:
            app, _ = self._build_app()
            return len(app.get_accounts()) > 0

        return await loop.run_in_executor(None, _check)
