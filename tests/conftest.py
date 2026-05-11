"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def isolated_spinner_dir(tmp_path, monkeypatch):
    """Override CCMUX_SPINNER_DIR to a fresh tmp dir for the test."""
    monkeypatch.setenv("CCMUX_SPINNER_DIR", str(tmp_path))
    for var in ("CCMUX_SPINNER_POLL_INTERVAL",):
        monkeypatch.delenv(var, raising=False)
    return tmp_path
