"""Runnable live ISS telemetry server for browser frontends."""

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import monotonic

from fastapi import FastAPI

from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim_telemetry.api import create_app
from sat_sim_telemetry.publisher import ISSTelemetryPublisher
from sat_sim_telemetry.pus_udp import PUSUDPChannel, PUSUDPConfiguration
from sat_sim_telemetry.snapshot import describe_iss_scenario
from sat_sim_telemetry.store import TelemetryStore

logger = logging.getLogger(__name__)


def create_live_app(
    *,
    scenario: ISSScenario | None = None,
    interval: float = 1.0,
    pus_channel: PUSUDPChannel | None = None,
) -> FastAPI:
    """Create an API that owns and advances a live ISS scenario."""
    if interval <= 0:
        raise ValueError("interval must be greater than zero")

    scenario = scenario or ISSScenario()
    scenario.print_steps = False
    store = TelemetryStore()
    channel = pus_channel or PUSUDPChannel(PUSUDPConfiguration.from_environment())
    publisher = ISSTelemetryPublisher(scenario, store, channel)
    last_step = 0.0
    failed = False

    def step(timestamp: datetime) -> None:
        nonlocal last_step
        publisher.step(timestamp)
        last_step = monotonic()

    def task_finished(task: asyncio.Task[None]) -> None:
        nonlocal failed
        if task.cancelled():
            return
        failed = True
        error = task.exception()
        if error is None:
            logger.error("telemetry task %s exited unexpectedly", task.get_name())
        else:
            logger.error(
                "telemetry task %s failed",
                task.get_name(),
                exc_info=(type(error), error, error.__traceback__),
            )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        channel.open()
        logger.info("telemetry starting interval=%s", interval)
        tasks: tuple[asyncio.Task[None], ...] = ()

        async def publish_forever() -> None:
            while True:
                await asyncio.sleep(interval)
                step(datetime.now(UTC))

        async def consume_forever() -> None:
            while True:
                try:
                    packet, _address = await channel.consume()
                except ValueError:
                    continue
                publisher.consume(packet)

        try:
            timestamp = datetime.now(UTC)
            publisher.setup(timestamp)
            step(timestamp)
            tasks = (
                asyncio.create_task(publish_forever(), name="publisher"),
                asyncio.create_task(consume_forever(), name="consumer"),
            )
            for task in tasks:
                task.add_done_callback(task_finished)
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            channel.close()
            logger.info("telemetry stopped")

    return create_app(
        store,
        lambda: describe_iss_scenario(scenario),
        allowed_origins=("http://localhost:5173", "http://127.0.0.1:5173"),
        lifespan=lifespan,
        health_check=lambda: (
            not failed and monotonic() - last_step <= max(5.0, 3 * interval)
        ),
    )


def main(arguments: Sequence[str] | None = None) -> None:
    """Compatibility entry point; use ``sat-sim`` for new invocations."""
    from sat_sim.app import main as simulation_main

    simulation_main(arguments)


if __name__ == "__main__":
    main()
