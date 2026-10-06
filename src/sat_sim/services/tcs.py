"""Simple thermal control system for sensor and heater channels."""

from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_SENSOR_COUNT = 9


@dataclass(slots=True)
class TemperatureSensor:
    """A temperature sensor reading in degrees Celsius."""

    temperature_celsius: float = 0.0

class Heater:
    """A controllable heater with a fixed power rating in watts."""

    power: float
    active: bool = False

    def __post_init__(self) -> None:
        if self.power < 0:
            raise ValueError("power must not be negative")

    def activate(self) -> None:
        """Turn the heater on."""
        self.active = True

    def deactivate(self) -> None:
        """Turn the heater off."""
        self.active = False

    def get_current_power(self) -> float:
        """Return the current power output of the heater."""
        return self.power if self.active else 0.0


class ThermalControlSystem:
    """Apply active heater output to paired temperature sensors."""

    def __init__(
        self,
        sensor_count: int = DEFAULT_SENSOR_COUNT,
        *,
        initial_temperature: float = 0.0,
        powers: Sequence[float] | None = None,
        heating_rate: float = 1.0,
    ) -> None:
        if sensor_count <= 0:
            raise ValueError("sensor_count must be greater than zero")
        if heating_rate < 0:
            raise ValueError("heating_rate must not be negative")

        configured_powers = self._validate_powers(sensor_count, powers)
        self.heating_rate = heating_rate
        self.sensors = [
            TemperatureSensor(initial_temperature) for _ in range(sensor_count)
        ]
        self.heaters = [Heater(power) for power in configured_powers]

    def activate_heater(self, index: int) -> None:
        """Activate the heater paired with a sensor index."""
        self.heaters[index].activate()

    def deactivate_heater(self, index: int) -> None:
        """Deactivate the heater paired with a sensor index."""
        self.heaters[index].deactivate()

    def step(self, delta_time: float) -> None:
        """Update sensor temperatures for one simulation interval."""
        if delta_time < 0:
            raise ValueError("delta_time must not be negative")

        for sensor, heater in zip(self.sensors, self.heaters, strict=True):
            if heater.active:
                sensor.temperature_celsius += (
                    heater.power * self.heating_rate * delta_time
                )

    @staticmethod
    def _validate_powers(
        sensor_count: int,
        powers: Sequence[float] | None,
    ) -> list[float]:
        configured_powers = (
            [0.0] * sensor_count if powers is None else list(powers)
        )
        if len(configured_powers) != sensor_count:
            raise ValueError("powers must contain one value per sensor")
        if any(power < 0 for power in configured_powers):
            raise ValueError("power must not be negative")
        return configured_powers
