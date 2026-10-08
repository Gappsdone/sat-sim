import math
from datetime import UTC, datetime

import pytest

from sat_sim.iss_scenario import ISSScenario
from sat_sim.orbital import ECIVelocity
from sat_sim.scenario import (
    ISS_TLE_URL,
    TLE,
    Scenario,
    TleFetcher,
    create_iss_orbital,
    fetch_iss_tle,
)

ISS_TLE = """ISS (ZARYA)
1 25544U 98067A   21001.59097222  .00001264  00000-0  29602-4 0  9996
2 25544  51.6455  18.3234 0002187  86.1767 273.9526 15.48915313263513
"""


def make_fetcher(calls: list[tuple[str, float]]) -> TleFetcher:
    def fetch(url: str, timeout: float) -> str:
        calls.append((url, timeout))
        return ISS_TLE

    return fetch


def test_scenario_is_abstract() -> None:
    with pytest.raises(TypeError):
        Scenario()  # type: ignore[abstract]


def test_fetch_iss_tle_parses_celestrak_response() -> None:
    calls: list[tuple[str, float]] = []

    tle = fetch_iss_tle(timeout=4.0, fetcher=make_fetcher(calls))

    assert tle == TLE(
        name="ISS (ZARYA)",
        line1="1 25544U 98067A   21001.59097222  .00001264  00000-0  29602-4 0  9996",
        line2="2 25544  51.6455  18.3234 0002187  86.1767 273.9526 15.48915313263513",
    )
    assert calls == [(ISS_TLE_URL, 4.0)]


def test_fetch_iss_tle_rejects_invalid_response() -> None:
    def fetch(_url: str, _timeout: float) -> str:
        return "ISS (ZARYA)\nnot a TLE\n"

    with pytest.raises(ValueError, match="valid two-line element"):
        fetch_iss_tle(fetcher=fetch)


def test_fetch_iss_tle_requires_valid_tle_line_format() -> None:
    line2 = "2 25544  51.6455  18.3234 0002187  86.1767 273.9526 15.48915313263513"

    def fetch(_url: str, _timeout: float) -> str:
        return f"1 bogus line\n{line2}\n"

    with pytest.raises(ValueError, match="valid two-line element"):
        fetch_iss_tle(fetcher=fetch)


def test_fetch_iss_tle_defaults_name_when_pair_leads_response() -> None:
    text = (
        "1 25544U 98067A   21001.59097222  .00001264  00000-0  29602-4 0  9996\n"
        "2 25544  51.6455  18.3234 0002187  86.1767 273.9526 15.48915313263513\n"
    )

    tle = fetch_iss_tle(fetcher=lambda _url, _timeout: text)

    assert tle.name == "ISS"


def test_fetch_iss_tle_retries_transient_network_errors() -> None:
    calls: list[tuple[str, float]] = []
    delays: list[float] = []

    def flaky_fetch(url: str, timeout: float) -> str:
        calls.append((url, timeout))
        if len(calls) == 1:
            raise OSError("connection reset")
        return ISS_TLE

    tle = fetch_iss_tle(fetcher=flaky_fetch, sleeper=delays.append)

    assert tle.name == "ISS (ZARYA)"
    assert len(calls) == 2
    assert delays == [1.0]


def test_fetch_iss_tle_raises_after_exhausting_retries() -> None:
    calls: list[tuple[str, float]] = []
    delays: list[float] = []

    def failing_fetch(url: str, timeout: float) -> str:
        calls.append((url, timeout))
        raise OSError("connection refused")

    with pytest.raises(OSError, match="connection refused"):
        fetch_iss_tle(fetcher=failing_fetch, sleeper=delays.append)

    assert len(calls) == 3
    assert delays == [1.0, 1.0]


def test_create_iss_orbital_uses_fetched_tle() -> None:
    calls: list[tuple[str, float]] = []

    orbital = create_iss_orbital(fetcher=make_fetcher(calls))

    position, velocity = orbital.get_position(datetime(2021, 1, 1, tzinfo=UTC))
    assert len(position) == 3
    assert len(velocity) == 3
    assert calls == [(ISS_TLE_URL, 10.0)]


def test_iss_scenario_setup_creates_entity_and_step_updates_state() -> None:
    timestamp = datetime(2021, 1, 1, tzinfo=UTC)
    scenario = ISSScenario(fetcher=make_fetcher([]))

    scenario.setup(timestamp)
    position = scenario.step(timestamp)

    assert scenario.entity is not None
    assert scenario.orbital is not None
    assert all(
        math.isfinite(coordinate) for coordinate in (position.x, position.y, position.z)
    )
    velocity = scenario.world.get(scenario.entity, ECIVelocity)
    assert all(
        math.isfinite(coordinate) for coordinate in (velocity.x, velocity.y, velocity.z)
    )


def test_iss_scenario_requires_setup_before_step() -> None:
    scenario = ISSScenario(fetcher=make_fetcher([]))

    with pytest.raises(RuntimeError, match="set up"):
        scenario.step(datetime(2021, 1, 1, tzinfo=UTC))
