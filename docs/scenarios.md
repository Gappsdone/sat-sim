# Scenarios

## Run

Start the live ISS simulation with the command-line interface:

```shell
uv run python -m sat_sim
```

or with the installed console script:

```shell
uv run sat-sim
```

Both commands start the live telemetry API on `127.0.0.1:8000`, advancing the
selected simulation and serving it to the Cesium frontend. Configure the step
interval, TLE request timeout, and API bind address when needed:

```shell
uv run sat-sim --scenario iss --interval 0.5 --tle-timeout 5
```

Use `--offline` to run the terminal-only simulation instead. The online
telemetry publisher currently supports the ISS scenario; additional scenarios
will need telemetry adapters before they can run online.

Run `uv run sat-sim --help` for the complete CLI reference.

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

Shared Earth geometry, gravity, rotation, magnetic-field, and solar-radiation
pressure values are defined in `sat_sim.constants` using SI units. Tunable
spacecraft design values remain with their owning simulation components.

