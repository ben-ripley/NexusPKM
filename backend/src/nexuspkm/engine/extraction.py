"""EntityExtractor — LLM-powered entity and relationship extraction.

Sends document text to an LLM with a structured prompt and parses the
JSON response into an ExtractionResult. JSON parse errors return an empty
result rather than raising (extraction errors must not crash the queue worker).

Spec: F-006 FR-2, FR-3
"""

from __future__ import annotations

import json
import re

import structlog
from pydantic import ValidationError

from nexuspkm.models.entity import ExtractionResult
from nexuspkm.providers.base import BaseLLMProvider

logger = structlog.get_logger(__name__)

# Strip optional ```json ... ``` fences that some LLMs wrap their output in.
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

_EXTRACTION_PROMPT_TEMPLATE = """\
Given the following document, extract all entities and their relationships.

Entity types: Person, Project, Topic, Decision, ActionItem, Meeting

For each entity, provide:
- type: the entity type (person, project, topic, decision, action_item, meeting)
- name: the canonical name
- properties: relevant properties (email, role, date, status, assignee, due_date, etc.)
- confidence: 0.0-1.0 how certain you are
- source_span: the text excerpt where the entity was found

For each relationship, provide:
- source_entity: entity name
- relationship_type: one of ATTENDED, MENTIONED_IN, ASSIGNED_TO, RELATED_TO,
  DECIDED_IN, WORKS_ON, TAGGED_WITH, FOLLOWED_UP_BY, OWNS, BLOCKS
- target_entity: entity name
- confidence: 0.0-1.0
- context: the text that supports this relationship

Return ONLY valid JSON in this exact format:
{
  "entities": [...],
  "relationships": [...],
  "confidence": 0.0
}

Document ID: __DOCUMENT_ID__

Document:
__DOCUMENT_TEXT__"""


class ExtractionError(Exception):
    """Raised when the LLM call itself fails (provider error, timeout, etc.)."""


class EntityExtractor:
    """Extract entities and relationships from document text using an LLM."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def extract(self, document_text: str, document_id: str) -> ExtractionResult:
        """Build prompt, call LLM, parse JSON → ExtractionResult.

        Returns an empty ExtractionResult (entities=[], relationships=[], confidence=0.0)
        on JSON parse errors or Pydantic validation failures — these must not crash
        the background queue worker.

        Raises ExtractionError if the LLM provider itself fails.
        """
        # Use explicit replacement rather than .format() so that document_text
        # containing brace-like tokens (e.g. "{entities}") cannot corrupt the prompt.
        prompt = _EXTRACTION_PROMPT_TEMPLATE.replace("__DOCUMENT_ID__", document_id).replace(
            "__DOCUMENT_TEXT__", document_text
        )
        messages = [{"role": "user", "content": prompt}]

        log = logger.bind(document_id=document_id)
        try:
            response = await self._llm.generate(messages)
        except Exception as exc:
            log.error("extraction.llm_failed", error=str(exc))
            raise ExtractionError(f"LLM call failed: {exc}") from exc

        raw = response.content.strip()
        raw = self._strip_json_fence(raw)

        try:
            data = json.loads(raw)
            result = ExtractionResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as exc:
            log.warning("extraction.parse_failed", error=str(exc), raw_preview=raw[:200])
            return ExtractionResult(entities=[], relationships=[], confidence=0.0)

        log.info(
            "extraction.complete",
            entity_count=len(result.entities),
            relationship_count=len(result.relationships),
            confidence=result.confidence,
        )
        return result

    @staticmethod
    def _strip_json_fence(text: str) -> str:
        """Remove ```json ... ``` or ``` ... ``` fences if present."""
        match = _JSON_FENCE_RE.search(text)
        if match:
            return match.group(1).strip()
        return text
