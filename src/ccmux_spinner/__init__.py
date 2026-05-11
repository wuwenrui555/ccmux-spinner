"""ccmux-spinner: tmux pane spinner / idle-decoration watcher for Claude Code."""

from ._version import __version__
from .errors import PaneCaptureError, TmuxResolutionError
from .monitor import SpinnerMonitor
from .pane import resolve_active_pane_id
from .parser import Activity, IdleDecoration, Spinner, parse_pane

__all__ = [
    "__version__",
    "Activity",
    "IdleDecoration",
    "PaneCaptureError",
    "Spinner",
    "SpinnerMonitor",
    "TmuxResolutionError",
    "parse_pane",
    "resolve_active_pane_id",
]
