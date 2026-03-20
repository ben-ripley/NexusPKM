"""Unit tests for Obsidian markdown parser.

Covers: connectors/obsidian/markdown_parser.py
Spec: F-004
NXP-49, NXP-57
"""

from __future__ import annotations

from nexuspkm.connectors.obsidian.markdown_parser import (
    ParsedNote,
    parse_obsidian_note,
)

# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def test_frontmatter_present() -> None:
    raw = "---\ntitle: My Note\nauthor: Alice\ntags: [work, ideas]\n---\nBody text."
    result = parse_obsidian_note(raw, "my-note")
    assert result.frontmatter["title"] == "My Note"
    assert result.frontmatter["author"] == "Alice"
    assert result.frontmatter["tags"] == ["work", "ideas"]


def test_frontmatter_missing() -> None:
    raw = "No frontmatter here, just body text."
    result = parse_obsidian_note(raw, "note")
    assert result.frontmatter == {}


def test_frontmatter_malformed_yaml() -> None:
    raw = "---\ntitle: [unclosed bracket\n---\nBody."
    result = parse_obsidian_note(raw, "note")
    # Malformed YAML yields empty frontmatter without raising
    assert result.frontmatter == {}


def test_frontmatter_empty_block() -> None:
    raw = "---\n---\nBody text."
    result = parse_obsidian_note(raw, "note")
    assert result.frontmatter == {}


def test_frontmatter_only_no_body() -> None:
    raw = "---\ntitle: Just Frontmatter\n---\n"
    result = parse_obsidian_note(raw, "note")
    assert result.frontmatter["title"] == "Just Frontmatter"


# ---------------------------------------------------------------------------
# Wikilinks
# ---------------------------------------------------------------------------


def test_wikilinks_basic() -> None:
    raw = "See [[Project Alpha]] for details."
    result = parse_obsidian_note(raw, "note")
    assert "Project Alpha" in result.wikilinks


def test_wikilinks_with_alias() -> None:
    raw = "See [[Project Alpha|the alpha project]] for details."
    result = parse_obsidian_note(raw, "note")
    assert "Project Alpha" in result.wikilinks
    assert "the alpha project" not in result.wikilinks


def test_wikilinks_multiple() -> None:
    raw = "Link to [[Note A]] and [[Note B]] here."
    result = parse_obsidian_note(raw, "note")
    assert "Note A" in result.wikilinks
    assert "Note B" in result.wikilinks


def test_wikilinks_not_in_code_block() -> None:
    raw = "Outside\n```\n[[inside code block]]\n```\n[[outside code]]"
    result = parse_obsidian_note(raw, "note")
    assert "outside code" in result.wikilinks
    assert "inside code block" not in result.wikilinks


def test_wikilinks_empty() -> None:
    raw = "No links here."
    result = parse_obsidian_note(raw, "note")
    assert result.wikilinks == []


def test_wikilinks_embed_excluded() -> None:
    """Embeds (![[...]]) must NOT appear in wikilinks."""
    raw = "![[embedded-note]] and [[regular-link]]"
    result = parse_obsidian_note(raw, "note")
    assert "embedded-note" not in result.wikilinks
    assert "regular-link" in result.wikilinks


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tags_inline() -> None:
    raw = "This note is #work and #productivity focused."
    result = parse_obsidian_note(raw, "note")
    assert "work" in result.tags
    assert "productivity" in result.tags


def test_tags_nested() -> None:
    raw = "Topic: #parent/child tag."
    result = parse_obsidian_note(raw, "note")
    assert "parent/child" in result.tags


def test_tags_from_frontmatter_merged() -> None:
    raw = "---\ntags: [meta, review]\n---\nInline #work tag."
    result = parse_obsidian_note(raw, "note")
    assert "meta" in result.tags
    assert "review" in result.tags
    assert "work" in result.tags


def test_tags_deduplicated() -> None:
    raw = "---\ntags: [work]\n---\nInline #work here."
    result = parse_obsidian_note(raw, "note")
    assert result.tags.count("work") == 1


def test_tags_not_in_code_block() -> None:
    raw = "Real #tag outside.\n```\n#not-a-tag-in-code\n```"
    result = parse_obsidian_note(raw, "note")
    assert "tag" in result.tags
    assert "not-a-tag-in-code" not in result.tags


def test_tags_empty() -> None:
    raw = "No tags here, just text."
    result = parse_obsidian_note(raw, "note")
    assert result.tags == []


# ---------------------------------------------------------------------------
# Embeds
# ---------------------------------------------------------------------------


def test_embeds_basic() -> None:
    raw = "![[embedded-note]] in the body."
    result = parse_obsidian_note(raw, "note")
    assert "embedded-note" in result.embeds


def test_embeds_with_alias() -> None:
    raw = "![[image.png|300]]"
    result = parse_obsidian_note(raw, "note")
    assert "image.png" in result.embeds


def test_embeds_not_in_wikilinks() -> None:
    raw = "![[some-embed]]"
    result = parse_obsidian_note(raw, "note")
    assert "some-embed" not in result.wikilinks


def test_embeds_empty() -> None:
    raw = "No embeds here."
    result = parse_obsidian_note(raw, "note")
    assert result.embeds == []


# ---------------------------------------------------------------------------
# Callouts
# ---------------------------------------------------------------------------


def test_callouts_basic() -> None:
    raw = "> [!NOTE] Important\n> This is the callout body."
    result = parse_obsidian_note(raw, "note")
    assert len(result.callouts) == 1
    assert result.callouts[0]["type"] == "NOTE"
    assert result.callouts[0]["title"] == "Important"


def test_callouts_no_title() -> None:
    raw = "> [!WARNING]\n> Watch out."
    result = parse_obsidian_note(raw, "note")
    assert len(result.callouts) == 1
    assert result.callouts[0]["type"] == "WARNING"
    assert result.callouts[0]["title"] == ""


def test_callouts_multiple() -> None:
    raw = "> [!NOTE] First\n> Body\n\nSome text\n\n> [!TIP] Second\n> Tip body"
    result = parse_obsidian_note(raw, "note")
    assert len(result.callouts) == 2


def test_callouts_empty() -> None:
    raw = "No callouts."
    result = parse_obsidian_note(raw, "note")
    assert result.callouts == []


# ---------------------------------------------------------------------------
# Plain content / strip syntax
# ---------------------------------------------------------------------------


def test_strip_wikilink_keeps_display_text() -> None:
    raw = "Read [[Project Alpha|the alpha project]] today."
    result = parse_obsidian_note(raw, "note")
    assert "the alpha project" in result.plain_content
    assert "[[" not in result.plain_content


def test_strip_wikilink_bare_uses_target() -> None:
    raw = "See [[Project Alpha]] for more."
    result = parse_obsidian_note(raw, "note")
    assert "Project Alpha" in result.plain_content
    assert "[[" not in result.plain_content


def test_strip_tags_removed() -> None:
    raw = "This is #important information."
    result = parse_obsidian_note(raw, "note")
    assert "#important" not in result.plain_content
    assert "important" in result.plain_content


def test_strip_embed_removed() -> None:
    raw = "Prefix ![[embedded-note]] suffix."
    result = parse_obsidian_note(raw, "note")
    assert "![[" not in result.plain_content


def test_plain_content_preserves_body_text() -> None:
    raw = "---\ntitle: Test\n---\nHello world, this is the body."
    result = parse_obsidian_note(raw, "note")
    assert "Hello world" in result.plain_content


# ---------------------------------------------------------------------------
# raw_markdown preserved
# ---------------------------------------------------------------------------


def test_raw_markdown_stored() -> None:
    raw = "---\ntitle: T\n---\nBody [[link]]."
    result = parse_obsidian_note(raw, "note")
    assert result.raw_markdown == raw


# ---------------------------------------------------------------------------
# ParsedNote dataclass completeness
# ---------------------------------------------------------------------------


def test_parsed_note_fields() -> None:
    result = parse_obsidian_note("Body text.", "my-note")
    assert isinstance(result, ParsedNote)
    assert isinstance(result.frontmatter, dict)
    assert isinstance(result.wikilinks, list)
    assert isinstance(result.tags, list)
    assert isinstance(result.embeds, list)
    assert isinstance(result.callouts, list)
    assert isinstance(result.plain_content, str)
    assert isinstance(result.raw_markdown, str)
