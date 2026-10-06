"""Simulation components, systems, and scheduling orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic, sleep

from sat_sim.ecs import World
from sat_sim.position import Position
from sat_sim.scenario import Scenario


@dataclass(slots=True)
class Velocity:
    """ECEF-frame Cartesian velocity in meters per second."""

    x: float
    y: float
    z: float


def create_satellite(
    world: World,
    position: Position,
    velocity: Velocity,
) -> int:
    """Create a satellite entity with position and velocity components."""
    entity = world.create()
    world.add(entity, position)
    world.add(entity, velocity)
    return entity


Clock = Callable[[], float]
Sleeper = Callable[[float], None]
TimestampFactory = Callable[[], datetime]
StatePrinter = Callable[[datetime, object], None]


def print_state(timestamp: datetime, state: object) -> None:
    """Print a timestamped simulation state."""
    print(f"Simulation state at {timestamp.isoformat()}: {state}")


class Simulation:
    """Run a scenario on a fixed-interval monotonic schedule."""

    def __init__(
        self,
        scenario: Scenario,
        interval: float = 1.0,
        *,
        clock: Clock = monotonic,
        sleeper: Sleeper = sleep,
        timestamp_factory: TimestampFactory | None = None,
        printer: StatePrinter = print_state,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be greater than zero")
        self.scenario = scenario
        self.interval = interval
        self._clock = clock
        self._sleeper = sleeper
        self._timestamp_factory = timestamp_factory or (lambda: datetime.now(UTC))
        self._printer = printer
        self._is_setup = False

    def setup(self, timestamp: datetime | None = None) -> None:
        """Initialize the configured scenario exactly once."""
        if self._is_setup:
            raise RuntimeError("simulation is already set up")
        self.scenario.setup(timestamp or self._timestamp_factory())
        self._is_setup = True

    def run(self) -> None:
        """Run the scenario continuously until interrupted."""
        if not self._is_setup:
            self.setup()

        deadline = self._clock()
        while True:
            timestamp = self._timestamp_factory()
            state = self.scenario.step(timestamp)
            self._printer(timestamp, state)

            deadline += self.interval
            self._sleeper(max(0.0, deadline - self._clock()))
