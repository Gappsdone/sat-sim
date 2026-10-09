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
then prints the propagated ECI position, velocity, and nine-channel thermal
telemetry once per step:

```shell
uv run python -m sat_sim.scenarios.iss_scenario
```

The ISS scenario initializes nine heaters and paired sensors in a 3x3 grid,
automatically applies PID control when a sensor falls below the 22 °C threshold,
advances the thermal simulation using elapsed wall-clock seconds, and prints
each channel's temperature, heater output/power, threshold, and illumination
alongside the orbital state. These thermal defaults are
illustrative rather than a validated spacecraft thermal model.

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
from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim.simulation import Simulation

simulation = Simulation(ISSScenario())
simulation.run()  # returns when interrupted with Ctrl+C
```

The ISS-specific class fetches its TLE and creates its ECS entity in `setup()`;
`Simulation` calls `step()` at each scheduled tick.

## Thermal control system

`ThermalControlSystem` provides nine paired temperature sensors and heaters by
default. Pairs occupy a row-major 3x3 grid with one meter between neighbors;
smaller channel counts use the first cells. Each sensor below the configured
temperature threshold automatically drives its paired heater with a bounded
PID controller (`kp=1.0`, `ki=0.0`, `kd=0.0` by default):

```python
from datetime import UTC, datetime

from sat_sim.services.tcs import ThermalControlSystem

tcs = ThermalControlSystem(
    sensor_count=9,
    wattages=[10.0] * 9,
    heater_threshold_celsius=22.0,
    kp=0.1,
)
# Automatically controls each paired heater below 22 °C; computes eclipse
# from this Earth-centered inertial position and the UTC timestamp.
tcs.step(1.0, (6_700_000.0, 0.0, 0.0), datetime.now(UTC))

# Manual full-power operation remains available:
tcs.activate_heater(1)
tcs.step(1.0, (6_700_000.0, 0.0, 0.0), datetime.now(UTC))
tcs.deactivate_heater(1)
```

A PID output is clamped to 0–100% of the heater's rated wattage. Its derivative
is based on measured temperature (avoiding setpoint kick), and integral
accumulation uses conditional anti-windup. In automatic mode, each heater
uses the shared threshold; manual activation overrides PID at full power until
deactivated. `set_setpoint(index, target_celsius)` selects an explicit per-heater
PID target instead, while `deactivate_heater(index)` turns it off and suppresses
automatic control until `enable_automatic_control(index)` is called.

The TCS accepts the satellite's Earth-centered inertial position on every step.
It estimates the Sun direction from UTC time, treats Earth as a spherical
6,371 km opaque body, and classifies the spacecraft as eclipsed when it lies
behind Earth inside a cylindrical umbra. It ignores penumbra, atmosphere, panel
orientation, and all other celestial bodies. As an illustrative lumped model,
all sensors warm by 0.02 °C/s in sunlight and cool by 0.01 °C/s in eclipse by
default; both rates are configurable. Each heater independently runs PID while
its paired sensor is strictly below `heater_threshold_celsius` (22 °C by
default), otherwise it turns off. Set the threshold to `None` to disable
automatic heater control.

The intentionally simple thermal model applies each heater's contribution to
every sensor. For distance `d` in meters, its contribution is multiplied by
`1 / (1 + ln(1 + d))`; the paired sensor is at `d=0` and gets full contribution.
Temperature change is `wattage * PID_output_fraction * heating_rate * delta_time *
attenuation`. `heating_rate` is the temperature-rise scale per watt-second,
temperature is in degrees Celsius, and time is in seconds. This logarithmic
attenuation is a qualitative grid interaction model, not a physical heat
diffusion solver. `grid_spacing_m` and the channel count (1–9) are configurable.

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
