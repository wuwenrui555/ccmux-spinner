"""Tests for pane.py: chrome detection + tmux IO."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ccmux_spinner.errors import PaneCaptureError, TmuxResolutionError
from ccmux_spinner.pane import (
    capture_pane,
    find_chrome_separator,
    has_input_chrome,
    resolve_active_pane_id,
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


def test_resolve_active_pane_id_uses_active_pane():
    """First call (no window suffix) returns the active pane id."""

    class _R:
        returncode = 0
        stdout = "%80\n"
        stderr = ""

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()) as mock_run:
        assert resolve_active_pane_id("foo") == "%80"

    args = mock_run.call_args.args[0]
    # First positional arg should be the tmux command list; the -t arg
    # should be the session name with no ":0" suffix.
    assert args[:4] == ["tmux", "display-message", "-t", "foo"]
    assert args[4:6] == ["-p", "#{pane_id}"]


def test_resolve_active_pane_id_falls_back_to_window_zero():
    """When the unsuffixed lookup yields empty, fall back to :0."""

    class _Active:
        returncode = 0
        stdout = "\n"  # empty → triggers fallback
        stderr = ""

    class _Fallback:
        returncode = 0
        stdout = "%99\n"
        stderr = ""

    with patch(
        "ccmux_spinner.pane.subprocess.run",
        side_effect=[_Active(), _Fallback()],
    ) as mock_run:
        assert resolve_active_pane_id("foo") == "%99"

    # Two calls: first without :0, second with :0.
    assert mock_run.call_count == 2
    second_args = mock_run.call_args_list[1].args[0]
    assert second_args[:4] == ["tmux", "display-message", "-t", "foo:0"]


def test_resolve_active_pane_id_fallback_on_nonzero_rc():
    """A non-zero exit on the active lookup also triggers the :0 fallback."""

    class _Active:
        returncode = 1
        stdout = ""
        stderr = "no active pane"

    class _Fallback:
        returncode = 0
        stdout = "%7\n"
        stderr = ""

    with patch(
        "ccmux_spinner.pane.subprocess.run",
        side_effect=[_Active(), _Fallback()],
    ):
        assert resolve_active_pane_id("foo") == "%7"


def test_resolve_active_pane_id_both_lookups_fail():
    class _Active:
        returncode = 1
        stdout = ""
        stderr = "no such session"

    class _Fallback:
        returncode = 1
        stdout = ""
        stderr = "no such session"

    with patch(
        "ccmux_spinner.pane.subprocess.run",
        side_effect=[_Active(), _Fallback()],
    ):
        with pytest.raises(TmuxResolutionError):
            resolve_active_pane_id("nope")


def test_resolve_active_pane_id_tmux_binary_missing():
    with patch("ccmux_spinner.pane.subprocess.run", side_effect=FileNotFoundError("x")):
        with pytest.raises(TmuxResolutionError):
            resolve_active_pane_id("foo")


def test_resolve_active_pane_id_both_empty_pane_strings():
    """Both subprocess calls return whitespace-only stdout → raise."""

    class _R:
        returncode = 0
        stdout = "  \n"
        stderr = ""

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()):
        with pytest.raises(TmuxResolutionError):
            resolve_active_pane_id("foo")


def test_capture_pane_success():
    class _R:
        returncode = 0
        stdout = "hello world\n"
        stderr = ""

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()) as m:
        out = capture_pane("%80")
        assert out == "hello world\n"
        args = m.call_args[0][0]
        assert args == [
            "tmux",
            "capture-pane",
            "-p",
            "-J",
            "-t",
            "%80",
            "-S",
            "-200",
            "-E",
            "-",
        ]


def test_capture_pane_failure_raises():
    class _R:
        returncode = 1
        stdout = ""
        stderr = "pane gone"

    with patch("ccmux_spinner.pane.subprocess.run", return_value=_R()):
        with pytest.raises(PaneCaptureError):
            capture_pane("%80")
