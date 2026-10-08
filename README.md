# sat-sim

A small, runnable Python starter application with a simple entity-component-system (ECS).

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

## Setup

Create the virtual environment and install the development dependencies:

```shell
uv sync
```

The project includes `pyorbital` for orbital propagation and `numpy`, `scipy`,
and `pyproj` transitively for its calculations.

## Run

Run the starter application:

```shell
uv run python -m sat_sim
```

or with the installed console script:

```shell
uv run sat-sim
```

Run the live ISS scenario. It fetches the current ISS TLE from CelesTrak,
then prints the propagated ECI position immediately and once per second:

```shell
uv run python -m sat_sim.iss_scenario
```

The simulation runs continuously until you press `Ctrl+C`. `Simulation.run()`
handles `KeyboardInterrupt` internally and returns when stopped. It fetches
the TLE once during `ISSScenario.setup()`, reuses one orbital propagator, and
uses a monotonic clock to avoid accumulating drift. The ISS scenario requires
network access; its HTTP request has a 10-second timeout, and transient network
errors are retried twice with a one-second delay between attempts.

## Scenario architecture

A `Scenario` is an abstract ECS-backed unit with two lifecycle methods:

- `setup(timestamp)` creates entities and initializes scenario-specific state.
- `step(timestamp)` advances the scenario and returns the state to report.

`Simulation` owns scheduling and accepts a `Scenario` in its constructor. This
keeps timing independent from scenario setup and allows other scenarios to reuse
the same one-second scheduler:

```python
from sat_sim.iss_scenario import ISSScenario, print_iss_position
from sat_sim.simulation import Simulation

simulation = Simulation(ISSScenario(), printer=print_iss_position)
simulation.run()  # returns when interrupted with Ctrl+C
```

The ISS-specific class fetches its TLE and creates its ECS entity in `setup()`;
`Simulation` calls `step()` at each scheduled tick.

## Thermal control system

`ThermalControlSystem` provides nine paired temperature sensors and heaters by
default. The channel count is configurable, and heater wattage controls the
rate of temperature increase:

```python
from sat_sim.services.tcs import ThermalControlSystem

tcs = ThermalControlSystem(sensor_count=9, wattages=[10.0] * 9)
tcs.activate_heater(0)
tcs.step(2.0)  # channel 0 increases by 20 °C at the default rate
tcs.deactivate_heater(0)
```

The thermal model is intentionally simple: each active channel increases by
`wattage * heating_rate * delta_time`. Temperatures are in degrees Celsius,
wattage is in watts, and time is in seconds.

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

## pyorbital ECI adapter

The orbital adapter accepts an existing `pyorbital.Orbital` object. It does not
load TLE data or convert coordinate frames. Pyorbital's propagated ECI output is
converted from kilometers and kilometers per second into meters and meters per
second, then stored in `ECIPosition` and `ECIVelocity` components.

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

## Test

```shell
uv run pytest
```

## Quality checks

Format the project:

```shell
uv run ruff format .
```

Check lint, formatting, types, and coverage:

```shell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest  # runs with coverage; fails below 90%
```
