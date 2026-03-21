"""Unit tests for Apple Notes HTML → Markdown converter.

Covers: connectors/apple_notes/html_converter.py
Spec: F-009
NXP-68
"""

from __future__ import annotations

from nexuspkm.connectors.apple_notes.html_converter import convert_html_to_markdown


def test_plain_html_to_markdown() -> None:
    html = "<html><body><p>Hello world</p></body></html>"
    result = convert_html_to_markdown(html)
    assert "Hello world" in result


def test_unchecked_checklist_item() -> None:
    html = '<ul><li data-checked="false">Todo item</li></ul>'
    result = convert_html_to_markdown(html)
    assert "[ ]" in result
    assert "Todo item" in result


def test_checked_checklist_item() -> None:
    html = '<ul><li data-checked="true">Done item</li></ul>'
    result = convert_html_to_markdown(html)
    assert "[x]" in result
    assert "Done item" in result


def test_mixed_checklist_items() -> None:
    html = (
        "<ul>"
        '<li data-checked="true">Completed task</li>'
        '<li data-checked="false">Pending task</li>'
        "</ul>"
    )
    result = convert_html_to_markdown(html)
    assert "[x]" in result
    assert "[ ]" in result
    assert "Completed task" in result
    assert "Pending task" in result


def test_table_conversion() -> None:
    html = "<table><tr><th>Name</th><th>Value</th></tr><tr><td>Alice</td><td>42</td></tr></table>"
    result = convert_html_to_markdown(html)
    assert "Name" in result
    assert "Value" in result
    assert "Alice" in result
    assert "42" in result


def test_strips_apple_notes_spans() -> None:
    html = (
        "<html><body>"
        '<span style="font-weight: bold; font-family: Helvetica;">Bold text</span>'
        "</body></html>"
    )
    result = convert_html_to_markdown(html)
    assert "Bold text" in result
    assert "font-weight" not in result
    assert "Helvetica" not in result


def test_heading_conversion() -> None:
    html = "<html><body><h1>Title</h1><h2>Section</h2><p>Body</p></body></html>"
    result = convert_html_to_markdown(html)
    assert "Title" in result
    assert "Section" in result
    assert "Body" in result


def test_empty_html_returns_empty_string() -> None:
    result = convert_html_to_markdown("")
    assert result == ""


def test_html_with_divs_and_spans() -> None:
    html = (
        "<html><body><div><span>Line one</span></div><div><span>Line two</span></div></body></html>"
    )
    result = convert_html_to_markdown(html)
    assert "Line one" in result
    assert "Line two" in result


def test_data_checked_single_quotes() -> None:
    """Apple Notes may use single-quoted attributes in some contexts."""
    html = "<ul><li data-checked='true'>Done</li></ul>"
    result = convert_html_to_markdown(html)
    assert "[x]" in result
    assert "Done" in result


def test_list_items_use_dash_marker() -> None:
    html = "<ul><li>Item A</li><li>Item B</li></ul>"
    result = convert_html_to_markdown(html)
    # html2text with ul_item_mark='-' produces "- Item A"
    assert "- " in result
    assert "Item A" in result
