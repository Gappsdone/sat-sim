"""Electrical power generation, storage, and distribution components."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, sqrt

from sat_sim.attitude import AttitudeSystem, SpacecraftAttitude
from sat_sim.ecs import Entity, World
from sat_sim.position import ECIPosition
from sat_sim.solar import satellite_is_sunlit, solar_direction_eci


@dataclass
class PowerConsumer:
    """Power requested by another spacecraft system."""

    requested_power_w: float = 0.0


@dataclass
class SolarPanel:
    """A body-fixed solar panel represented by its normal and peak power."""

    peak_power_w: float
    normal_body: tuple[float, float, float] = (0.0, 0.0, -1.0)

    def __post_init__(self) -> None:
        _require_nonnegative("peak_power_w", self.peak_power_w)
        self.peak_power_w = float(self.peak_power_w)
        self.normal_body = _unit_vector("normal_body", self.normal_body)


@dataclass
class PCDU:
    """Battery state and latest power-distribution telemetry."""

    capacity_wh: float
    charge_wh: float
    generated_power_w: float = 0.0
    consumed_power_w: float = 0.0
    is_sunlit: bool | None = None

    def __post_init__(self) -> None:
        _require_nonnegative("capacity_wh", self.capacity_wh)
        _require_nonnegative("charge_wh", self.charge_wh)
        if self.capacity_wh == 0.0:
            raise ValueError("capacity_wh must be greater than zero")
        if self.charge_wh > self.capacity_wh:
            raise ValueError("charge_wh must not exceed capacity_wh")
        self.capacity_wh = float(self.capacity_wh)
        self.charge_wh = float(self.charge_wh)

    @property
    def state_of_charge(self) -> float:
        return self.charge_wh / self.capacity_wh


class PCDUSystem:
    """Charge from panel incidence and discharge for all registered loads."""

    @staticmethod
    def update(
        world: World, spacecraft_entity: Entity, delta_time: float, timestamp: datetime
    ) -> PCDU:
        _require_nonnegative("delta_time", delta_time)
        if delta_time == 0.0:
            raise ValueError("delta_time must be greater than zero")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")

        pcdu = world.get(spacecraft_entity, PCDU)
        panel = world.get(spacecraft_entity, SolarPanel)
        position = world.get(spacecraft_entity, ECIPosition)
        attitude = AttitudeSystem.update(world, spacecraft_entity)
        position_m = (position.x, position.y, position.z)
        pcdu.is_sunlit = satellite_is_sunlit(position_m, timestamp)

        generated_power_w = 0.0
        if pcdu.is_sunlit:
            sun_direction = solar_direction_eci(timestamp)
            normal_eci = _body_to_eci(panel.normal_body, attitude)
            incidence = max(0.0, _dot(normal_eci, sun_direction))
            generated_power_w = panel.peak_power_w * incidence

        consumed_power_w = sum(
            consumer.requested_power_w
            for _entity, consumer in world.query(PowerConsumer)
        )
        for _entity, consumer in world.query(PowerConsumer):
            _require_nonnegative("requested_power_w", consumer.requested_power_w)

        pcdu.generated_power_w = generated_power_w
        pcdu.consumed_power_w = consumed_power_w
        net_energy_wh = (generated_power_w - consumed_power_w) * delta_time / 3600.0
        pcdu.charge_wh = min(pcdu.capacity_wh, max(0.0, pcdu.charge_wh + net_energy_wh))
        return pcdu


def _body_to_eci(
    vector: tuple[float, float, float], attitude: SpacecraftAttitude
) -> tuple[float, float, float]:
    x, y, z = vector
    return (
        x * attitude.x_axis_eci[0]
        + y * attitude.y_axis_eci[0]
        + z * attitude.z_axis_eci[0],
        x * attitude.x_axis_eci[1]
        + y * attitude.y_axis_eci[1]
        + z * attitude.z_axis_eci[1],
        x * attitude.x_axis_eci[2]
        + y * attitude.y_axis_eci[2]
        + z * attitude.z_axis_eci[2],
    )


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _unit_vector(
    name: str, vector: tuple[float, float, float]
) -> tuple[float, float, float]:
    if len(vector) != 3 or not all(isfinite(value) for value in vector):
        raise ValueError(f"{name} must contain three finite coordinates")
    length = sqrt(_dot(vector, vector))
    if length == 0.0:
        raise ValueError(f"{name} must have a finite nonzero length")
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative")
