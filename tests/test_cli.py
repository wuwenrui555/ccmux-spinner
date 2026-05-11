"""Smoke tests for the CLI parser + pretty/JSON formatters."""

from __future__ import annotations

import json
import re

from ccmux_spinner import __version__
from ccmux_spinner.cli import (
    _activity_to_json,
    _pretty_main_line,
    _pretty_message,
    _pretty_separator,
    _pretty_todo_lines,
    _visual_trim,
    _visual_width,
    build_parser,
    cmd_version,
)
from ccmux_spinner.parser import IdleDecoration, Spinner

# ---------- parser ----------


def test_parser_watch_subcommand():
    p = build_parser()
    args = p.parse_args(["watch", "my-session"])
    assert args.cmd == "watch"
    assert args.session == "my-session"
    assert args.json is False


def test_parser_watch_json_flag():
    p = build_parser()
    args = p.parse_args(["watch", "s", "--json"])
    assert args.json is True


def test_version_prints(capsys):
    class _A:
        pass

    rc = cmd_version(_A())
    assert rc == 0
    assert capsys.readouterr().out.strip() == __version__


# ---------- separator (visual width fixed) ----------


def test_separator_visual_width_matches_setting(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_PRETTY_WIDTH", "80")
    sep = _pretty_separator(80)
    assert _visual_width(sep) == 80
    assert re.match(r"^─ \d{2}:\d{2}:\d{2}\.\d{3} ─+$", sep)


# ---------- main line ----------


def test_main_line_working_no_trim():
    out = _pretty_main_line(Spinner(text="Thinking… (4s)"), width=100)
    assert out == "[ working ] Thinking… (4s)"


def test_main_line_idle_decoration():
    out = _pretty_main_line(IdleDecoration(text="Churned for 7s"), width=100)
    assert out == "[ idle ] Churned for 7s"


def test_main_line_none_renders_idle_with_empty_body():
    out = _pretty_main_line(None, width=100)
    assert out == "[ idle ] "


def test_main_line_trims_long_body_to_visual_width():
    long_text = "x" * 500
    out = _pretty_main_line(Spinner(text=long_text), width=40)
    assert _visual_width(out) == 40
    assert out.endswith("...")
    assert out.startswith("[ working ] ")


def test_main_line_cjk_visual_width():
    out = _pretty_main_line(Spinner(text="测" * 200), width=40)
    assert _visual_width(out) <= 40
    assert out.endswith("...")


# ---------- todo lines (raw, one row each) ----------


def test_todo_lines_empty_when_no_todos():
    assert _pretty_todo_lines(Spinner(text="t"), width=100) == []


def test_todo_lines_one_per_row_raw_text():
    """Rows render verbatim; no quotes, no list wrapper."""
    rows = ("  ⎿  ☒ first", "       ☒ second", "       ◻ third")
    out = _pretty_todo_lines(Spinner(text="t", todos=rows), width=100)
    assert out == [
        "  ⎿  ☒ first",
        "       ☒ second",
        "       ◻ third",
    ]


def test_todo_lines_each_row_trimmed_independently():
    """A long todo row is truncated with ``...`` on its own line."""
    rows = ("short", "x" * 200, "another short")
    out = _pretty_todo_lines(Spinner(text="t", todos=rows), width=40)
    assert out[0] == "short"
    assert _visual_width(out[1]) == 40
    assert out[1].endswith("...")
    assert out[2] == "another short"


# ---------- full block ----------


def test_pretty_message_multiple_todo_lines(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_PRETTY_WIDTH", "100")
    msg = _pretty_message(Spinner(text="Working…", todos=("☒ a", "◻ b", "☐ c")))
    lines = msg.split("\n")
    # 1 separator + 1 main + 3 todo rows
    assert len(lines) == 5
    assert lines[0].startswith("─ ")
    assert lines[1] == "[ working ] Working…"
    assert lines[2] == "☒ a"
    assert lines[3] == "◻ b"
    assert lines[4] == "☐ c"


def test_pretty_message_two_lines_without_todos(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_PRETTY_WIDTH", "100")
    msg = _pretty_message(Spinner(text="Working…"))
    lines = msg.split("\n")
    assert len(lines) == 2
    assert lines[1] == "[ working ] Working…"


# ---------- JSON output ----------


def test_to_json_spinner_includes_todos():
    s = Spinner(text="t", todos=("☒ a",))
    obj = json.loads(_activity_to_json(s))
    assert obj["kind"] == "Spinner"
    assert obj["text"] == "t"
    assert obj["todos"] == ["☒ a"]


def test_to_json_none():
    assert json.loads(_activity_to_json(None)) == {"kind": "none"}


# ---------- visual width helpers ----------


def test_visual_width_basic():
    assert _visual_width("hello") == 5
    assert _visual_width("中文") == 4
    assert _visual_width("hi 中") == 5


def test_visual_trim_does_not_split_wide_char():
    assert _visual_trim("中文测", 5) == "中文"
    assert _visual_width(_visual_trim("中文测", 5)) == 4
