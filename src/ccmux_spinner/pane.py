"""tmux IO + chrome-row detection.

Two responsibilities:

* Locate the input-chrome separator that bounds Claude Code's
  prompt box at the bottom of the pane.
* Shell out to ``tmux`` to discover the pane id and capture pane
  text.

Pure parsing functions live here; the spinner-row classification
(overlay skipping, glyph match, ellipsis test) is in
:mod:`ccmux_spinner.parser` so this module stays focused on
"chrome-or-not" geometry.
"""

from __future__ import annotations

import subprocess

from .errors import PaneCaptureError, TmuxResolutionError

# Empirical against Claude Code 2.1.x.
_CHROME_MIN_LEN = 20
_CHROME_SEARCH_WINDOW = 20
_CHROME_INPUT_MAX_LINES = 8


def _is_chrome_separator(line: str) -> bool:
    """True for a horizontal-rule row that ccmux treats as chrome.

    Real claude-code chrome separators start at column 0; indented
    dashes (e.g. ``  ⎿  ────`` from a rendered tool-result line in
    scrollback) are excluded. Two shapes are accepted:

    1. Pure dashes ``────…────`` of length >= ``_CHROME_MIN_LEN``.
    2. Dash run with embedded text (tmux ``pane-border-status``
       renders the title inside the border row): leading dash run
       must be >= ``_CHROME_MIN_LEN`` and overall dash density >= 60%.
    """
    if not line or line[0] != "─":
        return False
    stripped = line.rstrip()
    if len(stripped) < _CHROME_MIN_LEN:
        return False
    if all(c == "─" for c in stripped):
        return True
    leading_dashes = 0
    for c in stripped:
        if c == "─":
            leading_dashes += 1
        else:
            break
    if leading_dashes < _CHROME_MIN_LEN:
        return False
    dash_count = stripped.count("─")
    return dash_count / len(stripped) >= 0.6


def find_chrome_separator(
    lines: list[str], window: int = _CHROME_SEARCH_WINDOW
) -> int | None:
    """Index of the topmost ``────`` chrome row within the last *window* lines.

    Returns ``None`` when there is no chrome (e.g. session is at a
    raw bash prompt, or pane was just opened).
    """
    start = max(0, len(lines) - window)
    for i in range(start, len(lines)):
        if _is_chrome_separator(lines[i]):
            return i
    return None


def has_input_chrome(lines: list[str]) -> bool:
    """True when Claude's input chrome is rendered at the pane bottom.

    Pattern: a ``────`` separator, followed by a ``❯``-prefixed
    prompt row (with up to a few continuation rows for multi-line
    input), then a second ``────`` separator closing the sandwich.
    """
    if not lines:
        return False
    search_start = max(0, len(lines) - _CHROME_SEARCH_WINDOW)
    for i in range(search_start, len(lines) - 1):
        if not _is_chrome_separator(lines[i]):
            continue
        if not lines[i + 1].lstrip().startswith("❯"):
            continue
        scan_end = min(i + 2 + _CHROME_INPUT_MAX_LINES, len(lines))
        for j in range(i + 2, scan_end):
            if _is_chrome_separator(lines[j]):
                return True
        return False
    return False


# ---------------------------------------------------------------------------
# tmux IO
# ---------------------------------------------------------------------------


def resolve_active_pane_id(tmux_session: str) -> str:
    """Return the active pane id of *tmux_session*.

    Resolution order:
      1. ``tmux display-message -t <tmux_session> -p '#{pane_id}'``
         (no window suffix → tmux returns the active pane).
      2. Fallback: same command with ``:0`` suffix, returning window 0's
         first pane, if step 1 produced empty output or a non-zero
         exit.

    Raises :class:`TmuxResolutionError` when the binary is missing, the
    session does not exist, or neither lookup yields a pane id.
    """

    def _query(target: str) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-t", target, "-p", "#{pane_id}"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise TmuxResolutionError(f"tmux binary not on PATH: {e}") from e
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    rc, pane_id, err = _query(tmux_session)
    if rc == 0 and pane_id:
        return pane_id

    rc2, pane_id2, err2 = _query(f"{tmux_session}:0")
    if rc2 == 0 and pane_id2:
        return pane_id2

    detail = f"active lookup: rc={rc} err={err!r}; :0 lookup: rc={rc2} err={err2!r}"
    raise TmuxResolutionError(
        f"could not resolve a pane id for session {tmux_session!r}; {detail}"
    )


def capture_pane(pane_id: str) -> str:
    """Capture the visible content of a tmux pane.

    Uses ``tmux capture-pane -p -J -t <pane_id>``. ``-J`` joins
    wrapped lines so the ``────`` chrome separator survives wrapping.
    No ``-e``: ANSI escapes are stripped.

    Raises :class:`PaneCaptureError` on failure.
    """
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-p", "-J", "-t", pane_id],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise PaneCaptureError(f"tmux binary not on PATH: {e}") from e
    if result.returncode != 0:
        raise PaneCaptureError(
            f"tmux capture-pane failed for pane {pane_id!r}: {result.stderr.strip()}"
        )
    return result.stdout
