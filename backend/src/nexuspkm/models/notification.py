"""Pydantic models for Proactive Context Surfacing.

Spec: F-013
NXP-87
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexuspkm.models.schedule import PersonSummary


class NotificationType(StrEnum):
    MEETING_PREP = "meeting_prep"
    RELATED_CONTENT = "related_content"
    CONTRADICTION = "contradiction"
    INSIGHT = "insight"


class NotificationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Notification(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: NotificationType
    title: str
    summary: str
    priority: NotificationPriority
    data: dict[str, object] = Field(default_factory=dict)
    read: bool = False
    created_at: datetime


class NotificationPreferences(BaseModel):
    model_config = ConfigDict(frozen=True)

    meeting_prep_enabled: bool = True
    meeting_prep_lead_time_minutes: int = 60
    related_content_enabled: bool = True
    related_content_threshold: float = 0.7
    contradiction_alerts_enabled: bool = True
    # Global fallback webhook URL (all notification types)
    webhook_url: str | None = None
    # Per-type webhook URLs (take precedence over webhook_url when set)
    webhook_url_meeting_prep: str | None = None
    webhook_url_related_content: str | None = None
    webhook_url_contradiction: str | None = None
    webhook_url_insight: str | None = None

    @field_validator(
        "webhook_url",
        "webhook_url_meeting_prep",
        "webhook_url_related_content",
        "webhook_url_contradiction",
        "webhook_url_insight",
        mode="before",
    )
    @classmethod
    def _require_https(cls, v: object) -> object:
        if v is None:
            return v
        if not isinstance(v, str) or not v.startswith("https://"):
            raise ValueError("webhook URL must use HTTPS")
        return v


class DocumentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    source_type: str
    snippet: str = ""
    created_at: datetime | None = None


class ActionItemSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    status: str = "open"
    assignee_name: str = ""


class MeetingContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    meeting_id: str
    meeting_title: str
    meeting_time: datetime | None
    attendees: list[PersonSummary] = Field(default_factory=list)
    previous_meetings: list[DocumentSummary] = Field(default_factory=list)
    related_tickets: list[DocumentSummary] = Field(default_factory=list)
    related_notes: list[DocumentSummary] = Field(default_factory=list)
    related_emails: list[DocumentSummary] = Field(default_factory=list)
    open_action_items: list[ActionItemSummary] = Field(default_factory=list)
    suggested_agenda: list[str] = Field(default_factory=list)


class RelatedContentAlert(BaseModel):
    model_config = ConfigDict(frozen=True)

    new_document: DocumentSummary
    related_documents: list[DocumentSummary] = Field(default_factory=list)
    connection_type: str  # "same_topic" | "same_people" | "same_project"
    connection_strength: float
    summary: str
