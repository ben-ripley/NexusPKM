"""Relationship type enumeration for the knowledge graph.

Defines the canonical set of relationship types used in Kuzu graph storage
and entity extraction.

Spec: F-002 FR-4
"""

from __future__ import annotations

from enum import StrEnum


class RelationshipType(StrEnum):
    ATTENDED = "ATTENDED"
    MENTIONED_IN = "MENTIONED_IN"
    ASSIGNED_TO = "ASSIGNED_TO"
    RELATED_TO = "RELATED_TO"
    DECIDED_IN = "DECIDED_IN"
    WORKS_ON = "WORKS_ON"
    TAGGED_WITH = "TAGGED_WITH"
    FOLLOWED_UP_BY = "FOLLOWED_UP_BY"
    OWNS = "OWNS"
    BLOCKS = "BLOCKS"
