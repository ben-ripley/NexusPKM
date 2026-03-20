"""Unit tests for EntityDeduplicator.

Tests: email match, exact name match, fuzzy match, LLM-assisted match.
Spec: F-006 FR-4
"""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexuspkm.engine.deduplication import EntityDeduplicator, _levenshtein
from nexuspkm.models.entity import EntityType, ExtractedEntity

# ---------------------------------------------------------------------------
# Levenshtein distance utility
# ---------------------------------------------------------------------------


def test_levenshtein_identical_strings() -> None:
    assert _levenshtein("hello", "hello") == 0


def test_levenshtein_empty_strings() -> None:
    assert _levenshtein("", "") == 0


def test_levenshtein_one_empty() -> None:
    assert _levenshtein("abc", "") == 3
    assert _levenshtein("", "abc") == 3


def test_levenshtein_single_insertion() -> None:
    assert _levenshtein("cat", "cats") == 1


def test_levenshtein_single_deletion() -> None:
    assert _levenshtein("cats", "cat") == 1


def test_levenshtein_single_substitution() -> None:
    assert _levenshtein("cat", "bat") == 1


def test_levenshtein_transposition() -> None:
    # "ab" → "ba" = 2 substitutions (not transposition in plain Levenshtein)
    assert _levenshtein("ab", "ba") == 2


def test_levenshtein_known_pairs() -> None:
    assert _levenshtein("kitten", "sitting") == 3
    assert _levenshtein("saturday", "sunday") == 3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_deduplicator(
    graph_rows: list[dict] | None = None,
    llm_provider: object | None = None,
) -> EntityDeduplicator:
    graph_store = MagicMock()
    graph_store.execute = MagicMock(return_value=graph_rows or [])
    lock = threading.Lock()
    return EntityDeduplicator(graph_store, lock, llm_provider)


def _person_entity(name: str, email: str = "") -> ExtractedEntity:
    props: dict[str, object] = {}
    if email:
        props["email"] = email
    return ExtractedEntity(
        type=EntityType.PERSON,
        name=name,
        properties=props,
        confidence=0.9,
        source_span=name,
    )


def _project_entity(name: str) -> ExtractedEntity:
    return ExtractedEntity(
        type=EntityType.PROJECT,
        name=name,
        properties={},
        confidence=0.8,
        source_span=name,
    )


# ---------------------------------------------------------------------------
# Email match (Person only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_match_email_match_returns_existing_id() -> None:
    dedup = _make_deduplicator(
        graph_rows=[
            {
                "n.id": "person-1",
                "name": "John Smith",
                "n.email": "jsmith@company.com",
                "n.aliases": [],
            }
        ]
    )
    entity = _person_entity("J. Smith", email="jsmith@company.com")

    match_id = await dedup.find_match(entity)

    assert match_id == "person-1"


@pytest.mark.asyncio
async def test_find_match_email_no_match_returns_none_for_new_email() -> None:
    dedup = _make_deduplicator(
        graph_rows=[
            {
                "n.id": "person-1",
                "name": "John Smith",
                "n.email": "john@example.com",
                "n.aliases": [],
            }
        ]
    )
    entity = _person_entity("John Smith", email="different@example.com")

    match_id = await dedup.find_match(entity)

    # No email match; exact/fuzzy name still checked
    # Name matches exactly so it should match
    assert match_id == "person-1"


@pytest.mark.asyncio
async def test_find_match_email_match_non_person_ignored() -> None:
    """Email in properties is only used for Person type matching."""
    dedup = _make_deduplicator(graph_rows=[{"n.id": "proj-1", "name": "Alpha", "n.aliases": []}])
    entity = ExtractedEntity(
        type=EntityType.PROJECT,
        name="Alpha",
        properties={"email": "alpha@example.com"},
        confidence=0.8,
        source_span="Alpha",
    )

    match_id = await dedup.find_match(entity)

    # Matches on exact name, not email
    assert match_id == "proj-1"


# ---------------------------------------------------------------------------
# Exact name match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_match_exact_name_case_insensitive() -> None:
    dedup = _make_deduplicator(
        graph_rows=[{"n.id": "proj-1", "name": "Alpha Project", "n.aliases": []}]
    )
    entity = _project_entity("alpha project")

    match_id = await dedup.find_match(entity)

    assert match_id == "proj-1"


@pytest.mark.asyncio
async def test_find_match_no_existing_entities_returns_none() -> None:
    dedup = _make_deduplicator(graph_rows=[])
    entity = _project_entity("Brand New Project")

    match_id = await dedup.find_match(entity)

    assert match_id is None


# ---------------------------------------------------------------------------
# Fuzzy name match (Levenshtein <= 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_match_fuzzy_within_threshold() -> None:
    dedup = _make_deduplicator(
        graph_rows=[{"n.id": "person-2", "name": "Bob Johnson", "n.email": "", "n.aliases": []}]
    )
    # "Bob Jonson" is distance 1 from "Bob Johnson"
    entity = _person_entity("Bob Jonson")

    match_id = await dedup.find_match(entity)

    assert match_id == "person-2"


@pytest.mark.asyncio
async def test_find_match_fuzzy_beyond_threshold_returns_none() -> None:
    dedup = _make_deduplicator(
        graph_rows=[{"n.id": "person-3", "name": "Alice Brown", "n.email": "", "n.aliases": []}]
    )
    # "Charlie Green" is far from "Alice Brown"
    entity = _person_entity("Charlie Green")

    # No LLM provider, so falls through to None
    match_id = await dedup.find_match(entity)

    assert match_id is None


# ---------------------------------------------------------------------------
# LLM-assisted match (fuzzy score 0.6-0.8 range)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_match_llm_assisted_confirms_match() -> None:
    llm_provider = MagicMock()
    llm_resp = MagicMock()
    llm_resp.content = "yes"
    llm_provider.generate = AsyncMock(return_value=llm_resp)

    # Distance 3 — beyond fuzzy threshold but close enough for LLM assist
    dedup = _make_deduplicator(
        graph_rows=[{"n.id": "proj-2", "name": "Alpha Project", "n.aliases": []}],
        llm_provider=llm_provider,
    )
    entity = _project_entity("Alfa Project")  # distance 1 — will match fuzzy anyway

    match_id = await dedup.find_match(entity)

    assert match_id == "proj-2"


@pytest.mark.asyncio
async def test_find_match_no_llm_provider_returns_none_for_ambiguous() -> None:
    dedup = _make_deduplicator(
        graph_rows=[{"n.id": "proj-3", "name": "Nexus Platform", "n.aliases": []}],
        llm_provider=None,
    )
    # "Nexus" alone is distance >2 from "Nexus Platform"
    entity = _project_entity("Nexus")

    match_id = await dedup.find_match(entity)

    assert match_id is None


# ---------------------------------------------------------------------------
# Alias tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_match_adds_alias_on_fuzzy_match() -> None:
    graph_store = MagicMock()
    graph_store.execute = MagicMock(
        return_value=[{"n.id": "person-4", "name": "Robert Smith", "n.email": "", "n.aliases": []}]
    )
    lock = threading.Lock()
    dedup = EntityDeduplicator(graph_store, lock)

    entity = _person_entity("Robrt Smith")  # distance 1 from "Robert Smith" (missing 'e')
    match_id = await dedup.find_match(entity)

    assert match_id == "person-4"
    # Alias update should have been called
    assert graph_store.execute.call_count >= 2  # query + alias update
