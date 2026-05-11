"""SpinnerMonitor: async iterator over pane Activity snapshots."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from . import config
from .errors import PaneCaptureError
from .pane import capture_pane
from .parser import Activity, parse_pane

if TYPE_CHECKING:
    from types import TracebackType


class SpinnerMonitor:
    """Watch one tmux pane and yield :data:`Activity` changes.

    The monitor takes an explicit ``pane_id`` (e.g. ``%42``). Callers
    that have only a tmux session name can use
    :func:`ccmux_spinner.resolve_active_pane_id` to obtain the pane id
    first.

    Usage::

        async with SpinnerMonitor("%42") as mon:
            async for activity in mon:
                handle(activity)

    The iterator yields **on change** — repeated identical
    snapshots are coalesced — so a long-running spinner does not
    flood the consumer.

    Termination: when ``capture_pane`` raises :class:`PaneCaptureError`
    (pane killed, server crash) the iterator yields one final
    ``None`` and stops.
    """

    def __init__(
        self,
        pane_id: str,
        poll_interval: float | None = None,
    ) -> None:
        self._pane_id = pane_id
        self._poll_interval = (
            poll_interval if poll_interval is not None else config.poll_interval()
        )
        self._stop_event: asyncio.Event | None = None
        self._queue: asyncio.Queue[Activity] | None = None
        self._poll_task: asyncio.Task | None = None
        self._last: Activity = None
        self._first_yield_done = False
        # Raw-pane-text change tracking, exposed via the
        # ``last_pane_change_at`` property. Consumers downstream
        # (notably ccmux-core's grace timer) use this to distinguish
        # "spinner is absent because pane is streaming new content"
        # (pane changes ⇒ refresh) from "spinner is absent and pane
        # is static" (the only thing left to fire interrupted on).
        # The Activity-emit stream alone cannot disambiguate these
        # because Activity coalesces unchanged classifications.
        self._last_pane_text: str | None = None
        self._last_pane_change_at: float = 0.0

    async def __aenter__(self) -> SpinnerMonitor:
        self._stop_event = asyncio.Event()
        self._queue = asyncio.Queue()
        self._poll_task = asyncio.create_task(self._poll_loop())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._shutdown()

    async def __aiter__(self) -> AsyncIterator[Activity]:
        assert self._queue is not None
        while True:
            item = await self._queue.get()
            if item is _DONE:  # type: ignore[comparison-overlap]
                return
            yield item

    @property
    def current(self) -> Activity:
        """Latest classified :data:`Activity` from the poll loop.

        Reflects the most recent ``parse_pane`` result regardless of
        whether it was emitted to the iterator (coalescing skips
        repeated classifications). ``None`` until the first poll
        completes. Useful for one-shot queries that need the *current*
        state, not the next *change*.
        """
        return self._last

    @property
    def last_pane_change_at(self) -> float:
        """Unix epoch of the most recent poll where raw pane text
        differed from the previous poll.

        ``0.0`` until the first poll completes. After that, the value
        only advances when the raw captured text actually changes,
        which is a finer-grained signal than Activity-change emission
        (Activity coalesces; raw text comparison does not).

        Consumers can use ``time.time() - last_pane_change_at`` to
        decide whether the pane has been static for a while.
        """
        return self._last_pane_change_at

    async def _poll_loop(self) -> None:
        assert self._stop_event is not None
        assert self._queue is not None
        try:
            # First tick: emit the cold-start snapshot immediately
            # so the consumer doesn't wait poll_interval to see
            # whatever was on screen at subscribe time.
            try:
                pane_text = capture_pane(self._pane_id)
            except PaneCaptureError:
                await self._queue.put(None)
                await self._queue.put(_DONE)  # type: ignore[arg-type]
                return
            self._last_pane_text = pane_text
            self._last_pane_change_at = time.time()
            current = parse_pane(pane_text)
            self._last = current
            await self._queue.put(current)

            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._poll_interval,
                    )
                    return  # stop_event set
                except TimeoutError:
                    pass
                try:
                    pane_text = capture_pane(self._pane_id)
                except PaneCaptureError:
                    await self._queue.put(None)
                    await self._queue.put(_DONE)  # type: ignore[arg-type]
                    return
                if pane_text != self._last_pane_text:
                    self._last_pane_text = pane_text
                    self._last_pane_change_at = time.time()
                current = parse_pane(pane_text)
                if current != self._last:
                    self._last = current
                    await self._queue.put(current)
        except asyncio.CancelledError:
            raise
        finally:
            # Make sure the iterator unblocks when the loop exits
            # for any reason.
            try:
                await self._queue.put(_DONE)  # type: ignore[arg-type]
            except Exception:
                pass

    async def _shutdown(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._poll_task is not None and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except (asyncio.CancelledError, Exception):
                pass


# Sentinel for "iterator done". Defined here (not as a class) so it
# is identifiable by ``is`` and survives mypy.
_DONE: Any = object()
