"""Exception types raised by ccmux-spinner."""

from __future__ import annotations


class TmuxResolutionError(RuntimeError):
    """Raised when looking up a tmux session / window 0 / pane id fails."""


class PaneCaptureError(RuntimeError):
    """Raised when capturing a tmux pane fails (pane gone, server crashed, etc.)."""
