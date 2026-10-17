"""Runnable live ISS telemetry server for browser frontends."""

import argparse
import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI

from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim_telemetry.api import create_app
from sat_sim_telemetry.publisher import ISSTelemetryPublisher
from sat_sim_telemetry.snapshot import describe_iss_scenario
from sat_sim_telemetry.store import TelemetryStore


def create_live_app(*, interval: float = 1.0) -> FastAPI:
    """Create an API that owns and advances a live ISS scenario."""
    if interval <= 0:
        raise ValueError("interval must be greater than zero")

    scenario = ISSScenario()
    store = TelemetryStore()
    publisher = ISSTelemetryPublisher(scenario, store)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        timestamp = datetime.now(UTC)
        publisher.setup(timestamp)
        publisher.step(timestamp)

        async def publish_forever() -> None:
            while True:
                await asyncio.sleep(interval)
                publisher.step(datetime.now(UTC))

        task = asyncio.create_task(publish_forever())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return create_app(
        store,
        lambda: describe_iss_scenario(scenario),
        allowed_origins=("http://localhost:5173", "http://127.0.0.1:5173"),
        lifespan=lifespan,
    )


def main(arguments: Sequence[str] | None = None) -> None:
    """Run the live telemetry API with Uvicorn."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--interval", default=1.0, type=float)
    options = parser.parse_args(arguments)
    uvicorn.run(
        create_live_app(interval=options.interval),
        host=options.host,
        port=options.port,
    )


if __name__ == "__main__":
    main()
