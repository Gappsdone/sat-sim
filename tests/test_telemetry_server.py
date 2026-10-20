import asyncio
from datetime import datetime
from time import sleep
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from pus_library import SourcePacket
from sat_sim_telemetry import server
from sat_sim_telemetry.models import ScenarioDescription
from sat_sim_telemetry.store import TelemetryStore


class FakePublisher:
    instances: ClassVar[list["FakePublisher"]] = []

    def __init__(self, scenario: object, store: TelemetryStore, pus: object) -> None:
        self.scenario = scenario
        self.store = store
        self.pus = pus
        self.setup_timestamp: datetime | None = None
        self.steps = 0
        self.instances.append(self)

    def setup(self, timestamp: datetime) -> None:
        self.setup_timestamp = timestamp

    def step(self, timestamp: datetime) -> tuple[None, None]:
        del timestamp
        self.steps += 1
        return None, None

    def consume(self, packet: SourcePacket) -> None:
        del packet


class FakePUSChannel:
    def __init__(self) -> None:
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def publish(self, packet: SourcePacket) -> None:
        del packet

    async def consume(self) -> tuple[SourcePacket, tuple[str, int]]:
        await asyncio.Future()
        raise AssertionError("unreachable")

    def close(self) -> None:
        self.closed = True


def description() -> ScenarioDescription:
    return ScenarioDescription(
        scenario="ISS",
        entities=("iss",),
        entity_components={"iss": ()},
        entity_component_values={"iss": {}},
        battery_capacity_wh=1_000.0,
        solar_panel_peak_power_w=100.0,
        solar_panel_normal_body=(0.0, 0.0, -1.0),
        thermal_channels=(),
    )


def test_live_app_runs_publisher_during_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakePublisher.instances.clear()
    monkeypatch.setattr(server, "ISSTelemetryPublisher", FakePublisher)
    monkeypatch.setattr(
        server, "describe_iss_scenario", lambda _scenario: description()
    )

    channel = FakePUSChannel()
    app = server.create_live_app(interval=0.001, pus_channel=channel)  # type: ignore[arg-type]
    with TestClient(app) as client:
        response = client.get("/api/v1/scenario")
        sleep(0.01)

    assert response.status_code == 200
    publisher = FakePublisher.instances[0]
    assert publisher.setup_timestamp is not None
    assert publisher.steps >= 2
    assert channel.opened
    assert channel.closed


def test_live_app_rejects_nonpositive_interval() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        server.create_live_app(interval=0.0)


def test_server_main_passes_cli_configuration_to_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {}
    from sat_sim import app as simulation_app

    monkeypatch.setattr(
        simulation_app, "main", lambda arguments: called.update(arguments=arguments)
    )

    server.main(["--host", "0.0.0.0", "--port", "9000", "--interval", "0.5"])

    assert called == {
        "arguments": ["--host", "0.0.0.0", "--port", "9000", "--interval", "0.5"]
    }
