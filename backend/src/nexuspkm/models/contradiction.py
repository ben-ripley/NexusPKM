"""Contradiction and queue status models.

Spec: F-006 FR-5, FR-6
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict


class ContradictionType(StrEnum):
    DATE_CONFLICT = "date_conflict"
    STATUS_CONFLICT = "status_conflict"
    ASSIGNMENT_CONFLICT = "assignment_conflict"


class Contradiction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    entity_id: str
    field_name: str
    old_value: str
    new_value: str
    source_doc_id: str
    detected_at: AwareDatetime
    resolved: bool = False
    resolved_at: AwareDatetime | None = None


class QueueStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pending: int
    processing: int
    done: int
    failed: int
