"""Unit tests for VTT transcript parser.

Covers: connectors/ms_graph/vtt_parser.py
Spec refs: F-003 FR-3, FR-4
NXP-55
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TypedDict

import pytest

from nexuspkm.connectors.ms_graph.vtt_parser import ParsedTranscript, TranscriptSegment, parse_vtt

_DATE = datetime.datetime(2026, 3, 15, 9, 0, 0, tzinfo=datetime.UTC)
_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


class _ParseVttKwargs(TypedDict):
    meeting_id: str
    title: str
    date: datetime.datetime
    duration_minutes: int
    participants: list[str]


@pytest.fixture
def sample_vtt() -> str:
    return (_FIXTURE_DIR / "sample_transcript.vtt").read_text()


def _kwargs(
    *,
    meeting_id: str = "meeting-001",
    title: str = "Team Standup",
    participants: list[str] | None = None,
) -> _ParseVttKwargs:
    return _ParseVttKwargs(
        meeting_id=meeting_id,
        title=title,
        date=_DATE,
        duration_minutes=30,
        participants=(
            participants
            if participants is not None
            else ["Alice Smith", "Bob Jones", "Carol White"]
        ),
    )


class TestParseValidVtt:
    def test_parse_valid_vtt_multi_speaker(self, sample_vtt: str) -> None:
        result = parse_vtt(sample_vtt, **_kwargs())
        assert isinstance(result, ParsedTranscript)
        assert len(result.segments) == 6
        assert result.meeting_id == "meeting-001"
        assert result.title == "Team Standup"
        assert result.duration_minutes == 30

    def test_parse_valid_vtt_segment_fields(self, sample_vtt: str) -> None:
        result = parse_vtt(sample_vtt, **_kwargs())
        first = result.segments[0]
        assert isinstance(first, TranscriptSegment)
        assert first.speaker == "Alice Smith"
        assert first.start_time == "00:00:01.000"
        assert first.end_time == "00:00:05.000"
        assert "Hello everyone" in first.text

    def test_parse_valid_vtt_all_speakers_present(self, sample_vtt: str) -> None:
        result = parse_vtt(sample_vtt, **_kwargs())
        speakers = {seg.speaker for seg in result.segments}
        assert "Alice Smith" in speakers
        assert "Bob Jones" in speakers
        assert "Carol White" in speakers

    def test_parse_vtt_speaker_deduplication(self, sample_vtt: str) -> None:
        # Alice and Bob each appear twice; participants list should reflect what was passed
        result = parse_vtt(sample_vtt, **_kwargs())
        # Segments should each have one speaker (no merging)
        alice_segs = [s for s in result.segments if s.speaker == "Alice Smith"]
        bob_segs = [s for s in result.segments if s.speaker == "Bob Jones"]
        assert len(alice_segs) == 2
        assert len(bob_segs) == 2

        # participants list itself should be deduplicated (no repeated names)
        assert len(result.participants) == len(set(result.participants))


class TestFullTextFormat:
    def test_full_text_format(self, sample_vtt: str) -> None:
        result = parse_vtt(sample_vtt, **_kwargs())
        lines = result.full_text.splitlines()
        # Every non-empty line should be "Speaker: text"
        for line in lines:
            if line.strip():
                assert ": " in line, f"Expected 'Speaker: text' format, got: {line!r}"

    def test_full_text_contains_all_speakers(self, sample_vtt: str) -> None:
        result = parse_vtt(sample_vtt, **_kwargs())
        assert "Alice Smith:" in result.full_text
        assert "Bob Jones:" in result.full_text
        assert "Carol White:" in result.full_text

    def test_full_text_ends_with_newline_per_line(self, sample_vtt: str) -> None:
        result = parse_vtt(sample_vtt, **_kwargs())
        # Each segment produces exactly one "Speaker: text\n" line
        assert result.full_text.count("\n") == len(result.segments)


class TestEdgeCases:
    def test_parse_empty_vtt(self) -> None:
        result = parse_vtt("", **_kwargs())
        assert isinstance(result, ParsedTranscript)
        assert result.segments == []
        assert result.full_text == ""

    def test_parse_whitespace_only_vtt(self) -> None:
        result = parse_vtt("   \n\n  ", **_kwargs())
        assert result.segments == []
        assert result.full_text == ""

    def test_parse_malformed_vtt_no_crash(self) -> None:
        malformed = (
            "WEBVTT\n\n"
            "NOT A TIMESTAMP\n"
            "some text\n\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "<v Alice>Valid cue.</v>\n\n"
            "00:00:BAD --> 00:00:BAD\n"
            "<v Bob>Bad timestamp cue.</v>\n"
        )
        result = parse_vtt(malformed, **_kwargs())
        # Must not raise; valid cue should be parsed
        assert isinstance(result, ParsedTranscript)
        assert len(result.segments) >= 1
        assert result.segments[0].speaker == "Alice"

    def test_parse_truncated_cue_no_crash(self) -> None:
        truncated = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n"
        result = parse_vtt(truncated, **_kwargs())
        assert isinstance(result, ParsedTranscript)
        assert result.segments == []

    def test_parse_vtt_without_speaker_labels(self) -> None:
        no_labels = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:05.000\n"
            "Hello everyone.\n\n"
            "00:00:06.000 --> 00:00:10.000\n"
            "Let us get started.\n"
        )
        result = parse_vtt(no_labels, **_kwargs())
        assert len(result.segments) == 2
        # Speaker defaults to "Unknown" when no <v> tag present
        assert all(seg.speaker == "Unknown" for seg in result.segments)

    def test_parse_vtt_preserves_participants(self) -> None:
        result = parse_vtt("WEBVTT\n\n", **_kwargs(participants=["Alice", "Bob"]))
        assert result.participants == ["Alice", "Bob"]

    def test_parse_vtt_date_preserved(self, sample_vtt: str) -> None:
        result = parse_vtt(sample_vtt, **_kwargs())
        assert result.date == _DATE

    def test_parse_vtt_webvtt_header_ignored(self) -> None:
        vtt_with_header = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<v Alice>Only cue.</v>\n"
        result = parse_vtt(vtt_with_header, **_kwargs())
        assert len(result.segments) == 1
        assert result.segments[0].speaker == "Alice"
