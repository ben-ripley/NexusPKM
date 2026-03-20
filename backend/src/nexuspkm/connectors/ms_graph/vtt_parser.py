"""VTT transcript parser for Microsoft Teams meeting transcripts.

Parses WebVTT format (as produced by Teams) into structured ParsedTranscript
objects with per-segment speaker attribution.

Teams VTT format uses voice span tags for speaker labelling:
    <v Speaker Name>utterance text</v>

Spec: F-003 FR-3, FR-4
NXP-55
"""

from __future__ import annotations

import re

import structlog
from pydantic import AwareDatetime, BaseModel, ConfigDict

log = structlog.get_logger(__name__)

# Matches a WebVTT timestamp line: HH:MM:SS.mmm --> HH:MM:SS.mmm
_TIMESTAMP_RE = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}\.\d{3})")

# Extracts Teams speaker name and text from <v Speaker Name>text</v>
_SPEAKER_RE = re.compile(r"<v\s+([^>]+)>(.*?)</v>", re.DOTALL)


class TranscriptSegment(BaseModel):
    """A single timed utterance in a transcript."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    speaker: str
    start_time: str
    end_time: str
    text: str


class ParsedTranscript(BaseModel):
    """Fully parsed Teams meeting transcript."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    meeting_id: str
    title: str
    date: AwareDatetime
    duration_minutes: int
    participants: list[str]
    segments: list[TranscriptSegment]
    full_text: str


def parse_vtt(
    content: str,
    *,
    meeting_id: str,
    title: str,
    date: AwareDatetime,
    duration_minutes: int,
    participants: list[str],
) -> ParsedTranscript:
    """Parse a WebVTT string into a ParsedTranscript.

    Gracefully skips malformed or empty cues — never raises.  Returns a
    ParsedTranscript with empty segments when the VTT is empty or invalid.

    Args:
        content: Raw WebVTT file content.
        meeting_id: Graph API meeting ID.
        title: Human-readable meeting title.
        date: Meeting start time (timezone-aware).
        duration_minutes: Meeting duration in minutes.
        participants: List of participant display names from Graph API.

    Returns:
        ParsedTranscript with segments and concatenated full_text.
    """
    if not content.strip():
        return ParsedTranscript(
            meeting_id=meeting_id,
            title=title,
            date=date,
            duration_minutes=duration_minutes,
            participants=participants,
            segments=[],
            full_text="",
        )

    segments: list[TranscriptSegment] = []
    blocks = re.split(r"\n{2,}", content.strip())

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        # Find the first line that looks like a VTT timestamp
        timestamp_idx: int | None = None
        for i, line in enumerate(lines):
            if _TIMESTAMP_RE.match(line):
                timestamp_idx = i
                break

        if timestamp_idx is None:
            continue

        m = _TIMESTAMP_RE.match(lines[timestamp_idx])
        if not m:
            continue

        start_time = m.group(1)
        end_time = m.group(2)

        cue_text = "\n".join(lines[timestamp_idx + 1 :]).strip()
        if not cue_text:
            continue

        speaker_match = _SPEAKER_RE.search(cue_text)
        if speaker_match:
            speaker = speaker_match.group(1).strip()
            text = speaker_match.group(2).strip()
        else:
            speaker = "Unknown"
            text = cue_text

        if not text:
            continue

        try:
            segments.append(
                TranscriptSegment(
                    speaker=speaker,
                    start_time=start_time,
                    end_time=end_time,
                    text=text,
                )
            )
        except Exception:
            log.warning("vtt_parser.segment_skipped", block_preview=block[:80])
            continue

    full_text = "".join(f"{seg.speaker}: {seg.text}\n" for seg in segments)

    return ParsedTranscript(
        meeting_id=meeting_id,
        title=title,
        date=date,
        duration_minutes=duration_minutes,
        participants=participants,
        segments=segments,
        full_text=full_text,
    )
