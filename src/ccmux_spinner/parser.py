"""Spinner-row parser.

Anchored from the input-chrome separator and scans **upward**. On
each line above chrome:

* blank → skip
* matches an overlay pattern (tip / score modal) → skip silently
* matches a TodoWrite pattern → **collect** (these rows are
  rendered between the spinner and chrome, and are semantically
  part of the "what is happening right now" view)
* leads with a spinner glyph → classify and stop
* anything else → bail (return ``None``; we do not guess)

The :class:`Spinner` / :class:`IdleDecoration` we build also
carries the collected TodoWrite rows under ``todos``, in visual
top-to-bottom order. ``text`` stays the spinner row itself;
consumers render ``todos`` separately.

This algorithm is a clean port of
``claude_code_state.parser.parse_status_line`` (which the original
ccmux-state lost). The correctness property versus that old
ccmux-state is that any of {tips, score modals, TodoWrite rows}
between the spinner and the chrome no longer cause an Idle
mis-classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pane import find_chrome_separator

# Spinner glyphs Claude Code rotates through on its status row.
# Cycle observed 2026-05-09: `·` `✻` `✽` `✶` `*` (5 frames).
# `✳` and `✢` were in claude-code-state's list and may appear in
# older Claude Code releases — kept for forward compatibility.
_STATUS_SPINNERS = frozenset(["·", "✻", "✽", "✶", "✳", "✢", "*"])

# How far above chrome we search before giving up.
_STATUS_SCAN_WINDOW = 30

# Overlay rows that should be silently skipped during the scan.
# These have no message-stream semantics — they're decoration.
_OVERLAY_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Footer tip line, e.g. `  ⎿  Tip: Connect Claude to your IDE · /ide`.
    re.compile(r"^\s*⎿\s+Tip:\s+"),
    # Session-rating modal (CC 2.1.x+).
    re.compile(r"^\s*●\s*How is Claude doing this session\?"),
    re.compile(r"^\s*\d+:\s*(Bad|OK|Good|Great|Excellent|Loved)\b"),
)

# TodoWrite rows. Rendered between the spinner and chrome while a
# todo list is in scope. Semantically part of the "what is Claude
# doing right now" view, so the parser collects them onto
# ``Activity.todos`` rather than skipping.
_TODO_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Bare checkbox row.
    re.compile(r"^\s*[◼◻☐☒✔✓]"),
    # First-row elbow connector: `  ⎿  ☒ ...`.
    re.compile(r"^\s*⎿\s+[◼◻☐☒✔✓]"),
    # Overflow tail: `      … +7 pending` / `… +6 pending, 1 completed`.
    re.compile(r"^\s*…\s*\+\d+\b"),
)


@dataclass(frozen=True)
class Spinner:
    """Active spinner row above the input chrome.

    Identified by a leading spinner glyph plus ``…`` in the body —
    Claude Code uses the ellipsis to mark "still running". The
    ``text`` field carries the row verbatim (sans the leading
    glyph and surrounding whitespace); consumers that want
    sub-fields parse it themselves.

    ``todos`` carries TodoWrite rows rendered between the spinner
    and chrome, in visual top-to-bottom order. Each string is the
    raw pane line, rstripped only; it already contains the elbow
    connector and indentation Claude Code emits. Empty when no
    todo list is in scope.
    """

    text: str
    todos: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IdleDecoration:
    """Post-turn completion summary above the input chrome.

    Same pane location as the active spinner row, but with no
    ``…`` in the body. Examples: ``Churned for 55s``,
    ``Worked for 12s``. ``todos`` follows :class:`Spinner.todos`
    semantics.
    """

    text: str
    todos: tuple[str, ...] = field(default_factory=tuple)


Activity = Spinner | IdleDecoration | None


def _matches_overlay(line: str) -> bool:
    return any(p.search(line) for p in _OVERLAY_PATTERNS)


def _matches_todo(line: str) -> bool:
    return any(p.search(line) for p in _TODO_PATTERNS)


def parse_pane(pane_text: str) -> Activity:
    """Classify the latest activity row in a Claude Code tmux pane.

    Returns ``Spinner`` while a turn is running, ``IdleDecoration``
    immediately after a turn ends (until the next prompt typed),
    or ``None`` when the pane has no recognizable activity row.
    Either dataclass carries TodoWrite rows between the row and
    chrome under ``todos`` in visual order.
    """
    if not pane_text:
        return None
    lines = pane_text.split("\n")
    chrome_idx = find_chrome_separator(lines)
    if chrome_idx is None:
        return None

    # Collect bottom-up; reverse at the end so todos read in
    # visual top-to-bottom order.
    collected_todos: list[str] = []
    scan_floor = max(chrome_idx - _STATUS_SCAN_WINDOW, -1)
    for i in range(chrome_idx - 1, scan_floor, -1):
        line = lines[i]
        if not line.strip():
            continue
        if _matches_overlay(line):
            continue
        if _matches_todo(line):
            collected_todos.append(line.rstrip())
            continue
        stripped = line.strip()
        if stripped[0] not in _STATUS_SPINNERS:
            return None
        # Defense against false positives where the glyph happens to
        # match but the line is actually unrelated content rendered
        # right above the chrome (e.g. a markdown ``**bold**`` line
        # streamed into the terminal during a turn). A real status
        # row is always ``<glyph> <body>`` with a space between, so
        # require that. Single-glyph lines fall through to the
        # ``not body`` check below.
        if len(stripped) > 1 and not stripped[1].isspace():
            return None
        body = stripped[1:].strip()
        if not body:
            return None
        todos = tuple(reversed(collected_todos))
        if "…" in body:
            return Spinner(text=body, todos=todos)
        return IdleDecoration(text=body, todos=todos)
    return None
