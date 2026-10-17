"""Bridge synchronous ISS scenario steps into telemetry frames."""

from datetime import datetime

from sat_sim.scenarios.iss_scenario import ISSScenario, ISSScenarioState
from sat_sim_telemetry.models import TelemetryFrame
from sat_sim_telemetry.snapshot import snapshot_iss
from sat_sim_telemetry.store import TelemetryStore


class ISSTelemetryPublisher:
    """Step an ISS scenario and publish one immutable frame per step."""

    def __init__(self, scenario: ISSScenario, store: TelemetryStore) -> None:
        self.scenario = scenario
        self.store = store
        self._sequence = 0 if store.current is None else store.current.sequence + 1

    def setup(self, timestamp: datetime) -> None:
        self.scenario.setup(timestamp)

    def step(self, timestamp: datetime) -> tuple[ISSScenarioState, TelemetryFrame]:
        state = self.scenario.step(timestamp)
        frame = snapshot_iss(self.scenario, state, self._sequence)
        self.store.publish(frame)
        self._sequence += 1
        return state, frame
