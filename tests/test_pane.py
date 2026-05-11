"""Tests for pane.py: chrome detection + tmux IO."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ccmux_spinner.errors import PaneCaptureError, TmuxResolutionError
from ccmux_spinner.pane import (
    capture_pane,
    find_chrome_separator,
    has_input_chrome,
    resolve_pane_id,
)

_RULE = "─" * 60


def test_find_chrome_separator_detects_pure_dashes():
    lines = ["foo", _RULE, "bar"]
    assert find_chrome_separator(lines) == 1


def test_find_chrome_separator_none_when_absent():
    assert find_chrome_separator(["foo", "bar"]) is None


def test_find_chrome_separator_skips_indented_dashes():
    # Tool-result rendering uses indented dashes; not a real chrome.
    lines = ["foo", "  ⎿  ────────── still tool output", "bar"]
    assert find_chrome_separator(lines) is None


def test_find_chrome_separator_accepts_tmux_pane_border_status():
    # `─...─ <title> ─...─` from tmux pane-border-status: leading dash
    # run >= 20 and density >= 60% should still be treated as chrome.
    line = "─" * 25 + " ccmux:1 " + "─" * 25
    assert find_chrome_separator(["x", line]) == 1


def test_has_input_chrome_full_pattern():
    # Full pattern: rule + ❯ prompt + closing rule.
    lines = ["above", _RULE, "❯ ", _RULE]
    assert has_input_chrome(lines) is True


def test_has_input_chrome_missing_close():
    lines = ["above", _RULE, "❯ "]
    assert has_input_chrome(lines) is False


def test_has_input_chrome_no_prompt_marker():
    lines = ["above", _RULE, "no caret here", _RULE]
    assert has_input_chrome(lines) is False


# ---------- tmux IO ----------


def test_resolve_pane_id_success():
    class _R:
        returncode = 0
        stdout = "%80\n"
        stderr = ""

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()):
        assert resolve_pane_id("foo") == "%80"


def test_resolve_pane_id_session_missing():
    class _R:
        returncode = 1
        stdout = ""
        stderr = "no such session"

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()):
        with pytest.raises(TmuxResolutionError):
            resolve_pane_id("nope")


def test_resolve_pane_id_tmux_binary_missing():
    with patch("ccmux_spinner.pane.subprocess.run", side_effect=FileNotFoundError("x")):
        with pytest.raises(TmuxResolutionError):
            resolve_pane_id("foo")


def test_resolve_pane_id_empty_pane_raises():
    class _R:
        returncode = 0
        stdout = "\n"
        stderr = ""

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()):
        with pytest.raises(TmuxResolutionError):
            resolve_pane_id("foo")


def test_capture_pane_success():
    class _R:
        returncode = 0
        stdout = "hello world\n"
        stderr = ""

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()) as m:
        out = capture_pane("%80")
        assert out == "hello world\n"
        # Verify we used -p -J -t and the pane id.
        args = m.call_args[0][0]
        assert args[:3] == ["tmux", "capture-pane", "-p"]
        assert "-J" in args
        assert "%80" in args


def test_capture_pane_failure_raises():
    class _R:
        returncode = 1
        stdout = ""
        stderr = "pane gone"

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()):
        with pytest.raises(PaneCaptureError):
            capture_pane("%80")
