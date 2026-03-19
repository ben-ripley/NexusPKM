"""Tests for nexuspkm.models — written before implementation (TDD red phase).

Covers: document.py, entity.py, relationship.py, search.py, chat.py, __init__.py
Spec refs: F-002 (FR-1, FR-4, FR-5), F-005 (FR-3, FR-4), F-006 (FR-1, FR-2), F-007 (FR-1)
"""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)


# ===========================================================================
# document.py
# ===========================================================================


class TestSourceType:
    def test_has_all_six_values(self) -> None:
        from nexuspkm.models.document import SourceType

        expected = {
            "teams_transcript",
            "obsidian_note",
            "outlook_email",
            "outlook_calendar",
            "jira_issue",
            "apple_note",
        }
        assert {v.value for v in SourceType} == expected

    def test_is_str_enum(self) -> None:
        from nexuspkm.models.document import SourceType

        assert SourceType.TEAMS_TRANSCRIPT == "teams_transcript"


class TestProcessingStatus:
    def test_has_all_four_values(self) -> None:
        from nexuspkm.models.document import ProcessingStatus

        expected = {"pending", "processing", "indexed", "error"}
        assert {v.value for v in ProcessingStatus} == expected

    def test_is_str_enum(self) -> None:
        from nexuspkm.models.document import ProcessingStatus

        assert ProcessingStatus.PENDING == "pending"


class TestDocumentMetadata:
    def _make(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "source_type": "teams_transcript",
            "source_id": "meeting-123",
            "title": "Sprint Planning",
            "created_at": NOW,
            "updated_at": NOW,
            "synced_at": NOW,
        }
        base.update(overrides)
        return base

    def test_valid_minimal(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        meta = DocumentMetadata(**self._make())  # type: ignore[arg-type]
        assert meta.source_id == "meeting-123"

    def test_participants_defaults_empty(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        meta = DocumentMetadata(**self._make())  # type: ignore[arg-type]
        assert meta.participants == []

    def test_tags_defaults_empty(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        meta = DocumentMetadata(**self._make())  # type: ignore[arg-type]
        assert meta.tags == []

    def test_custom_defaults_empty_dict(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        meta = DocumentMetadata(**self._make())  # type: ignore[arg-type]
        assert meta.custom == {}

    def test_author_defaults_none(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        meta = DocumentMetadata(**self._make())  # type: ignore[arg-type]
        assert meta.author is None

    def test_url_defaults_none(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        meta = DocumentMetadata(**self._make())  # type: ignore[arg-type]
        assert meta.url is None

    def test_missing_source_type_raises(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        data = self._make()
        del data["source_type"]
        with pytest.raises(ValidationError):
            DocumentMetadata(**data)  # type: ignore[arg-type]

    def test_missing_source_id_raises(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        data = self._make()
        del data["source_id"]
        with pytest.raises(ValidationError):
            DocumentMetadata(**data)  # type: ignore[arg-type]

    def test_missing_title_raises(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        data = self._make()
        del data["title"]
        with pytest.raises(ValidationError):
            DocumentMetadata(**data)  # type: ignore[arg-type]

    def test_missing_created_at_raises(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        data = self._make()
        del data["created_at"]
        with pytest.raises(ValidationError):
            DocumentMetadata(**data)  # type: ignore[arg-type]

    def test_missing_updated_at_raises(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        data = self._make()
        del data["updated_at"]
        with pytest.raises(ValidationError):
            DocumentMetadata(**data)  # type: ignore[arg-type]

    def test_missing_synced_at_raises(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        data = self._make()
        del data["synced_at"]
        with pytest.raises(ValidationError):
            DocumentMetadata(**data)  # type: ignore[arg-type]

    def test_invalid_source_type_raises(self) -> None:
        from nexuspkm.models.document import DocumentMetadata

        with pytest.raises(ValidationError):
            DocumentMetadata(**self._make(source_type="not_a_type"))  # type: ignore[arg-type]


class TestDocument:
    def _meta(self) -> dict[str, object]:
        return {
            "source_type": "obsidian_note",
            "source_id": "note-abc",
            "title": "My Note",
            "created_at": NOW,
            "updated_at": NOW,
            "synced_at": NOW,
        }

    def test_valid_document(self) -> None:
        from nexuspkm.models.document import Document

        doc = Document(id="doc-1", content="Hello world", metadata=self._meta())  # type: ignore[arg-type]
        assert doc.id == "doc-1"

    def test_processing_status_defaults_pending(self) -> None:
        from nexuspkm.models.document import Document

        doc = Document(id="doc-1", content="Hello world", metadata=self._meta())  # type: ignore[arg-type]
        assert doc.processing_status == "pending"

    def test_chunks_defaults_empty(self) -> None:
        from nexuspkm.models.document import Document

        doc = Document(id="doc-1", content="Hello world", metadata=self._meta())  # type: ignore[arg-type]
        assert doc.chunks == []

    def test_invalid_processing_status_raises(self) -> None:
        from nexuspkm.models.document import Document

        with pytest.raises(ValidationError):
            Document(
                id="doc-1",
                content="Hello",
                metadata=self._meta(),  # type: ignore[arg-type]
                processing_status="bad_status",  # type: ignore[arg-type]
            )

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.document import Document

        doc = Document(id="doc-1", content="Hello world", metadata=self._meta())  # type: ignore[arg-type]
        restored = Document.model_validate_json(doc.model_dump_json())
        assert restored.id == doc.id
        assert restored.processing_status == doc.processing_status


class TestSourceAttribution:
    def test_valid_minimal(self) -> None:
        from nexuspkm.models.document import SourceAttribution

        sa = SourceAttribution(
            document_id="doc-1",
            title="Note",
            source_type="obsidian_note",
            source_id="note-1",
            excerpt="some text",
            relevance_score=0.9,
            created_at=NOW,
        )
        assert sa.document_id == "doc-1"

    def test_url_optional(self) -> None:
        from nexuspkm.models.document import SourceAttribution

        sa = SourceAttribution(
            document_id="doc-1",
            title="Note",
            source_type="obsidian_note",
            source_id="note-1",
            excerpt="text",
            relevance_score=0.5,
            created_at=NOW,
        )
        assert sa.url is None

    def test_participants_defaults_empty(self) -> None:
        from nexuspkm.models.document import SourceAttribution

        sa = SourceAttribution(
            document_id="doc-1",
            title="Note",
            source_type="obsidian_note",
            source_id="note-1",
            excerpt="text",
            relevance_score=0.5,
            created_at=NOW,
        )
        assert sa.participants == []

    def test_relevance_score_above_one_raises(self) -> None:
        from nexuspkm.models.document import SourceAttribution

        with pytest.raises(ValidationError):
            SourceAttribution(
                document_id="doc-1",
                title="Note",
                source_type="obsidian_note",
                source_id="note-1",
                excerpt="text",
                relevance_score=1.1,
                created_at=NOW,
            )

    def test_relevance_score_below_zero_raises(self) -> None:
        from nexuspkm.models.document import SourceAttribution

        with pytest.raises(ValidationError):
            SourceAttribution(
                document_id="doc-1",
                title="Note",
                source_type="obsidian_note",
                source_id="note-1",
                excerpt="text",
                relevance_score=-0.1,
                created_at=NOW,
            )

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.document import SourceAttribution

        sa = SourceAttribution(
            document_id="doc-1",
            title="Note",
            source_type="obsidian_note",
            source_id="note-1",
            excerpt="text",
            relevance_score=0.5,
            created_at=NOW,
            url="https://example.com",
            participants=["Alice"],
        )
        restored = SourceAttribution.model_validate_json(sa.model_dump_json())
        assert restored.url == sa.url
        assert restored.participants == sa.participants


class TestChunkResult:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.document import ChunkResult

        cr = ChunkResult(
            chunk_id="c-1",
            document_id="doc-1",
            text="some text chunk",
            score=0.85,
            source_type="jira_issue",
            source_id="NXP-42",
            title="My Issue",
            created_at=NOW,
        )
        assert cr.chunk_id == "c-1"
        assert cr.score == 0.85

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.document import ChunkResult

        cr = ChunkResult(
            chunk_id="c-1",
            document_id="doc-1",
            text="text",
            score=0.5,
            source_type="jira_issue",
            source_id="NXP-1",
            title="Title",
            created_at=NOW,
        )
        restored = ChunkResult.model_validate_json(cr.model_dump_json())
        assert restored.chunk_id == cr.chunk_id


class TestEntityResult:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.document import EntityResult

        er = EntityResult(
            entity_id="e-1",
            entity_type="person",
            name="Alice",
            context="mentioned in meeting",
        )
        assert er.name == "Alice"

    def test_entity_type_is_enum(self) -> None:
        from nexuspkm.models.document import EntityResult
        from nexuspkm.models.entity import EntityType

        er = EntityResult(entity_id="e-1", entity_type="person", name="Alice", context="ctx")
        assert er.entity_type == EntityType.PERSON

    def test_invalid_entity_type_raises(self) -> None:
        from nexuspkm.models.document import EntityResult

        with pytest.raises(ValidationError):
            EntityResult(entity_id="e-1", entity_type="robot", name="R2D2", context="ctx")


class TestRelResult:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.document import RelResult

        rr = RelResult(
            source_entity="Alice",
            relationship_type="ATTENDED",
            target_entity="Sprint Planning",
            context="attended the meeting",
        )
        assert rr.relationship_type == "ATTENDED"

    def test_relationship_type_is_enum(self) -> None:
        from nexuspkm.models.document import RelResult
        from nexuspkm.models.relationship import RelationshipType

        rr = RelResult(
            source_entity="Alice",
            relationship_type="ATTENDED",
            target_entity="Meeting",
            context="ctx",
        )
        assert rr.relationship_type == RelationshipType.ATTENDED

    def test_invalid_relationship_type_raises(self) -> None:
        from nexuspkm.models.document import RelResult

        with pytest.raises(ValidationError):
            RelResult(
                source_entity="Alice",
                relationship_type="INVENTED_THING",
                target_entity="X",
                context="ctx",
            )


class TestRetrievalResult:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.document import RetrievalResult, SourceAttribution

        sa = SourceAttribution(
            document_id="doc-1",
            title="Note",
            source_type="obsidian_note",
            source_id="note-1",
            excerpt="text",
            relevance_score=0.9,
            created_at=NOW,
        )
        rr = RetrievalResult(
            chunks=[],
            entities=[],
            relationships=[],
            combined_score=0.75,
            sources=[sa],
        )
        assert rr.combined_score == 0.75
        assert len(rr.sources) == 1

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.document import RetrievalResult

        rr = RetrievalResult(
            chunks=[], entities=[], relationships=[], combined_score=0.5, sources=[]
        )
        restored = RetrievalResult.model_validate_json(rr.model_dump_json())
        assert restored.combined_score == rr.combined_score


# ===========================================================================
# entity.py
# ===========================================================================


class TestEntityType:
    def test_has_all_six_values(self) -> None:
        from nexuspkm.models.entity import EntityType

        expected = {"person", "project", "topic", "decision", "action_item", "meeting"}
        assert {v.value for v in EntityType} == expected

    def test_is_str_enum(self) -> None:
        from nexuspkm.models.entity import EntityType

        assert EntityType.PERSON == "person"


class TestEntitySummary:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.entity import EntitySummary, EntityType

        es = EntitySummary(name="Alice", entity_type=EntityType.PERSON)
        assert es.name == "Alice"
        assert es.entity_type == "person"

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.entity import EntitySummary, EntityType

        es = EntitySummary(name="NexusPKM", entity_type=EntityType.PROJECT)
        restored = EntitySummary.model_validate_json(es.model_dump_json())
        assert restored.name == es.name
        assert restored.entity_type == es.entity_type


class TestExtractedEntity:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.entity import EntityType, ExtractedEntity

        ee = ExtractedEntity(
            type=EntityType.PERSON,
            name="Alice",
            confidence=0.95,
            source_span="Alice attended the meeting",
        )
        assert ee.name == "Alice"
        assert ee.properties == {}

    def test_confidence_at_zero(self) -> None:
        from nexuspkm.models.entity import EntityType, ExtractedEntity

        ee = ExtractedEntity(type=EntityType.TOPIC, name="AI", confidence=0.0, source_span="span")
        assert ee.confidence == 0.0

    def test_confidence_at_one(self) -> None:
        from nexuspkm.models.entity import EntityType, ExtractedEntity

        ee = ExtractedEntity(type=EntityType.TOPIC, name="AI", confidence=1.0, source_span="span")
        assert ee.confidence == 1.0

    def test_confidence_below_zero_raises(self) -> None:
        from nexuspkm.models.entity import EntityType, ExtractedEntity

        with pytest.raises(ValidationError):
            ExtractedEntity(type=EntityType.TOPIC, name="AI", confidence=-0.1, source_span="span")

    def test_confidence_above_one_raises(self) -> None:
        from nexuspkm.models.entity import EntityType, ExtractedEntity

        with pytest.raises(ValidationError):
            ExtractedEntity(type=EntityType.TOPIC, name="AI", confidence=1.1, source_span="span")

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.entity import EntityType, ExtractedEntity

        ee = ExtractedEntity(
            type=EntityType.DECISION,
            name="Adopt LanceDB",
            confidence=0.8,
            source_span="we decided to adopt LanceDB",
            properties={"rationale": "performance"},
        )
        restored = ExtractedEntity.model_validate_json(ee.model_dump_json())
        assert restored.name == ee.name
        assert restored.properties == ee.properties


class TestExtractedRelationship:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.entity import ExtractedRelationship

        er = ExtractedRelationship(
            source_entity="Alice",
            relationship_type="ATTENDED",
            target_entity="Sprint Planning",
            confidence=0.9,
            context="Alice attended the sprint planning",
        )
        assert er.source_entity == "Alice"

    def test_relationship_type_is_enum(self) -> None:
        from nexuspkm.models.entity import ExtractedRelationship
        from nexuspkm.models.relationship import RelationshipType

        er = ExtractedRelationship(
            source_entity="Alice",
            relationship_type="WORKS_ON",
            target_entity="NexusPKM",
            confidence=0.8,
            context="ctx",
        )
        assert er.relationship_type == RelationshipType.WORKS_ON

    def test_invalid_relationship_type_raises(self) -> None:
        from nexuspkm.models.entity import ExtractedRelationship

        with pytest.raises(ValidationError):
            ExtractedRelationship(
                source_entity="Alice",
                relationship_type="NOT_A_TYPE",
                target_entity="X",
                confidence=0.5,
                context="ctx",
            )

    def test_confidence_out_of_range_raises(self) -> None:
        from nexuspkm.models.entity import ExtractedRelationship

        with pytest.raises(ValidationError):
            ExtractedRelationship(
                source_entity="Alice",
                relationship_type="ATTENDED",
                target_entity="Meeting",
                confidence=2.0,
                context="ctx",
            )

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.entity import ExtractedRelationship

        er = ExtractedRelationship(
            source_entity="Alice",
            relationship_type="WORKS_ON",
            target_entity="NexusPKM",
            confidence=0.7,
            context="Alice works on NexusPKM",
        )
        restored = ExtractedRelationship.model_validate_json(er.model_dump_json())
        assert restored.target_entity == er.target_entity


class TestExtractionResult:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.entity import ExtractionResult

        result = ExtractionResult(entities=[], relationships=[], confidence=0.85)
        assert result.confidence == 0.85

    def test_confidence_out_of_range_raises(self) -> None:
        from nexuspkm.models.entity import ExtractionResult

        with pytest.raises(ValidationError):
            ExtractionResult(entities=[], relationships=[], confidence=-0.1)

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.entity import EntityType, ExtractedEntity, ExtractionResult

        entity = ExtractedEntity(
            type=EntityType.MEETING,
            name="Sprint Planning",
            confidence=0.9,
            source_span="Sprint Planning meeting",
        )
        result = ExtractionResult(entities=[entity], relationships=[], confidence=0.9)
        restored = ExtractionResult.model_validate_json(result.model_dump_json())
        assert len(restored.entities) == 1
        assert restored.entities[0].name == "Sprint Planning"


# ===========================================================================
# relationship.py
# ===========================================================================


class TestRelationshipType:
    def test_has_all_ten_values(self) -> None:
        from nexuspkm.models.relationship import RelationshipType

        expected = {
            "ATTENDED",
            "MENTIONED_IN",
            "ASSIGNED_TO",
            "RELATED_TO",
            "DECIDED_IN",
            "WORKS_ON",
            "TAGGED_WITH",
            "FOLLOWED_UP_BY",
            "OWNS",
            "BLOCKS",
        }
        assert {v.value for v in RelationshipType} == expected

    def test_is_str_enum(self) -> None:
        from nexuspkm.models.relationship import RelationshipType

        assert RelationshipType.ATTENDED == "ATTENDED"


# ===========================================================================
# search.py
# ===========================================================================


class TestSearchFilters:
    def test_all_fields_optional_defaults_none(self) -> None:
        from nexuspkm.models.search import SearchFilters

        sf = SearchFilters()
        assert sf.source_types is None
        assert sf.date_from is None
        assert sf.date_to is None
        assert sf.entities is None
        assert sf.tags is None

    def test_partial_construction(self) -> None:
        from nexuspkm.models.search import SearchFilters

        sf = SearchFilters(tags=["ai", "search"])
        assert sf.tags == ["ai", "search"]
        assert sf.source_types is None

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.search import SearchFilters

        sf = SearchFilters(
            source_types=["jira_issue"],
            date_from=NOW,
            entities=["Alice"],
            tags=["sprint"],
        )
        restored = SearchFilters.model_validate_json(sf.model_dump_json())
        assert restored.tags == sf.tags
        assert restored.source_types == sf.source_types


class TestSearchRequest:
    def test_defaults(self) -> None:
        from nexuspkm.models.search import SearchRequest

        req = SearchRequest(query="find meeting notes")
        assert req.top_k == 20
        assert req.include_graph_expansion is True
        assert req.filters is None

    def test_custom_values(self) -> None:
        from nexuspkm.models.search import SearchRequest

        req = SearchRequest(query="q", top_k=5, include_graph_expansion=False)
        assert req.top_k == 5
        assert req.include_graph_expansion is False

    def test_top_k_zero_raises(self) -> None:
        from nexuspkm.models.search import SearchRequest

        with pytest.raises(ValidationError):
            SearchRequest(query="q", top_k=0)

    def test_top_k_negative_raises(self) -> None:
        from nexuspkm.models.search import SearchRequest

        with pytest.raises(ValidationError):
            SearchRequest(query="q", top_k=-1)

    def test_top_k_above_max_raises(self) -> None:
        from nexuspkm.models.search import SearchRequest

        with pytest.raises(ValidationError):
            SearchRequest(query="q", top_k=201)

    def test_top_k_at_max_valid(self) -> None:
        from nexuspkm.models.search import SearchRequest

        req = SearchRequest(query="q", top_k=200)
        assert req.top_k == 200

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.search import SearchRequest

        req = SearchRequest(query="test query", top_k=10)
        restored = SearchRequest.model_validate_json(req.model_dump_json())
        assert restored.query == req.query
        assert restored.top_k == req.top_k


class TestSearchResult:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.search import SearchResult

        sr = SearchResult(
            id="res-1",
            title="Sprint Notes",
            excerpt="We discussed velocity",
            source_type="teams_transcript",
            source_id="meeting-1",
            relevance_score=0.88,
            created_at=NOW,
        )
        assert sr.matched_entities == []
        assert sr.related_documents == []
        assert sr.url is None

    def test_with_matched_entities(self) -> None:
        from nexuspkm.models.entity import EntitySummary, EntityType
        from nexuspkm.models.search import SearchResult

        es = EntitySummary(name="Alice", entity_type=EntityType.PERSON)
        sr = SearchResult(
            id="res-1",
            title="Note",
            excerpt="text",
            source_type="obsidian_note",
            source_id="n-1",
            relevance_score=0.5,
            created_at=NOW,
            matched_entities=[es],
            related_documents=["doc-2"],
        )
        assert len(sr.matched_entities) == 1
        assert sr.matched_entities[0].name == "Alice"
        assert sr.related_documents == ["doc-2"]

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.entity import EntitySummary, EntityType
        from nexuspkm.models.search import SearchResult

        sr = SearchResult(
            id="res-1",
            title="Note",
            excerpt="text",
            source_type="obsidian_note",
            source_id="n-1",
            relevance_score=0.5,
            created_at=NOW,
            matched_entities=[EntitySummary(name="Bob", entity_type=EntityType.PERSON)],
        )
        restored = SearchResult.model_validate_json(sr.model_dump_json())
        assert restored.matched_entities[0].name == "Bob"


class TestSearchFacets:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.entity import EntityType
        from nexuspkm.models.search import DateBucket, EntityCount, SearchFacets, TagCount

        facets = SearchFacets(
            source_types={"jira_issue": 5, "obsidian_note": 3},
            date_histogram=[DateBucket(date=NOW, count=8)],
            top_entities=[EntityCount(name="Alice", entity_type=EntityType.PERSON, count=3)],
            top_tags=[TagCount(tag="ai", count=5)],
        )
        assert facets.source_types["jira_issue"] == 5
        assert len(facets.date_histogram) == 1

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.search import SearchFacets

        facets = SearchFacets(
            source_types={},
            date_histogram=[],
            top_entities=[],
            top_tags=[],
        )
        restored = SearchFacets.model_validate_json(facets.model_dump_json())
        assert restored.source_types == {}


class TestSearchResponse:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.search import SearchFacets, SearchResponse

        facets = SearchFacets(
            source_types={},
            date_histogram=[],
            top_entities=[],
            top_tags=[],
        )
        resp = SearchResponse(results=[], total_count=0, facets=facets)
        assert resp.results == []
        assert resp.total_count == 0
        assert resp.query_entities == []

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.search import SearchFacets, SearchResponse

        facets = SearchFacets(source_types={}, date_histogram=[], top_entities=[], top_tags=[])
        resp = SearchResponse(results=[], total_count=42, facets=facets, query_entities=["Alice"])
        restored = SearchResponse.model_validate_json(resp.model_dump_json())
        assert restored.total_count == 42
        assert restored.query_entities == ["Alice"]


# ===========================================================================
# chat.py
# ===========================================================================


class TestChatMessage:
    def test_valid_user_message(self) -> None:
        from nexuspkm.models.chat import ChatMessage

        msg = ChatMessage(id="m-1", role="user", content="Hello", timestamp=NOW)
        assert msg.role == "user"
        assert msg.sources == []

    def test_valid_assistant_message(self) -> None:
        from nexuspkm.models.chat import ChatMessage

        msg = ChatMessage(id="m-2", role="assistant", content="Hi there", timestamp=NOW)
        assert msg.role == "assistant"

    def test_invalid_role_raises(self) -> None:
        from nexuspkm.models.chat import ChatMessage

        with pytest.raises(ValidationError):
            ChatMessage(id="m-3", role="system", content="bad", timestamp=NOW)  # type: ignore[arg-type]

    def test_sources_defaults_empty(self) -> None:
        from nexuspkm.models.chat import ChatMessage

        msg = ChatMessage(id="m-1", role="user", content="Hello", timestamp=NOW)
        assert msg.sources == []

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.chat import ChatMessage
        from nexuspkm.models.document import SourceAttribution

        sa = SourceAttribution(
            document_id="doc-1",
            title="Note",
            source_type="obsidian_note",
            source_id="n-1",
            excerpt="text",
            relevance_score=0.9,
            created_at=NOW,
        )
        msg = ChatMessage(
            id="m-1", role="assistant", content="Based on...", timestamp=NOW, sources=[sa]
        )
        restored = ChatMessage.model_validate_json(msg.model_dump_json())
        assert restored.role == "assistant"
        assert len(restored.sources) == 1
        assert restored.sources[0].document_id == "doc-1"


class TestChatSession:
    def test_valid_construct(self) -> None:
        from nexuspkm.models.chat import ChatSession

        session = ChatSession(
            id="s-1",
            title="My Chat",
            created_at=NOW,
            updated_at=NOW,
        )
        assert session.messages == []
        assert session.title == "My Chat"

    def test_messages_defaults_empty(self) -> None:
        from nexuspkm.models.chat import ChatSession

        session = ChatSession(id="s-1", title="Chat", created_at=NOW, updated_at=NOW)
        assert session.messages == []

    def test_json_roundtrip(self) -> None:
        from nexuspkm.models.chat import ChatMessage, ChatSession

        msg = ChatMessage(id="m-1", role="user", content="Hello", timestamp=NOW)
        session = ChatSession(
            id="s-1",
            title="Chat",
            messages=[msg],
            created_at=NOW,
            updated_at=NOW,
        )
        restored = ChatSession.model_validate_json(session.model_dump_json())
        assert restored.id == "s-1"
        assert len(restored.messages) == 1
        assert restored.messages[0].role == "user"


# ===========================================================================
# __init__.py smoke test — all public names importable from nexuspkm.models
# ===========================================================================


class TestModelsPackageExports:
    def test_document_exports(self) -> None:
        from pydantic import BaseModel

        from nexuspkm.models import (
            ChunkResult,
            Document,
            DocumentMetadata,
            EntityResult,
            RelResult,
            RetrievalResult,
            SourceAttribution,
        )

        for cls in (
            Document,
            DocumentMetadata,
            ChunkResult,
            EntityResult,
            RelResult,
            RetrievalResult,
            SourceAttribution,
        ):
            assert issubclass(cls, BaseModel)

    def test_enum_exports(self) -> None:
        from enum import StrEnum

        from nexuspkm.models import ProcessingStatus, RelationshipType, SourceType

        for cls in (SourceType, ProcessingStatus, RelationshipType):
            assert issubclass(cls, StrEnum)

    def test_entity_exports(self) -> None:
        from pydantic import BaseModel

        from nexuspkm.models import (
            EntitySummary,
            ExtractedEntity,
            ExtractedRelationship,
            ExtractionResult,
        )

        for cls in (EntitySummary, ExtractedEntity, ExtractedRelationship, ExtractionResult):
            assert issubclass(cls, BaseModel)

    def test_search_exports(self) -> None:
        from pydantic import BaseModel

        from nexuspkm.models import (
            DateBucket,
            EntityCount,
            SearchFacets,
            SearchFilters,
            SearchRequest,
            SearchResponse,
            SearchResult,
            TagCount,
        )

        for cls in (
            SearchFilters,
            SearchRequest,
            SearchResult,
            SearchFacets,
            SearchResponse,
            DateBucket,
            EntityCount,
            TagCount,
        ):
            assert issubclass(cls, BaseModel)

    def test_chat_exports(self) -> None:
        from pydantic import BaseModel

        from nexuspkm.models import ChatMessage, ChatSession

        for cls in (ChatMessage, ChatSession):
            assert issubclass(cls, BaseModel)

    def test_score_float_exported(self) -> None:
        from nexuspkm.models import ScoreFloat

        assert ScoreFloat is not None
