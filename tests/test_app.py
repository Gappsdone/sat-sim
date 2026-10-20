from types import SimpleNamespace
from typing import Any

import pytest
import uvicorn

from sat_sim import app
from sat_sim.factory import simulation_factory
from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim.simulation import Simulation


def test_main_starts_iss_simulation_with_cli_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: dict[str, Any] = {}
    simulation = SimpleNamespace(run=lambda: calls.update(ran=True))

    def create_simulation(name: str, *, interval: float, timeout: float) -> object:
        calls.update(name=name, interval=interval, timeout=timeout)
        return simulation

    monkeypatch.setattr(simulation_factory, "create", create_simulation)

    app.main(["--offline", "--interval", "0.25", "--tle-timeout", "3.5"])

    assert calls == {
        "timeout": 3.5,
        "name": "iss",
        "interval": 0.25,
        "ran": True,
    }
    assert capsys.readouterr().out == (
        "Starting the iss simulation. Press Ctrl+C to stop.\niss simulation stopped.\n"
    )


@pytest.mark.parametrize(
    ("argument", "value"),
    (("--interval", "0"), ("--tle-timeout", "-1")),
)
def test_main_rejects_nonpositive_values(argument: str, value: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        app.main([argument, value])

    assert exit_info.value.code == 2


def test_parser_help_describes_simulation_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        app.main(["--help"])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "Run a spacecraft simulation." in output
    assert "--scenario" in output
    assert "--interval" in output
    assert "--tle-timeout" in output


def test_parser_rejects_unknown_scenario() -> None:
    with pytest.raises(SystemExit) as exit_info:
        app.main(["--scenario", "unknown"])
    assert exit_info.value.code == 2


def test_main_serves_selected_simulation_online(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = ISSScenario()
    simulation = Simulation(scenario, interval=0.5)
    calls: dict[str, Any] = {}
    monkeypatch.setattr(
        simulation_factory, "create", lambda *_args, **_kwargs: simulation
    )
    monkeypatch.setattr(
        app,
        "create_live_app",
        lambda *, scenario, interval: (
            calls.update(scenario=scenario, interval=interval) or object()
        ),
    )
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda api, *, host, port: calls.update(api=api, host=host, port=port),
    )

    app.main(["--host", "0.0.0.0", "--port", "9000", "--interval", "0.5"])

    assert calls["scenario"] is scenario
    assert calls["interval"] == 0.5
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9000
