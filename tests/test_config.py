"""Tests for config.py: env vars + settings.env."""

from __future__ import annotations

from pathlib import Path

from ccmux_spinner import config as config_module
from ccmux_spinner.config import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PRETTY_WIDTH,
    _parse_settings_env,
    ccmux_spinner_dir,
    poll_interval,
    pretty_width,
    settings_env_path,
)


def test_default_dir(monkeypatch):
    monkeypatch.delenv("CCMUX_SPINNER_DIR", raising=False)
    assert ccmux_spinner_dir() == Path.home() / ".ccmux-spinner"


def test_dir_override(isolated_spinner_dir):
    assert ccmux_spinner_dir() == isolated_spinner_dir


def test_settings_env_path(isolated_spinner_dir):
    assert settings_env_path() == isolated_spinner_dir / "settings.env"


def test_poll_interval_default(isolated_spinner_dir):
    assert poll_interval() == DEFAULT_POLL_INTERVAL


def test_poll_interval_override(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_POLL_INTERVAL", "0.25")
    assert poll_interval() == 0.25


def test_poll_interval_invalid_falls_back(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_POLL_INTERVAL", "abc")
    assert poll_interval() == DEFAULT_POLL_INTERVAL


def test_poll_interval_non_positive_falls_back(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_POLL_INTERVAL", "0")
    assert poll_interval() == DEFAULT_POLL_INTERVAL


def test_parse_settings_env_basic(tmp_path):
    f = tmp_path / "settings.env"
    f.write_text(
        "# comment\n"
        "FOO=bar\n"
        "BAZ = qux \n"
        '\nQUOTED="value with spaces"\n'
        "INLINE=value # trailing comment\n"
    )
    parsed = _parse_settings_env(f)
    assert parsed["FOO"] == "bar"
    assert parsed["BAZ"] == "qux"
    assert parsed["QUOTED"] == "value with spaces"
    assert parsed["INLINE"] == "value"


def test_settings_env_loaded_into_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_DIR", str(tmp_path))
    settings_file = tmp_path / "settings.env"
    settings_file.write_text("CCMUX_SPINNER_POLL_INTERVAL=1.5\n")
    monkeypatch.delenv("CCMUX_SPINNER_POLL_INTERVAL", raising=False)

    config_module._LOADED_SETTINGS_FROM.clear()
    config_module._load_settings_env_files()

    assert poll_interval() == 1.5


def test_shell_export_wins_over_settings_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_DIR", str(tmp_path))
    settings_file = tmp_path / "settings.env"
    settings_file.write_text("CCMUX_SPINNER_POLL_INTERVAL=1.5\n")
    monkeypatch.setenv("CCMUX_SPINNER_POLL_INTERVAL", "9.9")

    config_module._LOADED_SETTINGS_FROM.clear()
    config_module._load_settings_env_files()

    assert poll_interval() == 9.9


# ---------- pretty width ----------


def test_pretty_width_default(isolated_spinner_dir, monkeypatch):
    monkeypatch.delenv("CCMUX_SPINNER_PRETTY_WIDTH", raising=False)
    assert pretty_width() == DEFAULT_PRETTY_WIDTH


def test_pretty_width_override(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_PRETTY_WIDTH", "80")
    assert pretty_width() == 80


def test_pretty_width_invalid_falls_back(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_PRETTY_WIDTH", "abc")
    assert pretty_width() == DEFAULT_PRETTY_WIDTH


def test_pretty_width_non_positive_falls_back(isolated_spinner_dir, monkeypatch):
    monkeypatch.setenv("CCMUX_SPINNER_PRETTY_WIDTH", "0")
    assert pretty_width() == DEFAULT_PRETTY_WIDTH
