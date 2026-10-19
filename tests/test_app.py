from types import SimpleNamespace
from typing import Any

import pytest

from sat_sim import app


def test_main_starts_iss_simulation_with_cli_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = object()
    calls: dict[str, Any] = {}
    simulation = SimpleNamespace(run=lambda: calls.update(ran=True))

    def create_scenario(*, timeout: float) -> object:
        calls["timeout"] = timeout
        return scenario

    def create_simulation(configured_scenario: object, *, interval: float) -> object:
        calls.update(scenario=configured_scenario, interval=interval)
        return simulation

    monkeypatch.setattr(app, "ISSScenario", create_scenario)
    monkeypatch.setattr(app, "Simulation", create_simulation)

    app.main(["--interval", "0.25", "--tle-timeout", "3.5"])

    assert calls == {
        "timeout": 3.5,
        "scenario": scenario,
        "interval": 0.25,
        "ran": True,
    }
    assert capsys.readouterr().out == (
        "Starting the ISS simulation. Press Ctrl+C to stop.\nISS simulation stopped.\n"
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
    assert "Run the live ISS spacecraft simulation." in output
    assert "--interval" in output
    assert "--tle-timeout" in output
