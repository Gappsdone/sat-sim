"""In-memory latest-state store and bounded fan-out broadcaster."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sat_sim_telemetry.models import TelemetryFrame


class TelemetryStore:
    """Retain the latest frame and fan new frames out to subscribers."""

    def __init__(self, subscriber_queue_size: int = 2) -> None:
        if subscriber_queue_size <= 0:
            raise ValueError("subscriber_queue_size must be greater than zero")
        self._subscriber_queue_size = subscriber_queue_size
        self._current: TelemetryFrame | None = None
        self._subscribers: set[asyncio.Queue[TelemetryFrame]] = set()

    @property
    def current(self) -> TelemetryFrame | None:
        return self._current

    def publish(self, frame: TelemetryFrame) -> None:
        """Store and broadcast a frame without blocking the simulation."""
        if self._current is not None and frame.sequence <= self._current.sequence:
            raise ValueError("telemetry sequence must increase")
        self._current = frame
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(frame)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[TelemetryFrame]]:
        queue: asyncio.Queue[TelemetryFrame] = asyncio.Queue(
            maxsize=self._subscriber_queue_size
        )
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.remove(queue)
