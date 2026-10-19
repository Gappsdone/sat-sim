"""Versioned wire models for simulator telemetry."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _camel_case(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)


class WireModel(BaseModel):
    """Immutable model serialized with lower-camel-case field names."""

    model_config = ConfigDict(
        alias_generator=_camel_case,
        populate_by_name=True,
        frozen=True,
    )


class Vector3(WireModel):
    frame: str
    unit: str
    value: tuple[float, float, float]


class AttitudeTelemetry(WireModel):
    frame: Literal["BODY_TO_ECI"] = "BODY_TO_ECI"
    representation: Literal["quaternion"] = "quaternion"
    order: Literal["xyzw"] = "xyzw"
    value: tuple[float, float, float, float]


class ADCSTelemetry(WireModel):
    angular_velocity_body_rad_s: tuple[float, float, float]
    pointing_error_deg: float
    target_quaternion_xyzw: tuple[float, float, float, float]
    commanded_torque_nm: tuple[float, float, float]
    applied_torque_nm: tuple[float, float, float]
    disturbance_torque_nm: tuple[float, float, float]
    wheel_speeds_rad_s: tuple[float, float, float]
    wheel_saturated: tuple[bool, bool, bool]


class IlluminationTelemetry(WireModel):
    sunlit: bool | None
    sun_direction_eci: tuple[float, float, float] | None


class PowerTelemetry(WireModel):
    battery_charge_wh: float
    battery_capacity_wh: float
    state_of_charge: float
    generated_power_w: float
    consumed_power_w: float


class ThermalChannelTelemetry(WireModel):
    id: int
    temperature_c: float
    heater_output: float
    heater_power_w: float
    heater_rated_power_w: float
    setpoint_c: float | None


class EntityTelemetry(WireModel):
    position: Vector3
    velocity: Vector3
    attitude: AttitudeTelemetry
    adcs: ADCSTelemetry
    illumination: IlluminationTelemetry
    power: PowerTelemetry
    thermal_channels: tuple[ThermalChannelTelemetry, ...]


class SimulationStatus(WireModel):
    state: Literal["running", "paused"] = "running"
    time_scale: float = 1.0


class TelemetryFrame(WireModel):
    schema_version: Literal[1] = 1
    sequence: int = Field(ge=0)
    time: datetime
    simulation: SimulationStatus = SimulationStatus()
    entities: dict[str, EntityTelemetry]


class ThermalChannelDescription(WireModel):
    id: int
    position_m: tuple[float, float]
    sensor_normal_body: tuple[float, float, float]
    heater_rated_power_w: float


class ScenarioDescription(WireModel):
    schema_version: Literal[1] = 1
    scenario: str
    entities: tuple[str, ...]
    coordinate_frame: Literal["ECI"] = "ECI"
    position_unit: Literal["m"] = "m"
    velocity_unit: Literal["m/s"] = "m/s"
    attitude_convention: str = "body-to-ECI quaternion in [x, y, z, w] order"
    battery_capacity_wh: float
    solar_panel_peak_power_w: float
    solar_panel_normal_body: tuple[float, float, float]
    thermal_channels: tuple[ThermalChannelDescription, ...]
