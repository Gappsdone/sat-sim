"""Named simulation registry and construction."""

from collections.abc import Callable

from sat_sim.scenario import Scenario
from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim.simulation import Simulation

ScenarioBuilder = Callable[..., Scenario]


class SimulationFactory:
    """Register scenarios by unique name and construct their simulations."""

    def __init__(self) -> None:
        self._scenarios: dict[str, ScenarioBuilder] = {}

    def register(self, name: str, builder: ScenarioBuilder) -> None:
        if not name:
            raise ValueError("scenario name must not be empty")
        if name in self._scenarios:
            raise ValueError(f"scenario {name!r} is already registered")
        self._scenarios[name] = builder

    @property
    def names(self) -> tuple[str, ...]:
        """Return the available scenario names."""
        return tuple(self._scenarios)

    def create(
        self, name: str, *, interval: float = 1.0, **options: float
    ) -> Simulation:
        """Create a simulation for a registered scenario."""
        try:
            builder = self._scenarios[name]
        except KeyError as error:
            raise ValueError(f"unknown scenario {name!r}") from error
        return Simulation(builder(**options), interval=interval)


simulation_factory = SimulationFactory()
simulation_factory.register("iss", ISSScenario)
