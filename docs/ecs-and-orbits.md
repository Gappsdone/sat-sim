# Ecs And Orbits

## ECS example

Create a world, add a satellite with an ECEF position, and advance it with the
movement system. Positions use Earth-Centered, Earth-Fixed Cartesian coordinates
in meters. Velocities use the corresponding ECEF frame in meters per second.

```python
from sat_sim.ecs import World
from sat_sim.position import Position
from sat_sim.simulation import Velocity, create_satellite

world = World()
satellite = create_satellite(world, Position(6_700_000, 0, 0), Velocity(0, 7_500, 0))

print(world.get(satellite, Position))
# Position(x=6700000.0, y=3750.0, z=0.0)
```

`World` supports entity creation and destruction, component add/get/remove/has
operations, and type-based queries:

```python
for entity, position, velocity in world.query(Position, Velocity):
    print(entity, position, velocity)
```

## PyOrbital TEME adapter

The orbital adapter accepts an existing `pyorbital.Orbital` object. It does not
load TLE data or convert coordinate frames. PyOrbital's propagated SGP4 output is
in the TEME frame and converted from kilometers and kilometers per second into
meters and meters per second, then stored in the legacy-named `ECIPosition` and
`ECIVelocity` components.

```python
from datetime import datetime, timezone

from pyorbital.orbital import Orbital
from sat_sim.ecs import World
from sat_sim.orbital import ECIPosition, create_satellite_from_orbital

orbital = Orbital("satellite", tle_file="path/to/tle.txt")
world = World()
satellite = create_satellite_from_orbital(
    world,
    orbital,
    datetime.now(timezone.utc),
)

print(world.get(satellite, ECIPosition))
```

