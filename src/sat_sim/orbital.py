"""Adapters for populating ECS components from pyorbital propagators."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sat_sim.ecs import Entity, World
from sat_sim.position import ECIPosition, ECIVelocity

_KILOMETERS_TO_METERS = 1_000.0


class OrbitalLike(Protocol):
    """Minimum interface required from a pyorbital ``Orbital`` object."""

    def get_position(
        self,
        utc_time: datetime,
        normalize: bool = False,
    ) -> tuple[Sequence[float], Sequence[float]]: ...


def propagate_orbital(
    orbital: OrbitalLike,
    timestamp: datetime,
) -> tuple[ECIPosition, ECIVelocity]:
    """Propagate an orbital object and convert pyorbital output to SI units.

    pyorbital returns ECI position in kilometers and ECI velocity in kilometers
    per second. The adapter stores both components in meters-based SI units.
    """
    position_km, velocity_km_per_second = orbital.get_position(
        timestamp,
        normalize=False,
    )
    position = ECIPosition(
        *(coordinate * _KILOMETERS_TO_METERS for coordinate in position_km)
    )
    velocity = ECIVelocity(
        *(coordinate * _KILOMETERS_TO_METERS for coordinate in velocity_km_per_second)
    )
    return position, velocity


def create_satellite_from_orbital(
    world: World,
    orbital: OrbitalLike,
    timestamp: datetime,
) -> Entity:
    """Create an entity with ECI components from a propagated orbit."""
    position, velocity = propagate_orbital(orbital, timestamp)
    entity = world.create()
    world.add(entity, position)
    world.add(entity, velocity)
    return entity
