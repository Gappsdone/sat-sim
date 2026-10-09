"""Grid-based thermal control with independent PID-controlled heater channels."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import cos, hypot, isfinite, log1p, radians, sin, sqrt

from sat_sim.ecs import Entity, World
from sat_sim.position import ECIPosition

DEFAULT_SENSOR_COUNT = 9
GRID_WIDTH = 3
DEFAULT_GRID_SPACING_METERS = 1.0
EARTH_RADIUS_METERS = 6_371_000.0
DEFAULT_HEATER_THRESHOLD_CELSIUS = 22.0
DEFAULT_SUNLIT_WARMING_RATE_CELSIUS_PER_SECOND = 0.02
DEFAULT_ECLIPSE_COOLING_RATE_CELSIUS_PER_SECOND = 0.01


@dataclass
class PIDState:
    """Mutable controller history stored as an ECS component."""

    integral: float = 0.0
    previous_measurement: float | None = None


@dataclass
class IlluminationState:
    """Spacecraft illumination and position supplied to thermal systems."""

    is_sunlit: bool | None = None
    position_m: tuple[float, float, float] | None = None


@dataclass
class HeaterCommand:
    """Per-channel requested output and operator/automatic control mode."""

    output_fraction: float = 0.0
    active: bool = False
    setpoint_celsius: float | None = None
    manual_override: bool = False
    automatic_control_enabled: bool = True


class TemperatureSensor:
    """A temperature sensor reading in degrees Celsius at a grid position."""

    def __init__(
        self,
        id: int,
        temperature: float = 0.0,
        position: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        _require_finite("temperature", temperature)
        if len(position) != 2 or not all(
            isfinite(coordinate) for coordinate in position
        ):
            raise ValueError("position must contain two finite coordinates")
        self.id = id
        self.temperature_celsius = float(temperature)
        self.position = position


class PIDController:
    """A bounded PID controller with derivative-on-measurement and anti-windup.

    Controller output is a fraction in [0, 1] of heater rated power. The
    derivative is taken from the measured temperature to avoid setpoint kick.
    """

    def __init__(
        self,
        kp: float = 1.0,
        ki: float = 0.0,
        kd: float = 0.0,
        *,
        output_min: float = 0.0,
        output_max: float = 1.0,
        state: PIDState | None = None,
    ) -> None:
        for name, value in (("kp", kp), ("ki", ki), ("kd", kd)):
            _require_finite(name, value)
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        _require_finite("output_min", output_min)
        _require_finite("output_max", output_max)
        if output_min < 0 or output_max <= output_min or output_max > 1.0:
            raise ValueError("output limits must satisfy 0 <= min < max <= 1")
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.output_min = float(output_min)
        self.output_max = float(output_max)
        self.state = state if state is not None else PIDState()

    @property
    def _integral(self) -> float:
        return self.state.integral

    @_integral.setter
    def _integral(self, value: float) -> None:
        self.state.integral = value

    @property
    def _previous_measurement(self) -> float | None:
        return self.state.previous_measurement

    @_previous_measurement.setter
    def _previous_measurement(self, value: float | None) -> None:
        self.state.previous_measurement = value

    def reset(self) -> None:
        """Clear accumulated integral and derivative history."""
        self._integral = 0.0
        self._previous_measurement = None

    def update(self, setpoint: float, measurement: float, delta_time: float) -> float:
        """Return the bounded heater output for one control interval."""
        _require_finite("setpoint", setpoint)
        _require_finite("measurement", measurement)
        _validate_delta_time(delta_time)

        error = setpoint - measurement
        derivative = 0.0
        if self._previous_measurement is not None:
            derivative = (measurement - self._previous_measurement) / delta_time
        proposed_integral = self._integral + error * delta_time
        raw_output = (
            self.kp * error + self.ki * proposed_integral - self.kd * derivative
        )
        output = min(self.output_max, max(self.output_min, raw_output))

        # Integrate only when unsaturated or when the error would unwind the
        # current saturation. This prevents prolonged error from winding up I.
        if (
            (output == raw_output and self.output_min < raw_output < self.output_max)
            or (output == self.output_max and error < 0)
            or (output == self.output_min and error > 0)
        ):
            self._integral = proposed_integral
        self._previous_measurement = float(measurement)
        return output


class Heater:
    """A controllable heater with fixed rated power and an optional setpoint."""

    def __init__(
        self,
        id: int,
        power: float,
        active: bool = False,
        *,
        pid: PIDController | None = None,
        position: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        _require_finite("wattage", power)
        if power < 0:
            raise ValueError("wattage must not be negative")
        if len(position) != 2 or not all(
            isfinite(coordinate) for coordinate in position
        ):
            raise ValueError("position must contain two finite coordinates")
        self.id = id
        self.sensor_id = id
        self.power = float(power)
        self.position = position
        self.pid = pid if pid is not None else PIDController()
        self.command = HeaterCommand(
            output_fraction=1.0 if active else 0.0,
            active=bool(active),
            manual_override=bool(active),
        )

    @property
    def active(self) -> bool:
        return self.command.active

    @active.setter
    def active(self, value: bool) -> None:
        self.command.active = bool(value)

    @property
    def output_fraction(self) -> float:
        return self.command.output_fraction

    @output_fraction.setter
    def output_fraction(self, value: float) -> None:
        self.command.output_fraction = value

    @property
    def setpoint_celsius(self) -> float | None:
        return self.command.setpoint_celsius

    @setpoint_celsius.setter
    def setpoint_celsius(self, value: float | None) -> None:
        self.command.setpoint_celsius = value

    @property
    def _manual_override(self) -> bool:
        return self.command.manual_override

    @_manual_override.setter
    def _manual_override(self, value: bool) -> None:
        self.command.manual_override = value

    @property
    def automatic_control_enabled(self) -> bool:
        return self.command.automatic_control_enabled

    @automatic_control_enabled.setter
    def automatic_control_enabled(self, value: bool) -> None:
        self.command.automatic_control_enabled = value

    @property
    def manual_override(self) -> bool:
        """Whether explicit activation is currently overriding PID control."""
        return self._manual_override

    def activate(self, active: bool = True) -> None:
        """Enable or disable manual full-power operation."""
        self._manual_override = bool(active)
        self.automatic_control_enabled = True
        self.active = bool(active)
        self.output_fraction = 1.0 if active else 0.0
        if not active:
            self.pid.reset()

    def deactivate(self) -> None:
        """Disable heating and automatic control until explicitly re-enabled."""
        self.activate(False)
        self.setpoint_celsius = None
        self.automatic_control_enabled = False


@dataclass
class ThermalConfiguration:
    """Tunable thermal-system parameters, separate from per-entity state."""

    heating_rate: float
    grid_spacing_m: float
    heater_threshold_celsius: float | None
    sunlit_warming_rate_celsius_per_second: float
    eclipse_cooling_rate_celsius_per_second: float


class IlluminationSystem:
    """Update spacecraft illumination state from ECI position and UTC time."""

    @staticmethod
    def update(world: World, entity: Entity, timestamp: datetime) -> IlluminationState:
        position = world.get(entity, ECIPosition)
        position_m = (position.x, position.y, position.z)
        if not world.has(entity, IlluminationState):
            world.add(entity, IlluminationState())
        state = world.get(entity, IlluminationState)
        state.is_sunlit = satellite_is_sunlit(position_m, timestamp)
        state.position_m = position_m
        return state


class HeaterControlSystem:
    """Calculate heater commands from ECS temperature and actuator state."""

    @staticmethod
    def update(world: World, delta_time: float, threshold: float | None) -> None:
        _validate_delta_time(delta_time)
        for _entity, sensor, heater, command, _pid_state in world.query(
            TemperatureSensor, Heater, HeaterCommand, PIDState
        ):
            measurement = sensor.temperature_celsius
            setpoint = (
                command.setpoint_celsius
                if command.setpoint_celsius is not None
                else threshold
            )
            if command.manual_override:
                output = 1.0
            elif (
                command.automatic_control_enabled
                and setpoint is not None
                and measurement < setpoint
            ):
                output = heater.pid.update(setpoint, measurement, delta_time)
            else:
                output = 0.0
                heater.pid.reset()
            command.output_fraction = output
            command.active = output > 0.0


class ThermalDynamicsSystem:
    """Apply heater heat and environmental effects to ECS temperature state."""

    @staticmethod
    def update(
        world: World,
        delta_time: float,
        configuration: ThermalConfiguration,
        is_sunlit: bool,
    ) -> None:
        channels = list(world.query(TemperatureSensor, Heater, HeaterCommand))
        environmental_rate = (
            configuration.sunlit_warming_rate_celsius_per_second
            if is_sunlit
            else -configuration.eclipse_cooling_rate_celsius_per_second
        )
        deltas = {entity: 0.0 for entity, _sensor, _heater, _command in channels}
        for _heater_entity, _heater_sensor, heater, command in channels:
            output = command.output_fraction
            if output <= 0.0 or heater.power <= 0.0:
                continue
            for (
                target_entity,
                target_sensor,
                _target_heater,
                _target_command,
            ) in channels:
                distance_m = hypot(
                    heater.position[0] - target_sensor.position[0],
                    heater.position[1] - target_sensor.position[1],
                )
                attenuation = 1.0 / (1.0 + log1p(distance_m))
                deltas[target_entity] += (
                    heater.power
                    * configuration.heating_rate
                    * output
                    * delta_time
                    * attenuation
                )
        for entity, sensor, _heater, _command in channels:
            deltas[entity] += environmental_rate * delta_time
            sensor.temperature_celsius += deltas[entity]


class ThermalControlSystem:
    """Control paired sensors/heaters on a 3x3 grid.

    A pair's own heater contributes at full strength. Other heaters contribute
    with logarithmic attenuation ``1 / (1 + ln(1 + distance_m))``. Grid
    coordinates are row-major, separated by ``grid_spacing_m``. This is a
    qualitative diffusion approximation, not a physical heat-transfer solver.
    """

    def __init__(
        self,
        sensor_count: int = DEFAULT_SENSOR_COUNT,
        initial_temperature: float = 0.0,
        wattages: Sequence[float] | None = None,
        heating_rate: float = 1.0,
        *,
        kp: float = 1.0,
        ki: float = 0.0,
        kd: float = 0.0,
        grid_spacing_m: float = DEFAULT_GRID_SPACING_METERS,
        heater_threshold_celsius: float | None = DEFAULT_HEATER_THRESHOLD_CELSIUS,
        sunlit_warming_rate_celsius_per_second: float = (
            DEFAULT_SUNLIT_WARMING_RATE_CELSIUS_PER_SECOND
        ),
        eclipse_cooling_rate_celsius_per_second: float = (
            DEFAULT_ECLIPSE_COOLING_RATE_CELSIUS_PER_SECOND
        ),
        world: World | None = None,
    ) -> None:
        if not isinstance(sensor_count, int) or isinstance(sensor_count, bool):
            raise ValueError("sensor_count must be an integer from 1 to 9")
        if not 1 <= sensor_count <= GRID_WIDTH**2:
            raise ValueError("sensor_count must be from 1 to 9 for a 3x3 grid")
        _require_finite("initial_temperature", initial_temperature)
        _require_finite("heating_rate", heating_rate)
        if heating_rate < 0:
            raise ValueError("heating_rate must not be negative")
        _require_finite("grid_spacing_m", grid_spacing_m)
        if grid_spacing_m <= 0:
            raise ValueError("grid_spacing_m must be greater than zero")
        if heater_threshold_celsius is not None:
            _require_finite("heater_threshold_celsius", heater_threshold_celsius)
        for name, rate in (
            (
                "sunlit_warming_rate_celsius_per_second",
                sunlit_warming_rate_celsius_per_second,
            ),
            (
                "eclipse_cooling_rate_celsius_per_second",
                eclipse_cooling_rate_celsius_per_second,
            ),
        ):
            _require_finite(name, rate)
            if rate < 0:
                raise ValueError(f"{name} must not be negative")

        if wattages is None:
            powers = [10.0] * sensor_count
        else:
            powers = list(wattages)
            if len(powers) != sensor_count:
                raise ValueError("provide one value per sensor for wattages")
        for power in powers:
            _require_finite("wattage", power)
            if power < 0:
                raise ValueError("wattage must not be negative")

        self.configuration = ThermalConfiguration(
            heating_rate=float(heating_rate),
            grid_spacing_m=float(grid_spacing_m),
            heater_threshold_celsius=(
                None
                if heater_threshold_celsius is None
                else float(heater_threshold_celsius)
            ),
            sunlit_warming_rate_celsius_per_second=float(
                sunlit_warming_rate_celsius_per_second
            ),
            eclipse_cooling_rate_celsius_per_second=float(
                eclipse_cooling_rate_celsius_per_second
            ),
        )
        positions = [
            (
                float(index % GRID_WIDTH) * self.grid_spacing_m,
                float(index // GRID_WIDTH) * self.grid_spacing_m,
            )
            for index in range(sensor_count)
        ]
        sensors = [
            TemperatureSensor(index, initial_temperature, positions[index])
            for index in range(sensor_count)
        ]
        heaters = [
            Heater(
                index,
                power,
                pid=PIDController(kp, ki, kd),
                position=positions[index],
            )
            for index, power in enumerate(powers)
        ]
        self.world = world if world is not None else World()
        self.thermal_entities: list[Entity] = []
        self.spacecraft_entity: Entity | None = None
        if world is None:
            self.spacecraft_entity = self.world.create()
            self.world.add(self.spacecraft_entity, ECIPosition(0.0, 0.0, 0.0))
            self.world.add(self.spacecraft_entity, IlluminationState())
        for sensor, heater in zip(sensors, heaters, strict=True):
            entity = self.world.create()
            self.world.add(entity, sensor)
            self.world.add(entity, heater)
            self.world.add(entity, heater.command)
            self.world.add(entity, heater.pid.state)
            self.thermal_entities.append(entity)
        self.illumination_system = IlluminationSystem()
        self.heater_control_system = HeaterControlSystem()
        self.thermal_dynamics_system = ThermalDynamicsSystem()

    @property
    def sensors(self) -> list[TemperatureSensor]:
        """Compatibility view of sensor components in ECS entity order."""
        return [
            self.world.get(entity, TemperatureSensor)
            for entity in self.thermal_entities
        ]

    @property
    def heaters(self) -> list[Heater]:
        """Compatibility view of heater components in ECS entity order."""
        return [self.world.get(entity, Heater) for entity in self.thermal_entities]

    def bind_spacecraft_entity(self, entity: Entity) -> None:
        """Attach illumination state to the spacecraft entity in this world."""
        if self.world is None:
            raise RuntimeError("thermal system has no ECS world")
        if not self.world.has(entity, ECIPosition):
            raise KeyError(f"Entity {entity} has no ECIPosition component")
        self.spacecraft_entity = entity
        if not self.world.has(entity, IlluminationState):
            self.world.add(entity, IlluminationState())

    def bind_world(self, world: World) -> None:
        """Move thermal-node components into a scenario-owned ECS world."""
        if world is self.world:
            return
        sensors = self.sensors
        heaters = self.heaters
        for entity in self.thermal_entities:
            self.world.destroy(entity)
        self.world = world
        self.thermal_entities = []
        for sensor, heater in zip(sensors, heaters, strict=True):
            entity = world.create()
            world.add(entity, sensor)
            world.add(entity, heater)
            world.add(entity, heater.command)
            world.add(entity, heater.pid.state)
            self.thermal_entities.append(entity)
        self.spacecraft_entity = None

    @property
    def illumination_state(self) -> IlluminationState:
        if self.spacecraft_entity is None:
            raise RuntimeError("thermal system is not bound to a spacecraft entity")
        return self.world.get(self.spacecraft_entity, IlluminationState)

    @property
    def is_sunlit(self) -> bool | None:
        if self.spacecraft_entity is None:
            return None
        return self.illumination_state.is_sunlit

    @property
    def heater_threshold_celsius(self) -> float | None:
        return self.configuration.heater_threshold_celsius

    @heater_threshold_celsius.setter
    def heater_threshold_celsius(self, value: float | None) -> None:
        self.configuration.heater_threshold_celsius = value

    @property
    def heating_rate(self) -> float:
        return self.configuration.heating_rate

    @heating_rate.setter
    def heating_rate(self, value: float) -> None:
        self.configuration.heating_rate = value

    @property
    def grid_spacing_m(self) -> float:
        return self.configuration.grid_spacing_m

    @grid_spacing_m.setter
    def grid_spacing_m(self, value: float) -> None:
        self.configuration.grid_spacing_m = value

    @property
    def sunlit_warming_rate_celsius_per_second(self) -> float:
        return self.configuration.sunlit_warming_rate_celsius_per_second

    @sunlit_warming_rate_celsius_per_second.setter
    def sunlit_warming_rate_celsius_per_second(self, value: float) -> None:
        self.configuration.sunlit_warming_rate_celsius_per_second = value

    @property
    def eclipse_cooling_rate_celsius_per_second(self) -> float:
        return self.configuration.eclipse_cooling_rate_celsius_per_second

    @eclipse_cooling_rate_celsius_per_second.setter
    def eclipse_cooling_rate_celsius_per_second(self, value: float) -> None:
        self.configuration.eclipse_cooling_rate_celsius_per_second = value

    @property
    def satellite_position_m(self) -> tuple[float, float, float] | None:
        if self.spacecraft_entity is None:
            return None
        return self.illumination_state.position_m

    def set_setpoint(self, heater_index: int, temperature_celsius: float) -> None:
        """Enable PID control for one heater at a target temperature."""
        _require_finite("setpoint", temperature_celsius)
        heater = self.heaters[heater_index]
        heater._manual_override = False
        heater.automatic_control_enabled = True
        heater.setpoint_celsius = float(temperature_celsius)
        heater.pid.reset()
        heater.output_fraction = 0.0
        heater.active = False

    def activate_heater(self, heater_index: int) -> None:
        """Run one heater at full power in manual mode."""
        heater = self.heaters[heater_index]
        heater.automatic_control_enabled = False
        heater.setpoint_celsius = None
        heater.activate()

    def deactivate_heater(self, heater_index: int) -> None:
        """Turn one heater off and disable its automatic control."""
        self.heaters[heater_index].deactivate()

    def enable_automatic_control(self, heater_index: int) -> None:
        """Re-enable threshold-based control for one heater."""
        heater = self.heaters[heater_index]
        heater._manual_override = False
        heater.setpoint_celsius = None
        heater.pid.reset()
        heater.automatic_control_enabled = True
        heater.output_fraction = 0.0
        heater.active = False

    def step(
        self,
        delta_time: float,
        satellite_position_m: tuple[float, float, float],
        timestamp: datetime,
    ) -> None:
        """Advance eclipse heating/cooling and all sensor/heater channels.

        ``satellite_position_m`` is an Earth-centered inertial position. The
        timestamp must be timezone-aware UTC so it can be used to approximate
        the Sun direction in the same inertial frame.
        """
        _validate_delta_time(delta_time)
        if not isinstance(timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if len(satellite_position_m) != 3 or not all(
            isfinite(coordinate) for coordinate in satellite_position_m
        ):
            raise ValueError(
                "satellite_position_m must contain three finite coordinates"
            )
        if self.spacecraft_entity is None:
            raise RuntimeError("thermal system is not bound to a spacecraft entity")
        spacecraft_position = self.world.get(self.spacecraft_entity, ECIPosition)
        spacecraft_position.x, spacecraft_position.y, spacecraft_position.z = (
            satellite_position_m
        )
        self.advance(delta_time, timestamp)

    def advance(self, delta_time: float, timestamp: datetime) -> None:
        """Run illumination, control, and dynamics against ECS state in order."""
        _validate_delta_time(delta_time)
        if not isinstance(timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if self.spacecraft_entity is None:
            raise RuntimeError("thermal system is not bound to a spacecraft entity")
        self.illumination_system.update(self.world, self.spacecraft_entity, timestamp)
        is_sunlit = self.is_sunlit
        assert is_sunlit is not None
        self.heater_control_system.update(
            self.world, delta_time, self.heater_threshold_celsius
        )
        self.thermal_dynamics_system.update(
            self.world, delta_time, self.configuration, is_sunlit
        )


def solar_direction_eci(timestamp: datetime) -> tuple[float, float, float]:
    """Approximate the Sun's unit direction in the ECI frame for a UTC time.

    This low-precision mean-orbit approximation is adequate for a simple
    umbra/shadow decision, not precision orbit determination.
    """
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    utc_time = timestamp.astimezone(UTC)
    days_since_j2000 = (
        utc_time - datetime(2000, 1, 1, 12, tzinfo=UTC)
    ).total_seconds() / 86_400.0
    mean_longitude = radians((280.460 + 0.9856474 * days_since_j2000) % 360.0)
    mean_anomaly = radians((357.528 + 0.9856003 * days_since_j2000) % 360.0)
    ecliptic_longitude = (
        mean_longitude
        + radians(1.915) * sin(mean_anomaly)
        + radians(0.020) * sin(2.0 * mean_anomaly)
    )
    obliquity = radians(23.439 - 0.0000004 * days_since_j2000)
    return (
        cos(ecliptic_longitude),
        cos(obliquity) * sin(ecliptic_longitude),
        sin(obliquity) * sin(ecliptic_longitude),
    )


def satellite_is_sunlit(
    satellite_position_m: tuple[float, float, float], timestamp: datetime
) -> bool:
    """Return false only when Earth blocks the Sun (cylindrical umbra model).

    Earth is treated as a sphere of ``EARTH_RADIUS_METERS``. Atmospheric
    refraction, penumbra, other bodies, and attitude/panel orientation are
    intentionally ignored.
    """
    if len(satellite_position_m) != 3 or not all(
        isfinite(coordinate) for coordinate in satellite_position_m
    ):
        raise ValueError("satellite_position_m must contain three finite coordinates")
    sun_direction = solar_direction_eci(timestamp)
    along_sun = sum(
        coordinate * direction
        for coordinate, direction in zip(
            satellite_position_m, sun_direction, strict=True
        )
    )
    if along_sun >= 0.0:
        return True
    distance_from_shadow_axis = sqrt(
        max(
            0.0,
            sum(coordinate * coordinate for coordinate in satellite_position_m)
            - along_sun * along_sun,
        )
    )
    return distance_from_shadow_axis >= EARTH_RADIUS_METERS


def _require_finite(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")


def _validate_delta_time(delta_time: float) -> None:
    _require_finite("delta_time", delta_time)
    if delta_time <= 0:
        raise ValueError("delta_time must be greater than zero")
