"""ISS scenario and command-line entry point."""

from datetime import datetime

from sat_sim.ecs import Entity
from sat_sim.orbital import (
    ECIPosition,
    ECIVelocity,
    OrbitalLike,
    create_satellite_from_orbital,
    propagate_orbital,
)
from sat_sim.scenario import (
    DEFAULT_TIMEOUT,
    Scenario,
    TleFetcher,
    create_iss_orbital,
)
from sat_sim.simulation import Simulation


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

    def step(self, timestamp: datetime) -> ECIPosition:
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
        return current_position


def print_iss_position(timestamp: datetime, position: object) -> None:
    """Print one timestamped ISS ECI position."""
    print(f"ISS ECI position at {timestamp.isoformat()}: {position}")


def main() -> None:
    """Print the ISS ECI position once per second until interrupted."""
    simulation = Simulation(ISSScenario(), printer=print_iss_position)
    print("Press Ctrl+C to stop the ISS scenario.")
    try:
        simulation.run()
    except KeyboardInterrupt:
        print("ISS scenario stopped.")


if __name__ == "__main__":
    main()
