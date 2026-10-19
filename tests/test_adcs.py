from collections.abc import Callable
from math import cos, radians, sin, sqrt

import pytest

from sat_sim.adcs import (
    ADCSStatus,
    ADCSSystem,
    AerodynamicDragTorque,
    AttitudeController,
    AttitudeReference,
    AttitudeState,
    GravityGradientTorque,
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
    assert world.get(entity, ADCSStatus).disturbance_torque_nm == (0.0, 0.0, 0.0)


def test_gravity_gradient_is_zero_along_a_principal_axis() -> None:
    model = GravityGradientTorque()
    body = RigidBody((10.0, 20.0, 30.0))
    state = AttitudeState()

    torque = model.torque_body_nm(
        body,
        state,
        ECIPosition(7_000_000.0, 0.0, 0.0),
        ECIVelocity(0.0, 0.0, 0.0),
    )

    assert torque == pytest.approx((0.0, 0.0, 0.0))


def test_gravity_gradient_matches_point_mass_equation() -> None:
    model = GravityGradientTorque(gravitational_parameter_m3_s2=1.0)
    body = RigidBody((1.0, 2.0, 4.0))
    state = AttitudeState()
    radius = 2.0
    component = radius / sqrt(2.0)

    torque = model.torque_body_nm(
        body,
        state,
        ECIPosition(component, component, 0.0),
        ECIVelocity(0.0, 0.0, 0.0),
    )

    assert torque == pytest.approx((0.0, 0.0, 3.0 / 16.0))


def test_adcs_sums_disturbance_torque_into_dynamics() -> None:
    world, entity, _system = make_adcs_world()
    controller = world.get(entity, AttitudeController)
    controller.proportional_gain_nm = 0.0
    controller.derivative_gain_nms = 0.0
    world.get(entity, ECIPosition).x = sqrt(2.0)
    world.get(entity, ECIPosition).y = sqrt(2.0)
    world.get(entity, RigidBody).inertia_kg_m2 = (10.0, 20.0, 30.0)
    world.get(entity, AttitudeState).quaternion_xyzw = (0.0, 0.0, 0.0, 1.0)
    system = ADCSSystem(
        max_substep_s=1.0,
        disturbance_models=(GravityGradientTorque(1.0),),
    )

    status = system.update(world, entity, 1.0)

    assert status.disturbance_torque_nm == pytest.approx((0.0, 0.0, 15.0 / 8.0))
    assert world.get(entity, AttitudeState).angular_velocity_body_rad_s[2] == (
        pytest.approx(1.0 / 16.0)
    )


def test_aerodynamic_drag_torque_matches_force_and_lever_arm() -> None:
    model = AerodynamicDragTorque(
        atmospheric_density_kg_m3=2.0,
        drag_coefficient=1.0,
        reference_area_m2=1.0,
        center_of_pressure_body_m=(0.0, 1.0, 0.0),
        atmosphere_angular_velocity_rad_s=0.0,
    )

    torque = model.torque_body_nm(
        RigidBody(),
        AttitudeState(),
        ECIPosition(1.0, 0.0, 0.0),
        ECIVelocity(2.0, 0.0, 0.0),
    )

    assert torque == pytest.approx((0.0, 0.0, 4.0))


def test_aerodynamic_drag_accounts_for_corotating_atmosphere() -> None:
    model = AerodynamicDragTorque(
        atmospheric_density_kg_m3=1.0,
        drag_coefficient=1.0,
        reference_area_m2=1.0,
        center_of_pressure_body_m=(0.0, 1.0, 0.0),
        atmosphere_angular_velocity_rad_s=2.0,
    )

    torque = model.torque_body_nm(
        RigidBody(),
        AttitudeState(),
        ECIPosition(1.0, 0.0, 0.0),
        ECIVelocity(0.0, 2.0, 0.0),
    )

    assert torque == (0.0, 0.0, 0.0)


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
        lambda: GravityGradientTorque(0.0),
        lambda: AerodynamicDragTorque(drag_coefficient=0.0),
    ],
)
def test_invalid_adcs_configuration_is_rejected(
    component: Callable[[], object],
) -> None:
    with pytest.raises(ValueError):
        component()
