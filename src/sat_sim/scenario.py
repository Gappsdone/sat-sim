"""Scenario abstractions"""

from abc import ABC, abstractmethod
from datetime import datetime

from sat_sim.ecs import World


class Scenario(ABC):
    """An ECS-backed simulation scenario."""

    def __init__(self) -> None:
        self.world = World()

    @abstractmethod
    def setup(self, timestamp: datetime) -> None:
        """Create entities and initialize scenario-specific state."""

    @abstractmethod
    def step(self, timestamp: datetime) -> object:
        """Run the scenario for exactly one step."""
