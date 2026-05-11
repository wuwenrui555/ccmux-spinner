"""ccmux-spinner CLI: ``ccmux-spinner watch <session>``.

Pretty output mirrors claude-tap's watch-messages format —
separator line with emit time, main line with ``[ state ]`` and
the spinner / decoration text, then one line per TodoWrite row
(if any), then a blank line between blocks.

Layout (no todos)::

    ─ HH:MM:SS.mmm ───────────────────────────────────────────
    [ working ] <spinner text>
    <blank>

Layout (with todos)::

    ─ HH:MM:SS.mmm ───────────────────────────────────────────
    [ working ] <spinner text>
      ⎿  ☒ first
           ☒ second
           ◻ third
    <blank>

All lines (separator, main, each todo) trim to a common visual
cell cap so CJK and ASCII render at comparable widths; both the
cap and the separator width share the single
``CCMUX_SPINNER_PRETTY_WIDTH`` setting.

``--json`` switches to one JSON object per snapshot (text + todos
together), for pipe-friendly consumers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import unicodedata
from dataclasses import asdict
from datetime import UTC, datetime

from . import __version__, config
from .errors import PaneCaptureError, TmuxResolutionError
from .monitor import SpinnerMonitor
from .parser import Spinner

_PRETTY_TRUNCATION_MARKER = "..."


def _now_timestamp() -> str:
    """Wall-clock UTC ``HH:MM:SS.mmm`` for emit-side timestamping."""
    now = datetime.now(UTC)
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"


def _visual_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in s)


def _visual_trim(s: str, width: int) -> str:
    if width <= 0:
        return ""
    w = 0
    out: list[str] = []
    for ch in s:
        char_w = 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        if w + char_w > width:
            break
        out.append(ch)
        w += char_w
    return "".join(out)


def _pretty_separator(width: int) -> str:
    """``─ HH:MM:SS.mmm ─...─`` to exact visual *width*."""
    now = _now_timestamp()
    prefix = f"─ {now} "
    rest = max(0, width - len(prefix))
    return prefix + "─" * rest


def _state_label(activity) -> str:
    """``working`` for active spinner, ``idle`` otherwise (None included)."""
    return "working" if isinstance(activity, Spinner) else "idle"


def _activity_text(activity) -> str:
    if activity is None:
        return ""
    return activity.text


def _activity_todos(activity) -> tuple[str, ...]:
    if activity is None:
        return ()
    return activity.todos


def _pretty_main_line(activity, width: int) -> str:
    label = _state_label(activity)
    head = f"[ {label} ] "
    body = _activity_text(activity)
    cap = max(0, width - _visual_width(head))
    if _visual_width(body) > cap:
        keep = max(0, cap - _visual_width(_PRETTY_TRUNCATION_MARKER))
        body = _visual_trim(body, keep) + _PRETTY_TRUNCATION_MARKER
    return head + body


def _pretty_todo_lines(activity, width: int) -> list[str]:
    """One raw pane line per TodoWrite row, visual-trimmed to ``width``.

    Returns ``[]`` when the activity has no todos. The todo rows
    are already valid single-line text (they came from a pane line
    split by ``\\n``), so no escaping or quoting is applied —
    each row prints verbatim. If a row is longer than ``width``
    cells it is truncated with ``...``.
    """
    todos = _activity_todos(activity)
    out: list[str] = []
    for row in todos:
        if _visual_width(row) > width:
            keep = max(0, width - _visual_width(_PRETTY_TRUNCATION_MARKER))
            out.append(_visual_trim(row, keep) + _PRETTY_TRUNCATION_MARKER)
        else:
            out.append(row)
    return out


def _pretty_message(activity) -> str:
    """Return the multi-line block (no trailing blank — caller adds it).

    Always emits separator + main line. Each TodoWrite row, if
    present, is appended as its own line in visual top-to-bottom
    order.
    """
    width = config.pretty_width()
    lines = [_pretty_separator(width), _pretty_main_line(activity, width)]
    lines.extend(_pretty_todo_lines(activity, width))
    return "\n".join(lines)


def _activity_to_json(activity) -> str:
    if activity is None:
        return json.dumps({"kind": "none"})
    d = asdict(activity)
    return json.dumps(
        {"kind": type(activity).__name__, **d},
        ensure_ascii=False,
    )


async def _watch_async(args) -> int:
    try:
        async with SpinnerMonitor(args.session) as mon:
            async for activity in mon:
                if args.json:
                    print(_activity_to_json(activity), flush=True)
                else:
                    print(_pretty_message(activity), flush=True)
                    print(flush=True)
    except TmuxResolutionError as e:
        print(f"ccmux-spinner: {e}", file=sys.stderr)
        return 1
    except PaneCaptureError as e:
        print(f"ccmux-spinner: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_watch(args) -> int:
    try:
        return asyncio.run(_watch_async(args))
    except KeyboardInterrupt:
        return 0


def cmd_version(args) -> int:
    print(__version__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccmux-spinner")
    sub = parser.add_subparsers(dest="cmd")

    p_watch = sub.add_parser("watch", help="Watch a tmux session's pane spinner")
    p_watch.add_argument("session", help="tmux session name")
    p_watch.add_argument(
        "--json",
        action="store_true",
        help="One JSON object per snapshot instead of pretty blocks",
    )
    p_watch.set_defaults(fn=cmd_watch)

    sub.add_parser("version", help="Print package version").set_defaults(fn=cmd_version)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "fn"):
        parser.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
