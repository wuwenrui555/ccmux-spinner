"""Tests for SpinnerMonitor: poll loop + change coalescing + termination."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from ccmux_spinner.errors import PaneCaptureError
from ccmux_spinner.monitor import SpinnerMonitor
from ccmux_spinner.parser import IdleDecoration, Spinner

_RULE = "─" * 60
_INPUT = "\n".join([_RULE, "❯ ", _RULE])


def _pane(*lines_above_chrome: str) -> str:
    return "\n".join([*lines_above_chrome, _INPUT])


@pytest.mark.asyncio
async def test_monitor_yields_initial_snapshot():
    panes = iter([_pane("✻ Thinking… (3s)"), _pane("✻ Thinking… (3s)")])

    with (
        patch("ccmux_spinner.monitor.capture_pane", side_effect=lambda _: next(panes)),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.05) as mon:
            received = []

            async def consumer():
                async for a in mon:
                    received.append(a)
                    if received:
                        break

            await asyncio.wait_for(consumer(), timeout=1.0)
            assert isinstance(received[0], Spinner)


@pytest.mark.asyncio
async def test_monitor_coalesces_repeated_snapshots():
    """Yields on change only — repeated identical pane text → 1 yield."""
    same = _pane("✻ Thinking… (3s)")
    with (
        patch("ccmux_spinner.monitor.capture_pane", return_value=same),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            received = []

            async def consumer():
                async for a in mon:
                    received.append(a)

            task = asyncio.create_task(consumer())
            await asyncio.sleep(0.2)  # enough for several poll ticks
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert len(received) == 1


@pytest.mark.asyncio
async def test_monitor_emits_change():
    panes = [
        _pane("✻ Thinking… (3s)"),
        _pane("✻ Thinking… (4s)"),
    ]
    idx = {"i": 0}

    def fake_capture(_pane_id: str) -> str:
        i = idx["i"]
        idx["i"] = min(i + 1, len(panes) - 1)
        return panes[i]

    with (
        patch("ccmux_spinner.monitor.capture_pane", side_effect=fake_capture),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            received = []

            async def consumer():
                async for a in mon:
                    received.append(a)
                    if len(received) >= 2:
                        break

            await asyncio.wait_for(consumer(), timeout=1.0)
            texts = [a.text for a in received if isinstance(a, Spinner)]
            assert texts == ["Thinking… (3s)", "Thinking… (4s)"]


@pytest.mark.asyncio
async def test_monitor_terminates_on_pane_capture_error():
    calls = {"n": 0}

    def fake_capture(_pane_id: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return _pane("✻ Thinking… (3s)")
        raise PaneCaptureError("pane gone")

    with (
        patch("ccmux_spinner.monitor.capture_pane", side_effect=fake_capture),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            received = []

            async def consumer():
                async for a in mon:
                    received.append(a)

            await asyncio.wait_for(consumer(), timeout=1.0)
            assert isinstance(received[0], Spinner)
            assert received[-1] is None  # terminal None on pane loss


@pytest.mark.asyncio
async def test_monitor_initial_pane_capture_error_terminates_immediately():
    with (
        patch(
            "ccmux_spinner.monitor.capture_pane",
            side_effect=PaneCaptureError("immediate"),
        ),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            received = []

            async def consumer():
                async for a in mon:
                    received.append(a)

            await asyncio.wait_for(consumer(), timeout=1.0)
            assert received == [None]


@pytest.mark.asyncio
async def test_monitor_idle_decoration_then_spinner():
    # User just finished a turn (idle decoration), then types and Claude
    # starts working again (spinner).
    panes = [
        _pane("✻ Churned for 12s"),
        _pane("✻ Thinking… (1s)"),
    ]
    idx = {"i": 0}

    def fake_capture(_pane_id: str) -> str:
        i = idx["i"]
        idx["i"] = min(i + 1, len(panes) - 1)
        return panes[i]

    with (
        patch("ccmux_spinner.monitor.capture_pane", side_effect=fake_capture),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            received = []

            async def consumer():
                async for a in mon:
                    received.append(a)
                    if len(received) >= 2:
                        break

            await asyncio.wait_for(consumer(), timeout=1.0)
            assert isinstance(received[0], IdleDecoration)
            assert isinstance(received[1], Spinner)


# ---------------------------------------------------------------------------
# `current` and `last_pane_change_at` properties (v0.2.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_current_reflects_latest_parse():
    """SpinnerMonitor.current returns the most recent classified Activity,
    even when coalescing means it was not emitted."""
    same = _pane("✻ Thinking… (3s)")
    with (
        patch("ccmux_spinner.monitor.capture_pane", return_value=same),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            await asyncio.sleep(0.1)  # let several polls happen
            assert isinstance(mon.current, Spinner)
            assert mon.current.text == "Thinking… (3s)"


@pytest.mark.asyncio
async def test_last_pane_change_at_updates_when_pane_changes():
    panes = [
        _pane("✻ Thinking… (3s)"),
        _pane("✻ Thinking… (4s)"),
        _pane("✻ Thinking… (5s)"),
    ]
    idx = {"i": 0}

    def fake_capture(_pane_id: str) -> str:
        i = idx["i"]
        idx["i"] = min(i + 1, len(panes) - 1)
        return panes[i]

    with (
        patch("ccmux_spinner.monitor.capture_pane", side_effect=fake_capture),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            await asyncio.sleep(0.01)
            t1 = mon.last_pane_change_at
            assert t1 > 0
            await asyncio.sleep(0.1)  # let more polls happen
            t2 = mon.last_pane_change_at
            assert t2 > t1, "last_pane_change_at should advance when pane changes"


@pytest.mark.asyncio
async def test_last_pane_change_at_stable_when_pane_unchanged():
    """Pane text identical poll after poll → last_pane_change_at frozen."""
    same = _pane("✻ Thinking… (constant)")
    with (
        patch("ccmux_spinner.monitor.capture_pane", return_value=same),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            await asyncio.sleep(0.01)
            t1 = mon.last_pane_change_at
            assert t1 > 0
            await asyncio.sleep(0.15)  # plenty of polls, but pane never changes
            t2 = mon.last_pane_change_at
            assert t2 == t1, (
                "last_pane_change_at must not advance while raw pane text is unchanged"
            )


@pytest.mark.asyncio
async def test_current_is_none_before_first_poll():
    """Before the poll loop has captured anything, current is None and
    last_pane_change_at is 0."""
    mon = SpinnerMonitor("%1", poll_interval=0.02)
    assert mon.current is None
    assert mon.last_pane_change_at == 0.0


@pytest.mark.asyncio
async def test_current_tracks_transition_to_idle_decoration():
    panes = [
        _pane("✻ Thinking… (3s)"),
        _pane("✻ Churned for 12s"),
    ]
    idx = {"i": 0}

    def fake_capture(_pane_id: str) -> str:
        i = idx["i"]
        idx["i"] = min(i + 1, len(panes) - 1)
        return panes[i]

    with (
        patch("ccmux_spinner.monitor.capture_pane", side_effect=fake_capture),
    ):
        async with SpinnerMonitor("%1", poll_interval=0.02) as mon:
            await asyncio.sleep(0.1)
            assert isinstance(mon.current, IdleDecoration)
