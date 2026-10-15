"""Spacecraft attitude components and systems."""

from dataclasses import dataclass
from math import isfinite, sqrt

from sat_sim.ecs import Entity, World
from sat_sim.position import ECIPosition, ECIVelocity


@dataclass
class SpacecraftAttitude:
    """Body axes expressed in ECI; orbital mode points body +Z toward Earth."""

    x_axis_eci: tuple[float, float, float] = (1.0, 0.0, 0.0)
    y_axis_eci: tuple[float, float, float] = (0.0, 1.0, 0.0)
    z_axis_eci: tuple[float, float, float] = (0.0, 0.0, 1.0)
    auto_orient: bool = True


class AttitudeSystem:
    """Construct a nadir-pointing, along-track spacecraft frame each step."""

    @staticmethod
    def update(world: World, entity: Entity) -> SpacecraftAttitude:
        attitude = world.get(entity, SpacecraftAttitude)
        if not attitude.auto_orient or not world.has(entity, ECIVelocity):
            return attitude
        position = world.get(entity, ECIPosition)
        velocity = world.get(entity, ECIVelocity)
        z_axis = _unit_vector(
            "spacecraft position", (-position.x, -position.y, -position.z)
        )
        velocity_vector = (velocity.x, velocity.y, velocity.z)
        along_z = _dot(velocity_vector, z_axis)
        along_track = (
            velocity_vector[0] - along_z * z_axis[0],
            velocity_vector[1] - along_z * z_axis[1],
            velocity_vector[2] - along_z * z_axis[2],
        )
        x_axis = _unit_vector("along-track velocity", along_track)
        y_axis = _cross(z_axis, x_axis)
        attitude.x_axis_eci = x_axis
        attitude.y_axis_eci = y_axis
        attitude.z_axis_eci = z_axis
        return attitude


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _unit_vector(
    name: str, vector: tuple[float, float, float]
) -> tuple[float, float, float]:
    if len(vector) != 3 or not all(isfinite(value) for value in vector):
        raise ValueError(f"{name} must contain three finite coordinates")
    length = sqrt(_dot(vector, vector))
    if length == 0.0 or not isfinite(length):
        raise ValueError(f"{name} must have a finite nonzero length")
    return (vector[0] / length, vector[1] / length, vector[2] / length)
