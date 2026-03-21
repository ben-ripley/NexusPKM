"""HTML → Markdown converter for Apple Notes content.

Handles Apple Notes-specific HTML patterns:
- Checklist items (via ``data-checked`` attribute)
- Tables → markdown tables
- Apple Notes styling attributes (stripped by html2text)

Spec: F-009
NXP-68
"""

from __future__ import annotations

import re

import html2text as _html2text

# Matches checked checklist items: <li ... data-checked="true" ...>
_CHECKED_LI_RE = re.compile(
    r'<li([^>]*)data-checked=["\']true["\']([^>]*)>',
    re.IGNORECASE,
)
# Matches unchecked checklist items: <li ... data-checked="false" ...>
_UNCHECKED_LI_RE = re.compile(
    r'<li([^>]*)data-checked=["\']false["\']([^>]*)>',
    re.IGNORECASE,
)


def convert_html_to_markdown(html: str) -> str:
    """Convert Apple Notes HTML body to plain markdown.

    Args:
        html: Raw HTML body from Apple Notes (via AppleScript or SQLite).

    Returns:
        Markdown-formatted string.  Checklist items become ``- [x]``/``- [ ]``
        task lists; tables are rendered as markdown pipe tables; Apple Notes
        inline styles are stripped.
    """
    if not html:
        return ""
    processed = _preprocess_apple_notes_html(html)
    converter = _html2text.HTML2Text()
    converter.body_width = 0  # no line wrapping
    converter.ignore_images = True  # skip embedded images
    converter.unicode_snob = True  # preserve unicode chars
    converter.ul_item_mark = "-"  # use - for unordered list items
    return converter.handle(processed).strip()


def _preprocess_apple_notes_html(html: str) -> str:
    """Normalise Apple Notes-specific HTML before passing to html2text.

    Converts checklist ``<li data-checked="…">`` elements so that html2text
    renders them with ``[x]`` / ``[ ]`` markers.  The markers are injected
    into the ``<li>`` content; html2text then formats each ``<li>`` as a
    list item, producing ``- [x] Text`` with ``ul_item_mark="-"``.
    """
    html = _CHECKED_LI_RE.sub(r"<li\1\2>[x] ", html)
    html = _UNCHECKED_LI_RE.sub(r"<li\1\2>[ ] ", html)
    return html
