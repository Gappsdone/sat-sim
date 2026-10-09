from datetime import UTC, datetime, timedelta

import pytest

from sat_sim.position import ECIVelocity
from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim.services.tcs import (
    HeaterCommand,
    IlluminationState,
    TemperatureSensor,
    solar_direction_eci,
)


class FakeOrbital:
    def get_position(
        self, utc_time: datetime, normalize: bool = False
    ) -> tuple[list[float], list[float]]:
        del normalize
        sun_direction = solar_direction_eci(utc_time)
        return [6_700.0 * component for component in sun_direction], [0.0, 7.5, 0.0]


def test_setup_initializes_orbit_and_temperature_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sat_sim.scenarios.iss_scenario.create_iss_orbital",
        lambda **_kwargs: FakeOrbital(),
    )
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    scenario = ISSScenario(thermal_threshold_celsius=24.0)

    scenario.setup(timestamp)

    assert scenario.entity is not None
    assert scenario.orbital is not None
    assert scenario.world.has(scenario.entity, IlluminationState)
    assert len(list(scenario.world.query(TemperatureSensor, HeaterCommand))) == 9
    assert len(scenario.tcs.sensors) == len(scenario.tcs.heaters) == 9
    assert scenario.tcs.heater_threshold_celsius == 24.0
    assert scenario._last_thermal_timestamp == timestamp


def test_step_returns_and_prints_orbital_and_thermal_telemetry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sat_sim.scenarios.iss_scenario.create_iss_orbital",
        lambda **_kwargs: FakeOrbital(),
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    scenario = ISSScenario(thermal_threshold_celsius=25.0)
    scenario.setup(start)

    state = scenario.step(start + timedelta(seconds=1))

    assert state.timestamp == start + timedelta(seconds=1)
    expected_position = tuple(
        6_700_000.0 * component for component in solar_direction_eci(state.timestamp)
    )
    assert all(
        actual == pytest.approx(expected)
        for actual, expected in zip(
            (state.position.x, state.position.y, state.position.z),
            expected_position,
            strict=True,
        )
    )
    assert state.velocity == ECIVelocity(0.0, 7_500.0, 0.0)
    assert len(state.temperatures_celsius) == len(state.heater_outputs) == 9
    assert all(temperature > 20.0 for temperature in state.temperatures_celsius)
    output = capsys.readouterr().out
    assert "Position:" in output
    assert "Velocity:" in output
    assert "Thermal control (sunlit):" in output
    assert "Channel 0:" in output
    assert scenario.world is scenario.tcs.world
    assert scenario.tcs.satellite_position_m == (
        state.position.x,
        state.position.y,
        state.position.z,
    )
    assert state.is_sunlit is True
    assert state.is_sunlit is True
    assert "sunlit" in output
    assert "threshold 25.0 °C" in output
    saved_position = (state.position.x, state.position.y, state.position.z)
    saved_velocity = (state.velocity.x, state.velocity.y, state.velocity.z)
    next_state = scenario.step(start + timedelta(seconds=2))
    assert (state.position.x, state.position.y, state.position.z) == saved_position
    assert (state.velocity.x, state.velocity.y, state.velocity.z) == saved_velocity
    assert next_state.position is not state.position


def test_step_rejects_backwards_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sat_sim.scenarios.iss_scenario.create_iss_orbital",
        lambda **_kwargs: FakeOrbital(),
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    scenario = ISSScenario()
    scenario.setup(start)

    with pytest.raises(ValueError, match="must not precede"):
        scenario.step(start - timedelta(seconds=1))


def test_step_requires_setup() -> None:
    scenario = ISSScenario()

    with pytest.raises(RuntimeError, match="set up"):
        scenario.step(datetime(2026, 1, 1, tzinfo=UTC))
