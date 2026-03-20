"""Obsidian markdown parser — pure functions, no I/O.

Parses Obsidian-flavoured Markdown into a structured ``ParsedNote`` dataclass.
Handles frontmatter, wikilinks, tags, embeds, and callouts.

Spec: F-004
NXP-49, NXP-57
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml


@dataclass
class ParsedNote:
    """Structured representation of an Obsidian markdown note."""

    frontmatter: dict[str, object]
    wikilinks: list[str]
    tags: list[str]
    embeds: list[str]
    callouts: list[dict[str, str]]
    plain_content: str
    raw_markdown: str


def parse_obsidian_note(raw: str, filename_stem: str) -> ParsedNote:
    """Parse an Obsidian markdown note into a ``ParsedNote``.

    Args:
        raw: Raw markdown string.
        filename_stem: The note filename without extension (used as fallback title).

    Returns:
        A fully-populated ``ParsedNote``.
    """
    frontmatter = _parse_frontmatter(raw)
    body = _strip_frontmatter_block(raw)

    embeds = _extract_embeds(body)
    wikilinks = _extract_wikilinks(body)
    tags = _extract_tags(body, frontmatter)
    callouts = _extract_callouts(body)
    plain_content = _strip_obsidian_syntax(body)

    return ParsedNote(
        frontmatter=frontmatter,
        wikilinks=wikilinks,
        tags=tags,
        embeds=embeds,
        callouts=callouts,
        plain_content=plain_content,
        raw_markdown=raw,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
# Matches wikilinks but NOT embeds: [[target]] or [[target|alias]]
_WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\[\]]+?)\]\]")
# Matches embeds: ![[target]] or ![[target|...]]
_EMBED_RE = re.compile(r"!\[\[([^\[\]|]+?)(?:\|[^\[\]]*?)?\]\]")
# Inline tags: #word or #word/subword — not inside a URL or code span
_TAG_RE = re.compile(r"(?<!\S)#([\w/][\w/.-]*)")
# Callout headers: > [!TYPE] Optional Title
_CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\][ \t]*(.*?)[ \t]*$", re.MULTILINE)
# Code blocks (fenced ``` or ~~~)
_CODE_BLOCK_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
# Inline code spans
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Extract and parse YAML frontmatter between --- delimiters."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    yaml_text = match.group(1)
    if not yaml_text.strip():
        return {}
    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            return {}
        return dict(data)
    except yaml.YAMLError:
        return {}


def _strip_frontmatter_block(text: str) -> str:
    """Return text with the frontmatter block removed."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def _mask_code_blocks(text: str) -> str:
    """Replace code block content with spaces (same byte length) to exclude from parsing."""

    def _replace(m: re.Match[str]) -> str:
        return " " * len(m.group(0))

    masked = _CODE_BLOCK_RE.sub(_replace, text)
    masked = _INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), masked)
    return masked


def _extract_embeds(text: str) -> list[str]:
    """Return targets from ![[...]] embed syntax."""
    return _EMBED_RE.findall(text)


def _extract_wikilinks(text: str) -> list[str]:
    """Return link targets from [[...]] wikilink syntax, excluding embeds.

    For [[target|alias]], returns target. Embeds (![[...]]) are excluded.
    """
    masked = _mask_code_blocks(text)
    targets = []
    for match in _WIKILINK_RE.finditer(masked):
        inner = match.group(1)
        target = inner.split("|")[0].strip()
        if target:
            targets.append(target)
    return targets


def _extract_tags(text: str, frontmatter: dict[str, object]) -> list[str]:
    """Return deduplicated tags from inline #tags and frontmatter tags list."""
    masked = _mask_code_blocks(text)
    inline_tags = _TAG_RE.findall(masked)

    fm_tags: list[str] = []
    raw_fm_tags = frontmatter.get("tags")
    if isinstance(raw_fm_tags, list):
        for t in raw_fm_tags:
            if isinstance(t, str):
                fm_tags.append(t)

    seen: set[str] = set()
    result: list[str] = []
    for tag in fm_tags + inline_tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _extract_callouts(text: str) -> list[dict[str, str]]:
    """Return callout blocks with ``type`` and ``title`` keys."""
    return [{"type": m.group(1).upper(), "title": m.group(2)} for m in _CALLOUT_RE.finditer(text)]


def _strip_obsidian_syntax(text: str) -> str:
    """Remove Obsidian-specific syntax, returning plain text suitable for embedding.

    - ``![[embed]]`` → removed
    - ``[[target|alias]]`` → alias
    - ``[[target]]`` → target
    - ``#tag`` → tag (hash removed)
    - Frontmatter already stripped before this is called
    """
    # Remove embeds first (before wikilink pass)
    result = _EMBED_RE.sub("", text)
    # Replace wikilinks with display text
    result = _WIKILINK_RE.sub(lambda m: m.group(1).split("|")[-1].strip(), result)
    # Remove tag hashes (keep the word)
    result = _TAG_RE.sub(lambda m: m.group(1), result)
    return result.strip()
