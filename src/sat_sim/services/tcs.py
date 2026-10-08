"""Simple thermal control system for sensor and heater channels."""

from collections.abc import Sequence

DEFAULT_SENSOR_COUNT = 9


class TemperatureSensor:
    """A temperature sensor reading in degrees Celsius."""

    id: int
    temperature_celsius: float = 0.0

    def __init__(self, id: int, temperature: float = 0.0) -> None:
        self.id = id
        self.temperature_celsius = temperature


class Heater:
    """A controllable heater with a fixed power rating in watts."""

    id: int
    power: float
    active: bool = False

    def __init__(self, id: int, power: float, active: bool = False) -> None:
        if power < 0:
            raise ValueError("power must not be negative")

        self.id = id
        self.power = power
        self.active = active

    def activate(self, active: bool = True) -> None:
        """Activate or deactivate this heater"""
        self.active = active


class ThermalControlSystem:
    """Apply active heater output to paired temperature sensors."""

    def __init__(
        self,
        sensor_count: int = DEFAULT_SENSOR_COUNT
    ) -> None:
        if sensor_count <= 0:
            raise ValueError("sensor_count must be greater than zero")

