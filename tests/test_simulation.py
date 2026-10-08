from datetime import UTC, datetime

import pytest

from sat_sim.ecs import World
from sat_sim.position import ECEFPosition
from sat_sim.scenario import Scenario
from sat_sim.simulation import Simulation, Velocity, create_satellite


def test_create_satellite_adds_ecef_position_and_velocity() -> None:
    world = World()

    entity = create_satellite(world, ECEFPosition(10, 20, 30), Velocity(2, -1, 0.5))

    assert world.get(entity, ECEFPosition) == ECEFPosition(10, 20, 30)
    assert world.get(entity, Velocity) == Velocity(2, -1, 0.5)


class FakeScenario(Scenario):
    def __init__(self) -> None:
        super().__init__()
        self.setup_timestamps: list[datetime] = []
        self.step_timestamps: list[datetime] = []

    def setup(self, timestamp: datetime) -> None:
        self.setup_timestamps.append(timestamp)

    def step(self, timestamp: datetime) -> str:
        self.step_timestamps.append(timestamp)
        return f"state-{len(self.step_timestamps)}"


def test_simulation_sets_up_scenario_and_schedules_steps() -> None:
    scenario = FakeScenario()
    setup_timestamp = datetime(2021, 1, 1, tzinfo=UTC)
    step_timestamps = iter(
        [
            datetime(2021, 1, 1, 0, 0, 1, tzinfo=UTC),
            datetime(2021, 1, 1, 0, 0, 2, tzinfo=UTC),
        ]
    )
    clock_values = iter([0.0, 0.2, 1.2])
    delays: list[float] = []
    printed: list[tuple[datetime, object]] = []

    def sleeper(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 2:
            raise KeyboardInterrupt

    simulation = Simulation(
        scenario,
        clock=lambda: next(clock_values),
        sleeper=sleeper,
        timestamp_factory=lambda: next(step_timestamps),
        printer=lambda timestamp, state: printed.append((timestamp, state)),
    )
    simulation.setup(setup_timestamp)
    # The fake sleeper raises KeyboardInterrupt on the second delay,
    # which run() handles internally to stop the simulation.
    simulation.run()

    assert scenario.setup_timestamps == [setup_timestamp]
    assert scenario.step_timestamps == [
        datetime(2021, 1, 1, 0, 0, 1, tzinfo=UTC),
        datetime(2021, 1, 1, 0, 0, 2, tzinfo=UTC),
    ]
    assert delays == [0.8, 0.8]
    assert printed == [
        (scenario.step_timestamps[0], "state-1"),
        (scenario.step_timestamps[1], "state-2"),
    ]


def test_simulation_run_sets_up_scenario_when_needed() -> None:
    scenario = FakeScenario()
    timestamps = iter([datetime(2021, 1, 1, tzinfo=UTC)] * 2)

    def stop(_delay: float) -> None:
        raise KeyboardInterrupt

    simulation = Simulation(
        scenario,
        clock=lambda: 0.0,
        sleeper=stop,
        timestamp_factory=lambda: next(timestamps),
        printer=lambda _timestamp, _state: None,
    )
    simulation.run()

    assert len(scenario.setup_timestamps) == 1
    assert len(scenario.step_timestamps) == 1


def test_simulation_rejects_duplicate_setup_and_invalid_interval() -> None:
    scenario = FakeScenario()
    simulation = Simulation(scenario)
    simulation.setup(datetime(2021, 1, 1, tzinfo=UTC))

    with pytest.raises(RuntimeError, match="already set up"):
        simulation.setup(datetime(2021, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="greater than zero"):
        Simulation(scenario, interval=0)
