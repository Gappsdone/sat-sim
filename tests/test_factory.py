import pytest

from sat_sim.factory import SimulationFactory, simulation_factory
from sat_sim.scenarios.iss_scenario import ISSScenario


def test_default_factory_creates_iss_simulation() -> None:
    simulation = simulation_factory.create("iss", interval=0.5, timeout=3.0)
    assert isinstance(simulation.scenario, ISSScenario)
    assert simulation.interval == 0.5


def test_factory_registers_unique_names() -> None:
    factory = SimulationFactory()
    factory.register("test", ISSScenario)
    assert factory.names == ("test",)
    with pytest.raises(ValueError, match="already registered"):
        factory.register("test", ISSScenario)
    with pytest.raises(ValueError, match="must not be empty"):
        factory.register("", ISSScenario)
    with pytest.raises(ValueError, match="unknown scenario"):
        factory.create("missing")
