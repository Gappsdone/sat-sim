"""Grid-based thermal control with independent PID-controlled heater channels."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from math import cos, hypot, isfinite, log1p, radians, sin, sqrt

DEFAULT_SENSOR_COUNT = 9
GRID_WIDTH = 3
DEFAULT_GRID_SPACING_METERS = 1.0
EARTH_RADIUS_METERS = 6_371_000.0
DEFAULT_HEATER_THRESHOLD_CELSIUS = 22.0
DEFAULT_SUNLIT_WARMING_RATE_CELSIUS_PER_SECOND = 0.02
DEFAULT_ECLIPSE_COOLING_RATE_CELSIUS_PER_SECOND = 0.01


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
        self._integral = 0.0
        self._previous_measurement: float | None = None

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
        self.active = bool(active)
        self.setpoint_celsius: float | None = None
        self.output_fraction = 1.0 if active else 0.0
        self._manual_override = bool(active)
        self.automatic_control_enabled = True

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

        self.heating_rate = float(heating_rate)
        self.grid_spacing_m = float(grid_spacing_m)
        self.heater_threshold_celsius = (
            None
            if heater_threshold_celsius is None
            else float(heater_threshold_celsius)
        )
        self.sunlit_warming_rate_celsius_per_second = float(
            sunlit_warming_rate_celsius_per_second
        )
        self.eclipse_cooling_rate_celsius_per_second = float(
            eclipse_cooling_rate_celsius_per_second
        )
        self.is_sunlit: bool | None = None
        self.satellite_position_m: tuple[float, float, float] | None = None
        positions = [
            (
                float(index % GRID_WIDTH) * self.grid_spacing_m,
                float(index // GRID_WIDTH) * self.grid_spacing_m,
            )
            for index in range(sensor_count)
        ]
        self.sensors = [
            TemperatureSensor(index, initial_temperature, positions[index])
            for index in range(sensor_count)
        ]
        self.heaters = [
            Heater(
                index,
                power,
                pid=PIDController(kp, ki, kd),
                position=positions[index],
            )
            for index, power in enumerate(powers)
        ]

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
        if not isinstance(timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        _validate_delta_time(delta_time)
        is_sunlit = satellite_is_sunlit(satellite_position_m, timestamp)
        self.is_sunlit = is_sunlit
        self.satellite_position_m = satellite_position_m
        environmental_rate = (
            self.sunlit_warming_rate_celsius_per_second
            if is_sunlit
            else -self.eclipse_cooling_rate_celsius_per_second
        )
        outputs: list[float] = []
        for index, heater in enumerate(self.heaters):
            measurement = self.sensors[index].temperature_celsius
            threshold = (
                heater.setpoint_celsius
                if heater.setpoint_celsius is not None
                else self.heater_threshold_celsius
            )
            if heater._manual_override:
                output = 1.0
            elif (
                heater.automatic_control_enabled
                and threshold is not None
                and measurement < threshold
            ):
                output = heater.pid.update(threshold, measurement, delta_time)
            else:
                output = 0.0
                heater.pid.reset()
            heater.output_fraction = output
            heater.active = output > 0.0
            outputs.append(output)

        temperature_deltas = [0.0] * len(self.sensors)
        for heater, output in zip(self.heaters, outputs, strict=True):
            if output <= 0.0 or heater.power <= 0.0:
                continue
            for target_index, sensor in enumerate(self.sensors):
                distance_m = hypot(
                    heater.position[0] - sensor.position[0],
                    heater.position[1] - sensor.position[1],
                )
                attenuation = 1.0 / (1.0 + log1p(distance_m))
                temperature_deltas[target_index] += (
                    heater.power * self.heating_rate * output * delta_time * attenuation
                )

        # Environmental sun/eclipse effects apply uniformly to each panel in
        # this lumped model; planet/moon illumination and view factors are omitted.
        for index in range(len(temperature_deltas)):
            temperature_deltas[index] += environmental_rate * delta_time

        for sensor, temperature_delta in zip(
            self.sensors, temperature_deltas, strict=True
        ):
            sensor.temperature_celsius += temperature_delta


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
