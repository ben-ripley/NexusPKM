"""Pydantic models for the Schedule & Task Management feature.

Spec: F-012
NXP-86
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PrioritizedItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str
    entity_type: str
    title: str
    priority_score: float = Field(ge=0.0, le=100.0)
    urgency: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    factors: list[str] = Field(default_factory=list)


class MeetingSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    date: datetime | None = None
    duration_minutes: int = 0


class ContextItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    source_type: str
    title: str
    snippet: str = ""


class MeetingPrep(BaseModel):
    model_config = ConfigDict(frozen=True)

    meeting: MeetingSummary
    relevant_context: list[ContextItem] = Field(default_factory=list)
    suggested_talking_points: list[str] = Field(default_factory=list)
    action_items_to_follow_up: list[PrioritizedItem] = Field(default_factory=list)


class DailyDigest(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    upcoming_meetings: list[MeetingPrep] = Field(default_factory=list)
    action_items: list[PrioritizedItem] = Field(default_factory=list)
    overdue_items: list[PrioritizedItem] = Field(default_factory=list)
    new_insights: list[str] = Field(default_factory=list)
    generated_at: datetime


class PersonSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    email: str = ""


class MemberWorkload(BaseModel):
    model_config = ConfigDict(frozen=True)

    person: PersonSummary
    open_action_items: int = 0
    total_story_points: int = 0
    meetings_this_week: int = 0
    workload_score: float = Field(ge=0.0, le=100.0)
    status: str
    top_items: list[PrioritizedItem] = Field(default_factory=list)


class OverlapAlert(BaseModel):
    model_config = ConfigDict(frozen=True)

    topic: str
    people_involved: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    description: str = ""


class TeamWorkload(BaseModel):
    model_config = ConfigDict(frozen=True)

    members: list[MemberWorkload] = Field(default_factory=list)
    overlap_alerts: list[OverlapAlert] = Field(default_factory=list)
