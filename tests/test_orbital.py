from datetime import UTC, datetime

from sat_sim.ecs import World
from sat_sim.orbital import create_satellite_from_orbital, propagate_orbital
from sat_sim.position import ECIPosition, ECIVelocity


class FakeOrbital:
    def __init__(self) -> None:
        self.calls: list[tuple[datetime, bool]] = []

    def get_position(
        self,
        utc_time: datetime,
        normalize: bool = False,
    ) -> tuple[list[float], list[float]]:
        self.calls.append((utc_time, normalize))
        return [7_000, -2, 0.5], [1, 2, -3]


def test_propagate_orbital_converts_kilometers_to_si_units() -> None:
    orbital = FakeOrbital()
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    position, velocity = propagate_orbital(orbital, timestamp)

    assert position == ECIPosition(7_000_000, -2_000, 500)
    assert velocity == ECIVelocity(1_000, 2_000, -3_000)
    assert orbital.calls == [(timestamp, False)]


def test_create_satellite_from_orbital_adds_eci_components() -> None:
    world = World()
    orbital = FakeOrbital()
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    entity = create_satellite_from_orbital(world, orbital, timestamp)

    assert world.get(entity, ECIPosition) == ECIPosition(7_000_000, -2_000, 500)
    assert world.get(entity, ECIVelocity) == ECIVelocity(1_000, 2_000, -3_000)
