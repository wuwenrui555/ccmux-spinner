"""Tests for parse_pane: anchor-from-chrome + skip-overlays algorithm."""

from __future__ import annotations

from ccmux_spinner.parser import (
    IdleDecoration,
    Spinner,
    parse_pane,
)

# A canonical bottom of pane: spinner row, blank, two-rule-bracketed
# input chrome with `❯ ` prompt and a closing rule.
_CHROME = "─" * 60
_INPUT = "\n".join([_CHROME, "❯ ", _CHROME])


def _pane(*lines_above_chrome: str) -> str:
    return "\n".join([*lines_above_chrome, _INPUT])


def _spinner_row(glyph: str, body: str) -> str:
    return f"{glyph} {body}"


# ---------- Spinner ----------


def test_active_spinner_above_chrome():
    pane = _pane("✻ Thinking… (16s · ↑ 827 tokens)")
    out = parse_pane(pane)
    assert isinstance(out, Spinner)
    assert "Thinking" in out.text


def test_completion_summary_above_chrome():
    pane = _pane("✻ Churned for 55s")
    out = parse_pane(pane)
    assert isinstance(out, IdleDecoration)
    assert "Churned" in out.text


def test_each_spinner_glyph_recognized():
    for glyph in ("·", "✻", "✽", "✶", "*", "✳", "✢"):
        pane = _pane(_spinner_row(glyph, "Doing… (3s)"))
        out = parse_pane(pane)
        assert isinstance(out, Spinner), glyph


# ---------- Overlay skipping (the regression cases) ----------


def test_skips_footer_tip_above_spinner():
    pane = _pane(
        "✻ Thinking… (4s · ↑ 100 tokens)",
        "  ⎿  Tip: Connect Claude to your IDE · /ide",
    )
    out = parse_pane(pane)
    assert isinstance(out, Spinner), "tip line should be skipped, spinner found"


def test_skips_score_modal_above_spinner():
    pane = _pane(
        "✻ Thinking… (4s · ↑ 100 tokens)",
        "● How is Claude doing this session?",
        "1: Bad",
        "2: OK",
        "3: Good",
        "4: Excellent",
        "5: Loved it",
    )
    out = parse_pane(pane)
    assert isinstance(out, Spinner)


def test_collects_todowrite_above_spinner():
    """TodoWrite rows are not skipped — they're collected onto Spinner.todos in visual order."""
    pane = _pane(
        "✻ Thinking… (4s · ↑ 100 tokens)",
        "  ⎿  ☒ first done",
        "       ☒ second done",
        "       ◻ third pending",
        "       … +5 pending",
    )
    out = parse_pane(pane)
    assert isinstance(out, Spinner)
    assert out.text == "Thinking… (4s · ↑ 100 tokens)"
    # Visual top-to-bottom order (same as how they appear on screen).
    assert out.todos == (
        "  ⎿  ☒ first done",
        "       ☒ second done",
        "       ◻ third pending",
        "       … +5 pending",
    )


def test_stacked_overlays_and_todos_mix():
    """A tip (overlay → skip) + a todo (collect) above the spinner."""
    pane = _pane(
        "✻ Thinking… (4s · ↑ 100 tokens)",
        "  ⎿  ☒ task",
        "  ⎿  Tip: tip line",
    )
    out = parse_pane(pane)
    assert isinstance(out, Spinner)
    assert out.todos == ("  ⎿  ☒ task",)


def test_blank_lines_between_spinner_and_overlays():
    pane = _pane(
        "✻ Thinking… (4s · ↑ 100 tokens)",
        "",
        "  ⎿  Tip: tip line",
        "",
    )
    out = parse_pane(pane)
    assert isinstance(out, Spinner)


# ---------- None / not classifiable ----------


def test_no_chrome_returns_none():
    assert parse_pane("just some bash output\n$ ls\n") is None


def test_empty_pane_returns_none():
    assert parse_pane("") is None


def test_unknown_content_above_chrome_returns_none():
    pane = _pane("> some user typed stuff but no spinner glyph here")
    assert parse_pane(pane) is None


def test_only_overlays_and_todos_no_spinner_returns_none():
    """Without a spinner glyph above chrome, we can't classify."""
    pane = _pane("  ⎿  ☒ a", "  ⎿  Tip: hi")
    assert parse_pane(pane) is None


def test_spinner_with_no_todos_has_empty_tuple():
    pane = _pane("✻ Thinking… (1s)")
    out = parse_pane(pane)
    assert isinstance(out, Spinner)
    assert out.todos == ()


def test_markdown_bold_above_chrome_not_spinner():
    """A ``**bold**`` markdown line rendered above chrome must NOT be classified.

    Regression test: ``*`` is in ``_STATUS_SPINNERS`` (because CC's
    5-frame cycle includes it), but markdown-bold lines start with
    ``*`` too. We require the glyph to be followed by whitespace to
    discriminate.
    """
    pane = _pane("**第一件事：验证 Esc 是否 fire stop hook**。")
    assert parse_pane(pane) is None


def test_bullet_list_above_chrome_not_spinner():
    """``* item`` (no leading space) is also rejected."""
    # Note: ``* item`` strips to ``* item`` and stripped[1]==' ', so it
    # WOULD match. The case we reject is ``*item`` (no space) and
    # ``**bold**`` (second char is also ``*``). Verify both.
    pane = _pane("*item")
    assert parse_pane(pane) is None


def test_double_dot_not_spinner():
    """A bare ``··`` line (e.g. a separator) is also rejected."""
    pane = _pane("··")
    assert parse_pane(pane) is None


def test_idle_decoration_with_todos():
    """Completion summary can also carry the still-on-screen todo list."""
    pane = _pane(
        "✻ Worked for 12s",
        "  ⎿  ☒ done thing",
        "       ◻ open thing",
    )
    out = parse_pane(pane)
    assert isinstance(out, IdleDecoration)
    assert out.todos == ("  ⎿  ☒ done thing", "       ◻ open thing")


def test_chrome_present_but_nothing_above():
    pane = "\n".join([_INPUT])
    assert parse_pane(pane) is None


# ---------- Spinner text passthrough ----------


def test_spinner_text_kept_verbatim():
    """Whatever the spinner row says, we keep the full body text."""
    pane = _pane("✻ Beaming… (2m 34s · ↓ 9.2k tokens · thought for 8s)")
    out = parse_pane(pane)
    assert isinstance(out, Spinner)
    assert out.text == "Beaming… (2m 34s · ↓ 9.2k tokens · thought for 8s)"


def test_idle_decoration_text_kept_verbatim():
    pane = _pane("✻ Churned for 12s")
    out = parse_pane(pane)
    assert isinstance(out, IdleDecoration)
    assert out.text == "Churned for 12s"
