"""Spacecraft attitude representations and reference-frame helpers."""

from dataclasses import dataclass
from math import isfinite, sqrt

from sat_sim.ecs import Entity, World
from sat_sim.position import ECIPosition, ECIVelocity

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


@dataclass
class SpacecraftAttitude:
    """Body axes expressed in ECI for power and thermal consumers."""

    x_axis_eci: Vector3 = (1.0, 0.0, 0.0)
    y_axis_eci: Vector3 = (0.0, 1.0, 0.0)
    z_axis_eci: Vector3 = (0.0, 0.0, 1.0)
    auto_orient: bool = True

    def set_quaternion(self, quaternion_xyzw: Quaternion) -> None:
        self.x_axis_eci, self.y_axis_eci, self.z_axis_eci = quaternion_to_axes(
            quaternion_xyzw
        )


class AttitudeSystem:
    """Legacy ideal nadir pointing for simulations without ADCS dynamics."""

    @staticmethod
    def update(world: World, entity: Entity) -> SpacecraftAttitude:
        attitude = world.get(entity, SpacecraftAttitude)
        if not attitude.auto_orient or not world.has(entity, ECIVelocity):
            return attitude
        position = world.get(entity, ECIPosition)
        velocity = world.get(entity, ECIVelocity)
        attitude.x_axis_eci, attitude.y_axis_eci, attitude.z_axis_eci = (
            nadir_pointing_axes(
                (position.x, position.y, position.z),
                (velocity.x, velocity.y, velocity.z),
            )
        )
        return attitude


def nadir_pointing_axes(
    position_eci: Vector3, velocity_eci: Vector3
) -> tuple[Vector3, Vector3, Vector3]:
    """Return +X along track, +Y orbit-normal, and +Z nadir body axes."""
    z_axis = unit_vector(
        "spacecraft position",
        (-position_eci[0], -position_eci[1], -position_eci[2]),
    )
    along_z = dot(velocity_eci, z_axis)
    along_track = (
        velocity_eci[0] - along_z * z_axis[0],
        velocity_eci[1] - along_z * z_axis[1],
        velocity_eci[2] - along_z * z_axis[2],
    )
    x_axis = unit_vector("along-track velocity", along_track)
    y_axis = cross(z_axis, x_axis)
    return x_axis, y_axis, z_axis


def quaternion_from_axes(
    x_axis: Vector3, y_axis: Vector3, z_axis: Vector3
) -> Quaternion:
    """Convert body-axis columns of a body-to-ECI matrix to ``[x,y,z,w]``."""
    matrix = (
        (x_axis[0], y_axis[0], z_axis[0]),
        (x_axis[1], y_axis[1], z_axis[1]),
        (x_axis[2], y_axis[2], z_axis[2]),
    )
    trace = matrix[0][0] + matrix[1][1] + matrix[2][2]
    if trace > 0.0:
        scale = sqrt(trace + 1.0) * 2.0
        quaternion = (
            (matrix[2][1] - matrix[1][2]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[1][0] - matrix[0][1]) / scale,
            0.25 * scale,
        )
    else:
        diagonal = (matrix[0][0], matrix[1][1], matrix[2][2])
        index = diagonal.index(max(diagonal))
        if index == 0:
            scale = sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
            quaternion = (
                0.25 * scale,
                (matrix[0][1] + matrix[1][0]) / scale,
                (matrix[0][2] + matrix[2][0]) / scale,
                (matrix[2][1] - matrix[1][2]) / scale,
            )
        elif index == 1:
            scale = sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
            quaternion = (
                (matrix[0][1] + matrix[1][0]) / scale,
                0.25 * scale,
                (matrix[1][2] + matrix[2][1]) / scale,
                (matrix[0][2] - matrix[2][0]) / scale,
            )
        else:
            scale = sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
            quaternion = (
                (matrix[0][2] + matrix[2][0]) / scale,
                (matrix[1][2] + matrix[2][1]) / scale,
                0.25 * scale,
                (matrix[1][0] - matrix[0][1]) / scale,
            )
    return normalize_quaternion(quaternion)


def quaternion_to_axes(
    quaternion_xyzw: Quaternion,
) -> tuple[Vector3, Vector3, Vector3]:
    """Return body-axis columns in ECI for a body-to-ECI quaternion."""
    x, y, z, w = normalize_quaternion(quaternion_xyzw)
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)),
        (2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w)),
        (2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)),
    )


def normalize_quaternion(quaternion: Quaternion) -> Quaternion:
    if len(quaternion) != 4 or not all(isfinite(value) for value in quaternion):
        raise ValueError("quaternion must contain four finite values")
    length = sqrt(sum(value * value for value in quaternion))
    if length == 0.0:
        raise ValueError("quaternion must have a finite nonzero length")
    return tuple(value / length for value in quaternion)  # type: ignore[return-value]


def quaternion_multiply(left: Quaternion, right: Quaternion) -> Quaternion:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def quaternion_conjugate(quaternion: Quaternion) -> Quaternion:
    x, y, z, w = quaternion
    return (-x, -y, -z, w)


def dot(a: Vector3, b: Vector3) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def unit_vector(name: str, vector: Vector3) -> Vector3:
    if len(vector) != 3 or not all(isfinite(value) for value in vector):
        raise ValueError(f"{name} must contain three finite coordinates")
    length = sqrt(dot(vector, vector))
    if length == 0.0 or not isfinite(length):
        raise ValueError(f"{name} must have a finite nonzero length")
    return (vector[0] / length, vector[1] / length, vector[2] / length)
