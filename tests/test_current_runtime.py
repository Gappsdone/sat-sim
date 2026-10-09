from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from sat_sim.position import (
    WGS84_ECCENTRICITY_SQUARED,
    WGS84_SEMI_MAJOR_AXIS,
    ECEFPosition,
)
from sat_sim.scenario import Scenario
from sat_sim.scenarios import iss_scenario
from sat_sim.simulation import Simulation
from sat_sim.tle import TLE, parse_tle

VALID_TLE = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   21001.59097222  .00001264  00000-0  29602-4 0  9996\n"
    "2 25544  51.6455  18.3234 0002187  86.1767 273.9526 15.48915313263513\n"
)


class FakeScenario(Scenario):
    def __init__(self) -> None:
        super().__init__()
        self.setup_calls: list[datetime] = []
        self.step_calls: list[datetime] = []

    def setup(self, timestamp: datetime) -> None:
        self.setup_calls.append(timestamp)

    def step(self, timestamp: datetime) -> str:
        self.step_calls.append(timestamp)
        return f"step-{len(self.step_calls)}"


def test_current_position_conversion_equator_and_pole() -> None:
    equator = ECEFPosition.from_lat_lon_alt(0.0, 0.0, 100.0)
    assert equator.x == pytest.approx(WGS84_SEMI_MAJOR_AXIS + 100.0)
    assert equator.y == pytest.approx(0.0)
    assert equator.z == pytest.approx(0.0)

    pole = ECEFPosition.from_lat_lon_alt(90.0, 0.0, 0.0)
    polar_radius = WGS84_SEMI_MAJOR_AXIS * (1 - WGS84_ECCENTRICITY_SQUARED) ** 0.5
    assert pole.x == pytest.approx(0.0, abs=1e-6)
    assert pole.y == pytest.approx(0.0, abs=1e-6)
    assert pole.z == pytest.approx(polar_radius)


def test_simulation_setup_interval_and_keyboard_interrupt() -> None:
    scenario = FakeScenario()
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    times = iter([origin, origin.replace(second=1), origin.replace(second=2)])
    clock_values = iter([0.0, 0.25, 1.25])
    delays: list[float] = []

    def sleeper(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 2:
            raise KeyboardInterrupt

    simulation = Simulation(
        scenario,
        clock=lambda: next(clock_values),
        sleeper=sleeper,
        timestamp_factory=lambda: next(times),
    )
    simulation.run()

    assert scenario.setup_calls == [origin]
    assert len(scenario.step_calls) == 2
    assert delays == [0.75, 0.75]
    with pytest.raises(RuntimeError, match="already set up"):
        simulation.setup(origin)
    with pytest.raises(ValueError, match="greater than zero"):
        Simulation(scenario, interval=0.0)


def test_tle_parser_handles_unnamed_data_and_rejects_bad_input() -> None:
    unnamed = "\n".join(VALID_TLE.splitlines()[1:])
    tle = parse_tle(unnamed)
    assert tle == TLE("ISS", VALID_TLE.splitlines()[1], VALID_TLE.splitlines()[2])
    with pytest.raises(ValueError, match="valid two-line element"):
        parse_tle("not TLE data")


def test_iss_tle_fetch_retries_transient_errors_and_returns_parsed_data() -> None:
    calls = 0
    delays: list[float] = []

    def fetch(_url: str, _timeout: float) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("temporary network failure")
        return VALID_TLE

    tle = iss_scenario.fetch_iss_tle(
        fetcher=fetch,
        sleeper=delays.append,
        retry_delay=0.25,
    )
    assert tle.name == "ISS (ZARYA)"
    assert calls == 2
    assert delays == [0.25]


def test_iss_tle_fetch_validates_retry_count_and_exhaustion() -> None:
    with pytest.raises(ValueError, match="retries"):
        iss_scenario.fetch_iss_tle(retries=-1)

    delays: list[float] = []
    with pytest.raises(OSError, match="offline"):
        iss_scenario.fetch_iss_tle(
            fetcher=lambda _url, _timeout: (_ for _ in ()).throw(OSError("offline")),
            sleeper=delays.append,
            retries=1,
        )
    assert delays == [1.0]

    with pytest.raises(ValueError, match="valid two-line element"):
        iss_scenario.fetch_iss_tle(fetcher=lambda _url, _timeout: "bad response")


def test_create_iss_orbital_uses_downloaded_tle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple[object, ...]] = []

    class Orbital:
        def __init__(self, *args: object, **kwargs: object) -> None:
            created.append((*args, kwargs))

    monkeypatch.setitem(
        __import__("sys").modules,
        "pyorbital.orbital",
        SimpleNamespace(Orbital=Orbital),
    )
    result = iss_scenario.create_iss_orbital(fetcher=lambda _url, _timeout: VALID_TLE)
    assert isinstance(result, Orbital)
    assert created == [
        (
            "ISS (ZARYA)",
            {"line1": VALID_TLE.splitlines()[1], "line2": VALID_TLE.splitlines()[2]},
        )
    ]
