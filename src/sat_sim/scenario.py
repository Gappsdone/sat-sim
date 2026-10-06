"""Scenario abstractions and live orbital-data helpers."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.request import Request, urlopen

from sat_sim.ecs import Entity, World
from sat_sim.orbital import OrbitalLike

ISS_TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?NAME=ISS&FORMAT=tle"
DEFAULT_TIMEOUT = 10.0
TleFetcher = Callable[[str, float], str]


class Scenario(ABC):
    """An ECS-backed simulation scenario."""

    def __init__(self) -> None:
        self.world = World()

    @abstractmethod
    def setup(self, timestamp: datetime) -> None:
        """Create entities and initialize scenario-specific state."""

    @abstractmethod
    def step(self, timestamp: datetime) -> object:
        """Advance the scenario and return the value to report."""


@dataclass(frozen=True, slots=True)
class TLE:
    """A satellite name and its two-line element data."""

    name: str
    line1: str
    line2: str


def _download_text(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": "sat-sim/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_iss_tle(
    timeout: float = DEFAULT_TIMEOUT,
    fetcher: TleFetcher | None = None,
) -> TLE:
    """Fetch and validate the current ISS TLE from CelesTrak."""
    get_text = fetcher or _download_text
    lines = [
        line.strip()
        for line in get_text(ISS_TLE_URL, timeout).splitlines()
        if line.strip()
    ]

    for index, line1 in enumerate(lines[:-1]):
        line2 = lines[index + 1]
        if line1.startswith("1 ") and line2.startswith("2 "):
            name = lines[index - 1] if index else "ISS"
            return TLE(name=name, line1=line1, line2=line2)

    raise ValueError("ISS TLE response does not contain a valid two-line element set")


def create_iss_orbital(
    timeout: float = DEFAULT_TIMEOUT,
    fetcher: TleFetcher | None = None,
) -> OrbitalLike:
    """Fetch the current ISS TLE and create a pyorbital-compatible object."""
    from pyorbital.orbital import Orbital

    tle = fetch_iss_tle(timeout=timeout, fetcher=fetcher)
    return Orbital(tle.name, line1=tle.line1, line2=tle.line2)


def run_iss_scenario(
    timestamp: datetime | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    fetcher: TleFetcher | None = None,
) -> tuple[World, Entity]:
    """Create and initialize an ISS scenario for compatibility."""
    from sat_sim.iss_scenario import ISSScenario

    scenario = ISSScenario(timeout=timeout, fetcher=fetcher)
    scenario.setup(timestamp or datetime.now(UTC))
    return scenario.world, scenario.entity
