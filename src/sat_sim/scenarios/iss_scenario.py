"""ISS scenario and command-line entry point."""

from datetime import datetime
from time import sleep

from sat_sim.ecs import Entity
from sat_sim.orbital import (
    ECIPosition,
    ECIVelocity,
    OrbitalLike,
    create_satellite_from_orbital,
    propagate_orbital,
)
from sat_sim.tle import (
    DEFAULT_TIMEOUT, 
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY,
    TleFetcher, 
    Sleeper, 
    TLE, 
    download_text, 
    parse_tle
)
from sat_sim.scenario import Scenario
from sat_sim.simulation import Simulation

ISS_TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?NAME=ISS&FORMAT=tle"

def fetch_iss_tle(
    timeout: float = DEFAULT_TIMEOUT,
    fetcher: TleFetcher | None = None,
    *,
    retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    sleeper: Sleeper = sleep,
) -> TLE:
    """Fetch and validate the current ISS TLE from CelesTrak.

    Transient network errors are retried up to ``retries`` times, waiting
    ``retry_delay`` seconds between attempts.
    """
    if retries < 0:
        raise ValueError("retries must not be negative")
    get_text = fetcher or download_text

    last_error: OSError | None = None
    for attempt in range(retries + 1):
        try:
            text = get_text(ISS_TLE_URL, timeout)
        except OSError as error:
            last_error = error
            if attempt < retries:
                sleeper(retry_delay)
        else:
            return parse_tle(text)

    assert last_error is not None
    raise last_error


def create_iss_orbital(
    timeout: float = DEFAULT_TIMEOUT,
    fetcher: TleFetcher | None = None,
) -> OrbitalLike:
    """Fetch the current ISS TLE and create a pyorbital-compatible object."""
    from pyorbital.orbital import Orbital

    tle = fetch_iss_tle(timeout=timeout, fetcher=fetcher)
    orbital: OrbitalLike = Orbital(tle.name, line1=tle.line1, line2=tle.line2)
    return orbital


class ISSScenario(Scenario):
    """Propagate the ISS from a live CelesTrak TLE."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        fetcher: TleFetcher | None = None,
    ) -> None:
        super().__init__()
        self.timeout = timeout
        self.fetcher = fetcher
        self.orbital: OrbitalLike | None = None
        self.entity: Entity | None = None

    def setup(self, timestamp: datetime) -> None:
        """Fetch the ISS TLE and create its initial ECS entity."""
        if self.entity is not None:
            raise RuntimeError("ISS scenario is already set up")
        self.orbital = create_iss_orbital(
            timeout=self.timeout,
            fetcher=self.fetcher,
        )
        self.entity = create_satellite_from_orbital(
            self.world,
            self.orbital,
            timestamp,
        )

    def step(self, timestamp: datetime):
        """Propagate the ISS and update its ECI components."""
        if self.orbital is None or self.entity is None:
            raise RuntimeError("ISS scenario must be set up before stepping")

        position, velocity = propagate_orbital(self.orbital, timestamp)
        current_position = self.world.get(self.entity, ECIPosition)
        current_velocity = self.world.get(self.entity, ECIVelocity)
        current_position.x = position.x
        current_position.y = position.y
        current_position.z = position.z
        current_velocity.x = velocity.x
        current_velocity.y = velocity.y
        current_velocity.z = velocity.z

        self.print_state(timestamp)


    def print_state(self, timestamp: datetime) -> None:
        print(f"Simulationstep: {timestamp.isoformat(sep=" ")}")
        pos = self.world.get(self.entity, ECIPosition) # type: ignore
        print(f"\tPosition: {pos}")
        vel = self.world.get(self.entity, ECIVelocity) # type: ignore
        print(f"\tVelocity: {vel}")


def main() -> None:
    """Print the ISS ECI position once per second until interrupted."""
    simulation = Simulation(ISSScenario())
    print("Press Ctrl+C to stop the ISS scenario.")
    simulation.run()
    print("ISS scenario stopped.")


if __name__ == "__main__":
    main()
