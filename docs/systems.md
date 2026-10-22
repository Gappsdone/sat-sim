# Systems

## Attitude determination and control

`ISSScenario` uses the rigid-body ADCS model in `sat_sim.adcs` instead of
instantaneously forcing the ideal orbital frame. Its body-to-ECI quaternion and
body angular velocity are integrated from Euler's rotational equation with
configurable principal moments of inertia. A quaternion-error PD controller
tracks a nadir reference where body +Z points toward Earth and body +X follows
the projected along-track velocity.

Three orthogonal reaction wheels apply equal-and-opposite spacecraft torque.
Each wheel enforces motor-torque and rotor-speed limits and reports its speed
and saturation state. The default integrator subdivides scenario steps into at
most 0.1 second intervals and normalizes the quaternion after every substep.
The initial state is aligned with the current nadir frame and initialized at
the orbital-frame angular rate. These parameters are illustrative spacecraft
values, not validated ISS hardware values.

The dynamics also accept independently testable environmental-torque models.
The ISS scenario enables a point-mass Earth gravity-gradient model by default;
pass `gravity_gradient_enabled=False` to `ISSScenario` to disable it. The model
uses SI units and evaluates `3 μ/r³ (r̂ × I r̂)` in spacecraft body axes on
every integration substep.

An aerodynamic-drag torque model is also enabled by default and can be disabled
with `aerodynamic_drag_enabled=False`. It subtracts a co-rotating atmosphere's
velocity from the ECI spacecraft velocity, evaluates a constant-density drag
force, transforms that force into body axes, and applies it at a configurable
center-of-pressure offset. Its default density, area, and geometry are
illustrative rather than an ISS atmosphere or structural model.

Solar-radiation-pressure and residual-magnetic-dipole torques complete the
initial disturbance set. SRP uses the existing Sun/eclipse model and a fixed
body-frame center-of-pressure offset. The magnetic model uses a centered axial
Earth dipole and a configurable fixed spacecraft residual dipole. Disable them
with `solar_radiation_pressure_enabled=False` and
`residual_magnetic_dipole_enabled=False`, respectively.

The scenario owns ADCS scheduling: orbit propagation, reference/control,
rigid-body integration, thermal dynamics, and finally electrical accounting.
Thermal and power systems consume the completed attitude without changing it.
Standalone `ThermalControlSystem` users retain the legacy ideal
`AttitudeSystem` behavior unless they supply their own fixed attitude.
Telemetry includes body rates, target quaternion, pointing error, commanded,
applied, and disturbance torque, wheel speeds, and wheel saturation. The ADCS
also contributes an 8 W default idle electrical load.

The scenario installs an illustrative gyro, Sun sensor, magnetometer, and Earth
vector sensor. Their bias, drift, noise, and validity can be configured through
`ADCSSensorConfiguration`. A deterministic complementary estimator integrates
gyro measurements and corrects the quaternion with whichever vector sensors
are valid; the controller uses this estimate rather than truth state. Estimated
attitude, measured body rate, and sensor-valid flags are included in telemetry.

`ADCSModeState` supports nadir pointing, inertial hold, Sun pointing, safe mode,
and magnetic detumble. Losing the gyro or every absolute-vector sensor causes
automatic safe-mode entry and publishes a fault reason. A three-axis limited
magnetorquer damps body rates in detumble mode and counters reaction-wheel
unloading torque whenever wheel speed exceeds the configured momentum threshold.
Mode, fault, commanded dipole, and magnetic torque are exposed in telemetry.

## Thermal control system

`ThermalControlSystem` provides nine paired temperature sensors and heaters by
default. Pairs occupy a row-major 3x3 grid with one meter between neighbors;
smaller channel counts use the first cells. Each channel is stored as a thermal
node entity in an ECS `World`, with `TemperatureSensor`, `Heater`,
`HeaterCommand`, and `PIDState` components. The spacecraft illumination state is
stored on its ECS entity as `IlluminationState`. In `ISSScenario`, orbital and
thermal entities share the scenario's `World`.

The attitude helpers live in `sat_sim.attitude`. Outside the integrated ISS
scenario, the TCS facade runs ideal attitude, illumination, heater control, and
thermal dynamics in that order. If no ECI velocity is present, the frame remains
fixed (identity by default). Set `auto_orient=False` to supply a fixed frame.
Scenario telemetry is read from ECS queries into an immutable snapshot. The
compatibility `sensors` and `heaters` properties return channel-ordered views;
new code should query the ECS world directly.

Each sensor below the configured temperature threshold automatically drives its
paired heater with a bounded PID controller (`kp=1.0`, `ki=0.0`, `kd=0.0` by
default):

```python
from datetime import UTC, datetime

from sat_sim.services.tcs import ThermalControlSystem

tcs = ThermalControlSystem(
    sensor_count=9,
    wattages=[10.0] * 9,
    heater_threshold_celsius=22.0,
    kp=0.1,
)
# Runs illumination, heater-control, then thermal-dynamics systems.
tcs.step(1.0, (6_700_000.0, 0.0, 0.0), datetime.now(UTC))

# Manual full-power operation remains available:
tcs.activate_heater(1)
tcs.step(1.0, (6_700_000.0, 0.0, 0.0), datetime.now(UTC))
tcs.deactivate_heater(1)
```

To model sensors on different faces, pass one body-frame normal per channel,
for example `sensor_normals_body=[(1, 0, 0), (-1, 0, 0)]` with
`sensor_count=2`. Opposing faces cannot both receive direct sunlight at the
same instant. The normals are normalized when sensors are created.

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
behind Earth inside a cylindrical umbra. It ignores penumbra, atmosphere, and
all other celestial bodies. Each sensor has a unit normal in the spacecraft body
frame (`sensor_normals_body` in the constructor); the default is body +Z for all
nine sensors, modeling one planar grid. In sunlight, solar warming is scaled by
`max(0, normal_ECI · sun_direction_ECI)`, so a sensor turned away from the Sun
receives no direct solar heat. In eclipse, all sensors cool. The default maximum
sun-facing warming rate is 0.02 °C/s and eclipse cooling is 0.01 °C/s; both are
configurable. This is an illustrative direct-solar model, not a full radiative
heat-transfer simulation. Each heater independently runs PID while
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

## Power control and distribution

The ISS entity has `PCDU` and `SolarPanel` components. `PCDUSystem` converts
panel incidence into generated power with
`peak_power_w * max(0, panel_normal_ECI · sun_direction_ECI)` and produces no
power while the spacecraft is in Earth's eclipse. Net watt-seconds are
converted to watt-hours and applied to the battery, clamped between empty and
its configured capacity.

Spacecraft loads expose a `PowerConsumer` component. Each TCS heater updates its
requested power from its rated wattage and PID output, and ADCS contributes its
idle load, before the PCDU totals all consumers. The ISS scenario reports
battery charge, generated power, and consumed power on every step. The defaults
are a 1,000 Wh battery initially charged to 500 Wh and a 100 W panel mounted on
body -Z; these values are configurable in the `ISSScenario` constructor.

