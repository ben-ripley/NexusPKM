"""Tests for ConnectorRegistry and BaseConnector.

Covers: connectors/base.py, connectors/registry.py
Spec refs: ADR-004
NXP-51
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncIterator

import pytest

from nexuspkm.connectors.base import BaseConnector
from nexuspkm.models.document import Document, DocumentMetadata, SourceType

NOW = datetime.datetime(2026, 3, 19, 12, 0, 0, tzinfo=datetime.UTC)


def _make_document(doc_id: str = "doc-1") -> Document:
    return Document(
        id=doc_id,
        content="Test content",
        metadata=DocumentMetadata(
            source_type=SourceType.OBSIDIAN_NOTE,
            source_id="note-1",
            title="Test Note",
            created_at=NOW,
            updated_at=NOW,
            synced_at=NOW,
        ),
    )


# We defer imports into test methods so tests fail cleanly with ImportError
# rather than AttributeError when the connector modules don't exist yet.


class TestBaseConnectorAbstract:
    def test_cannot_instantiate_directly(self) -> None:
        from nexuspkm.connectors.base import BaseConnector

        with pytest.raises(TypeError):
            BaseConnector()  # type: ignore[abstract]

    def test_stub_is_valid_subclass(self) -> None:
        from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
        from nexuspkm.models.document import SyncState

        class _LocalStub(BaseConnector):
            name = "local_stub"

            async def authenticate(self) -> bool:
                return True

            def fetch(self, since: datetime.datetime | None = None) -> AsyncIterator[Document]:
                async def _gen() -> AsyncIterator[Document]:
                    return
                    yield  # pragma: no cover  # make it an async generator

                return _gen()

            async def health_check(self) -> ConnectorStatus:
                return ConnectorStatus(name="local_stub", status="healthy")

            async def get_sync_state(self) -> SyncState:
                return SyncState()

            async def restore_sync_state(self, state: SyncState) -> None:
                pass

        stub = _LocalStub()
        assert isinstance(stub, BaseConnector)


class TestConnectorStatus:
    def test_defaults(self) -> None:
        from nexuspkm.connectors.base import ConnectorStatus

        s = ConnectorStatus(name="foo", status="healthy")
        assert s.name == "foo"
        assert s.status == "healthy"
        assert s.last_sync_at is None
        assert s.last_error is None
        assert s.documents_synced == 0

    def test_all_status_values(self) -> None:
        from nexuspkm.connectors.base import ConnectorStatus

        for status_val in ("healthy", "degraded", "unavailable"):
            s = ConnectorStatus(name="x", status=status_val)  # type: ignore[arg-type]
            assert s.status == status_val

    def test_invalid_status_rejected(self) -> None:
        from pydantic import ValidationError

        from nexuspkm.connectors.base import ConnectorStatus

        with pytest.raises(ValidationError):
            ConnectorStatus(name="x", status="broken")  # type: ignore[arg-type]

    def test_with_last_sync_and_error(self) -> None:
        from nexuspkm.connectors.base import ConnectorStatus

        s = ConnectorStatus(
            name="foo",
            status="degraded",
            last_sync_at=NOW,
            last_error="timeout",
            documents_synced=42,
        )
        assert s.last_sync_at == NOW
        assert s.last_error == "timeout"
        assert s.documents_synced == 42


def _make_stub_connector(stub_name: str = "stub") -> BaseConnector:
    """Create a concrete BaseConnector subclass for use in registry tests."""
    from nexuspkm.connectors.base import BaseConnector, ConnectorStatus
    from nexuspkm.models.document import SyncState

    class _Stub(BaseConnector):
        name = stub_name  # ClassVar satisfied via class body

        async def authenticate(self) -> bool:
            return True

        def fetch(self, since: datetime.datetime | None = None) -> AsyncIterator[Document]:
            async def _gen() -> AsyncIterator[Document]:
                return
                yield  # pragma: no cover

            return _gen()

        async def health_check(self) -> ConnectorStatus:
            return ConnectorStatus(name=stub_name, status="healthy")

        async def get_sync_state(self) -> SyncState:
            return SyncState()

        async def restore_sync_state(self, state: SyncState) -> None:
            pass

    return _Stub()


class TestConnectorRegistry:
    def _make_stub(self, name: str = "stub") -> BaseConnector:
        return _make_stub_connector(name)

    def test_empty_registry(self) -> None:
        from nexuspkm.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        assert reg.all_connectors() == []
        assert reg.get_all_statuses() == {}
        assert reg.get("missing") is None

    def test_register_and_get(self) -> None:
        from nexuspkm.connectors.base import BaseConnector
        from nexuspkm.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        stub = self._make_stub("myconn")
        reg.register(stub)

        retrieved = reg.get("myconn")
        assert retrieved is stub
        assert isinstance(retrieved, BaseConnector)

    def test_get_unknown_returns_none(self) -> None:
        from nexuspkm.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        assert reg.get("nonexistent") is None

    def test_all_connectors_returns_all(self) -> None:
        from nexuspkm.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        s1 = self._make_stub("conn_a")
        s2 = self._make_stub("conn_b")
        reg.register(s1)
        reg.register(s2)

        all_c = reg.all_connectors()
        assert len(all_c) == 2
        assert s1 in all_c
        assert s2 in all_c

    def test_initial_status_unavailable(self) -> None:
        from nexuspkm.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        stub = self._make_stub("myconn")
        reg.register(stub)

        statuses = reg.get_all_statuses()
        assert "myconn" in statuses
        assert statuses["myconn"].status == "unavailable"

    def test_update_status(self) -> None:
        from nexuspkm.connectors.base import ConnectorStatus
        from nexuspkm.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        stub = self._make_stub("myconn")
        reg.register(stub)

        new_status = ConnectorStatus(name="myconn", status="healthy", documents_synced=5)
        reg.update_status("myconn", new_status)

        assert reg.get_all_statuses()["myconn"].status == "healthy"
        assert reg.get_all_statuses()["myconn"].documents_synced == 5

    def test_update_status_unknown_name_is_noop(self) -> None:
        from nexuspkm.connectors.base import ConnectorStatus
        from nexuspkm.connectors.registry import ConnectorRegistry

        reg = ConnectorRegistry()
        # Unknown name: must not raise and must not insert a status entry
        reg.update_status("ghost", ConnectorStatus(name="ghost", status="healthy"))
        assert "ghost" not in reg.get_all_statuses()


class TestSyncState:
    def test_defaults(self) -> None:
        from nexuspkm.models.document import SyncState

        s = SyncState()
        assert s.last_synced_at is None
        assert s.cursor is None
        assert s.extra == {}

    def test_with_values(self) -> None:
        from nexuspkm.models.document import SyncState

        s = SyncState(last_synced_at=NOW, cursor="page_2", extra={"token": "abc"})
        assert s.last_synced_at == NOW
        assert s.cursor == "page_2"
        assert s.extra == {"token": "abc"}

    def test_frozen(self) -> None:
        from pydantic import ValidationError

        from nexuspkm.models.document import SyncState

        s = SyncState()
        with pytest.raises(ValidationError):
            s.cursor = "x"  # type: ignore[misc]

    def test_extra_forbids_extra_fields(self) -> None:
        from pydantic import ValidationError

        from nexuspkm.models.document import SyncState

        with pytest.raises(ValidationError):
            SyncState(unknown_field="oops")  # type: ignore[call-arg]
