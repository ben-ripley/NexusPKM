"""Unit tests for EntityExtractor.

Tests: LLM prompt construction, JSON parsing, error handling.
Spec: F-006 FR-2, FR-3
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.engine.extraction import EntityExtractor, ExtractionError
from nexuspkm.models.entity import EntityType, ExtractionResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_extractor() -> tuple[EntityExtractor, AsyncMock]:
    provider = MagicMock()
    provider.generate = AsyncMock()
    extractor = EntityExtractor(provider)
    return extractor, provider


def _llm_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    return resp


# ---------------------------------------------------------------------------
# Happy-path extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_returns_entities_and_relationships() -> None:
    extractor, provider = _make_extractor()
    payload = {
        "entities": [
            {
                "type": "person",
                "name": "Alice Smith",
                "properties": {"email": "alice@example.com"},
                "confidence": 0.9,
                "source_span": "Alice Smith said hello",
            }
        ],
        "relationships": [
            {
                "source_entity": "Alice Smith",
                "relationship_type": "MENTIONED_IN",
                "target_entity": "doc-1",
                "confidence": 0.8,
                "context": "Alice was mentioned",
            }
        ],
        "confidence": 0.85,
    }
    provider.generate.return_value = _llm_response(json.dumps(payload))

    result = await extractor.extract("Alice Smith said hello", "doc-1")

    assert isinstance(result, ExtractionResult)
    assert len(result.entities) == 1
    assert result.entities[0].name == "Alice Smith"
    assert result.entities[0].type == EntityType.PERSON
    assert result.entities[0].confidence == pytest.approx(0.9)
    assert len(result.relationships) == 1
    assert result.relationships[0].source_entity == "Alice Smith"
    assert result.confidence == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_extract_empty_document_returns_empty_result() -> None:
    extractor, provider = _make_extractor()
    payload = {"entities": [], "relationships": [], "confidence": 0.0}
    provider.generate.return_value = _llm_response(json.dumps(payload))

    result = await extractor.extract("No entities here", "doc-2")

    assert result.entities == []
    assert result.relationships == []
    assert result.confidence == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_extract_all_entity_types() -> None:
    extractor, provider = _make_extractor()
    entities = [
        {"type": t, "name": f"Test {t}", "properties": {}, "confidence": 0.7, "source_span": "x"}
        for t in ["person", "project", "topic", "decision", "action_item", "meeting"]
    ]
    payload = {"entities": entities, "relationships": [], "confidence": 0.7}
    provider.generate.return_value = _llm_response(json.dumps(payload))

    result = await extractor.extract("some text", "doc-3")

    types = {e.type for e in result.entities}
    assert EntityType.PERSON in types
    assert EntityType.PROJECT in types
    assert EntityType.TOPIC in types
    assert EntityType.DECISION in types
    assert EntityType.ACTION_ITEM in types
    assert EntityType.MEETING in types


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_sends_document_text_in_prompt() -> None:
    extractor, provider = _make_extractor()
    payload = {"entities": [], "relationships": [], "confidence": 0.0}
    provider.generate.return_value = _llm_response(json.dumps(payload))

    doc_text = "The project deadline is March 15."
    await extractor.extract(doc_text, "doc-4")

    call_args = provider.generate.call_args
    messages = call_args[0][0]
    assert any(doc_text in msg.get("content", "") for msg in messages)


@pytest.mark.asyncio
async def test_extract_prompt_includes_entity_types() -> None:
    extractor, provider = _make_extractor()
    payload = {"entities": [], "relationships": [], "confidence": 0.0}
    provider.generate.return_value = _llm_response(json.dumps(payload))

    await extractor.extract("text", "doc-5")

    call_args = provider.generate.call_args
    messages = call_args[0][0]
    full_prompt = " ".join(msg.get("content", "") for msg in messages)
    assert "Person" in full_prompt
    assert "Project" in full_prompt
    assert "Topic" in full_prompt
    assert "Decision" in full_prompt
    assert "ActionItem" in full_prompt
    assert "Meeting" in full_prompt


# ---------------------------------------------------------------------------
# Error handling — must not crash, returns empty result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_malformed_json_returns_empty_result() -> None:
    extractor, provider = _make_extractor()
    provider.generate.return_value = _llm_response("this is not json {{{")

    result = await extractor.extract("some text", "doc-6")

    assert result.entities == []
    assert result.relationships == []
    assert result.confidence == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_extract_invalid_schema_returns_empty_result() -> None:
    extractor, provider = _make_extractor()
    # Valid JSON but wrong schema
    provider.generate.return_value = _llm_response(json.dumps({"wrong": "schema"}))

    result = await extractor.extract("some text", "doc-7")

    assert result.entities == []
    assert result.relationships == []


@pytest.mark.asyncio
async def test_extract_llm_failure_raises_extraction_error() -> None:
    extractor, provider = _make_extractor()
    provider.generate.side_effect = RuntimeError("LLM unavailable")

    with pytest.raises(ExtractionError):
        await extractor.extract("some text", "doc-8")


@pytest.mark.asyncio
async def test_extract_json_embedded_in_markdown_fences() -> None:
    """LLMs often wrap JSON in ```json ... ``` blocks."""
    extractor, provider = _make_extractor()
    payload = {"entities": [], "relationships": [], "confidence": 0.5}
    provider.generate.return_value = _llm_response(f"```json\n{json.dumps(payload)}\n```")

    result = await extractor.extract("some text", "doc-9")

    assert result.confidence == pytest.approx(0.5)
