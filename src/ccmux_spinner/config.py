"""Environment-variable / settings.env resolution.

Mirrors :mod:`claude_tap.config` deliberately: same ``KEY=value``
format, same lookup order, same shell-exports-win semantics. The
parser is duplicated rather than imported so ccmux-spinner stays
zero-runtime-dependency.

Recognized settings:

* ``CCMUX_SPINNER_DIR`` — state directory
  (default ``~/.ccmux-spinner``). Reserved for future log files;
  v0.1 only loads ``settings.env`` from it.
* ``CCMUX_SPINNER_POLL_INTERVAL`` — pane poll cadence in seconds
  for :class:`SpinnerMonitor` (default 0.5).
* ``CCMUX_SPINNER_PRETTY_WIDTH`` — visual cell width used by
  ``ccmux-spinner watch`` for both the emit-time separator line
  and the body trim cap (default 100). One knob for both because
  the watch output reads as a unit and looks awkward when the
  two diverge.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_DIR = "~/.ccmux-spinner"
DEFAULT_POLL_INTERVAL = 0.5
DEFAULT_PRETTY_WIDTH = 100

_SETTINGS_ENV_FILENAME = "settings.env"
_LOADED_SETTINGS_FROM: list[Path] = []
_KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def ccmux_spinner_dir() -> Path:
    raw = os.environ.get("CCMUX_SPINNER_DIR", DEFAULT_DIR)
    return Path(raw).expanduser()


def settings_env_path() -> Path:
    return ccmux_spinner_dir() / _SETTINGS_ENV_FILENAME


def poll_interval() -> float:
    raw = os.environ.get("CCMUX_SPINNER_POLL_INTERVAL", "")
    if not raw:
        return DEFAULT_POLL_INTERVAL
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_POLL_INTERVAL
    return value if value > 0 else DEFAULT_POLL_INTERVAL


def pretty_width() -> int:
    """Visual cell width for both separator line and body trim cap."""
    raw = os.environ.get("CCMUX_SPINNER_PRETTY_WIDTH", "")
    if not raw:
        return DEFAULT_PRETTY_WIDTH
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PRETTY_WIDTH
    return value if value > 0 else DEFAULT_PRETTY_WIDTH


def loaded_settings_files() -> list[Path]:
    """Paths from which settings.env values were loaded at import time."""
    return list(_LOADED_SETTINGS_FROM)


def _parse_settings_env(path: Path) -> dict[str, str]:
    """Read a KEY=value file. Supports ``#`` comments and quoted values."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY_VALUE_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value and not (value.startswith('"') or value.startswith("'")):
            if "#" in value:
                value = value.split("#", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        out[key] = value
    return out


def _load_settings_env_files() -> None:
    paths = [Path(_SETTINGS_ENV_FILENAME), settings_env_path()]
    for path in paths:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        values = _parse_settings_env(path)
        if not values:
            continue
        for key, val in values.items():
            os.environ.setdefault(key, val)
        _LOADED_SETTINGS_FROM.append(path)


_load_settings_env_files()
