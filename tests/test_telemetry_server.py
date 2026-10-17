from datetime import datetime
from time import sleep
from typing import Any, ClassVar

import pytest
import uvicorn
from fastapi.testclient import TestClient

from sat_sim_telemetry import server
from sat_sim_telemetry.models import ScenarioDescription
from sat_sim_telemetry.store import TelemetryStore


class FakePublisher:
    instances: ClassVar[list["FakePublisher"]] = []

    def __init__(self, scenario: object, store: TelemetryStore) -> None:
        self.scenario = scenario
        self.store = store
        self.setup_timestamp: datetime | None = None
        self.steps = 0
        self.instances.append(self)

    def setup(self, timestamp: datetime) -> None:
        self.setup_timestamp = timestamp

    def step(self, timestamp: datetime) -> tuple[None, None]:
        del timestamp
        self.steps += 1
        return None, None


def description() -> ScenarioDescription:
    return ScenarioDescription(
        scenario="ISS",
        entities=("iss",),
        battery_capacity_wh=1_000.0,
        solar_panel_peak_power_w=100.0,
        solar_panel_normal_body=(0.0, 0.0, -1.0),
        thermal_channels=(),
    )


def test_live_app_runs_publisher_during_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakePublisher.instances.clear()
    monkeypatch.setattr(server, "ISSScenario", object)
    monkeypatch.setattr(server, "ISSTelemetryPublisher", FakePublisher)
    monkeypatch.setattr(
        server, "describe_iss_scenario", lambda _scenario: description()
    )

    app = server.create_live_app(interval=0.001)
    with TestClient(app) as client:
        response = client.get("/api/v1/scenario")
        sleep(0.01)

    assert response.status_code == 200
    publisher = FakePublisher.instances[0]
    assert publisher.setup_timestamp is not None
    assert publisher.steps >= 2


def test_live_app_rejects_nonpositive_interval() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        server.create_live_app(interval=0.0)


def test_server_main_passes_cli_configuration_to_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    called: dict[str, Any] = {}
    monkeypatch.setattr(server, "create_live_app", lambda *, interval: sentinel)

    def fake_run(app: object, *, host: str, port: int) -> None:
        called.update(app=app, host=host, port=port)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    server.main(["--host", "0.0.0.0", "--port", "9000", "--interval", "0.5"])

    assert called == {"app": sentinel, "host": "0.0.0.0", "port": 9000}
