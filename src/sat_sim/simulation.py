"""Simulation components, systems, and scheduling orchestration."""

from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic, sleep

from sat_sim.scenario import Scenario

Clock = Callable[[], float]
Sleeper = Callable[[float], None]
TimestampFactory = Callable[[], datetime]


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
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be greater than zero")
        self.scenario = scenario
        self.interval = interval
        self._clock = clock
        self._sleeper = sleeper
        self._timestamp_factory = timestamp_factory or (lambda: datetime.now(UTC))
        self._is_setup = False

    def setup(self, timestamp: datetime | None = None) -> None:
        """Initialize the configured scenario exactly once."""
        if self._is_setup:
            raise RuntimeError("simulation is already set up")
        self.scenario.setup(timestamp or self._timestamp_factory())
        self._is_setup = True

    def run(self) -> None:
        """Run the scenario continuously until interrupted.

        Handles ``KeyboardInterrupt`` internally and returns when the
        simulation is stopped, for example by pressing ``Ctrl+C``.
        """
        if not self._is_setup:
            self.setup()

        deadline = self._clock()
        try:
            while True:
                timestamp = self._timestamp_factory()
                self.scenario.step(timestamp)

                deadline += self.interval
                self._sleeper(max(0.0, deadline - self._clock()))
        except KeyboardInterrupt:
            return
