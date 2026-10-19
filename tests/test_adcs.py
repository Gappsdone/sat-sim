from collections.abc import Callable
from math import cos, radians, sin

import pytest

from sat_sim.adcs import (
    ADCSStatus,
    ADCSSystem,
    AttitudeController,
    AttitudeReference,
    AttitudeState,
    ReactionWheelAssembly,
    RigidBody,
    apply_reaction_wheels,
)
from sat_sim.attitude import (
    SpacecraftAttitude,
    quaternion_from_axes,
    quaternion_multiply,
    quaternion_to_axes,
)
from sat_sim.ecs import World
from sat_sim.position import ECIPosition, ECIVelocity


def make_adcs_world() -> tuple[World, int, ADCSSystem]:
    world = World()
    entity = world.create()
    world.add(entity, ECIPosition(1_000_000_000.0, 0.0, 0.0))
    world.add(entity, ECIVelocity(0.0, 1.0, 0.0))
    world.add(entity, SpacecraftAttitude(auto_orient=False))
    world.add(entity, RigidBody((10.0, 10.0, 10.0)))
    world.add(entity, AttitudeState())
    world.add(entity, AttitudeReference())
    world.add(entity, AttitudeController(1.0, 4.0))
    world.add(entity, ReactionWheelAssembly(max_torque_nm=1.0))
    world.add(entity, ADCSStatus())
    system = ADCSSystem(max_substep_s=0.02)
    system.initialize(world, entity)
    return world, entity, system


def test_quaternion_axes_round_trip() -> None:
    axes = ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    quaternion = quaternion_from_axes(*axes)
    converted = quaternion_to_axes(quaternion)
    for actual, expected in zip(converted, axes, strict=True):
        assert actual == pytest.approx(expected)
    assert sum(value * value for value in quaternion) == pytest.approx(1.0)


def test_reaction_wheels_limit_torque_and_momentum() -> None:
    wheels = ReactionWheelAssembly(
        rotor_inertia_kg_m2=1.0,
        max_torque_nm=0.5,
        max_speed_rad_s=1.0,
        speeds_rad_s=(0.9, 0.0, 0.0),
    )
    applied, saturated = apply_reaction_wheels(wheels, (-1.0, 0.25, 0.0), 1.0)
    assert applied == pytest.approx((-0.1, 0.25, 0.0))
    assert wheels.speeds_rad_s == pytest.approx((1.0, -0.25, 0.0))
    assert saturated == (True, False, False)


def test_zero_rate_and_zero_control_preserve_attitude() -> None:
    world, entity, system = make_adcs_world()
    state = world.get(entity, AttitudeState)
    initial = state.quaternion_xyzw
    state.angular_velocity_body_rad_s = (0.0, 0.0, 0.0)
    controller = world.get(entity, AttitudeController)
    controller.proportional_gain_nm = 0.0
    controller.derivative_gain_nms = 0.0

    system.update(world, entity, 10.0)

    assert state.quaternion_xyzw == pytest.approx(initial)
    assert state.angular_velocity_body_rad_s == (0.0, 0.0, 0.0)


def test_nadir_controller_reduces_ten_degree_pointing_error() -> None:
    world, entity, system = make_adcs_world()
    state = world.get(entity, AttitudeState)
    half_angle = radians(10.0) / 2.0
    error_rotation = (sin(half_angle), 0.0, 0.0, cos(half_angle))
    reference = world.get(entity, AttitudeReference).quaternion_xyzw
    state.quaternion_xyzw = quaternion_multiply(reference, error_rotation)
    state.angular_velocity_body_rad_s = (0.0, 0.0, 0.0)

    initial_status = system.update(world, entity, 0.02)
    initial_error = initial_status.pointing_error_deg
    for _ in range(500):
        status = system.update(world, entity, 0.02)

    assert initial_error > 9.0
    assert status.pointing_error_deg < 1.0
    assert sum(value * value for value in state.quaternion_xyzw) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "component",
    [
        lambda: RigidBody((1.0, 0.0, 1.0)),
        lambda: AttitudeState((0.0, 0.0, 0.0, 0.0)),
        lambda: AttitudeController(-1.0, 1.0),
        lambda: ReactionWheelAssembly(max_torque_nm=0.0),
    ],
)
def test_invalid_adcs_configuration_is_rejected(
    component: Callable[[], object],
) -> None:
    with pytest.raises(ValueError):
        component()
