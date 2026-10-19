from collections.abc import Callable
from datetime import UTC, datetime
from math import cos, radians, sin, sqrt

import pytest

from sat_sim.adcs import (
    ADCSFaultState,
    ADCSMode,
    ADCSModeState,
    ADCSSensorConfiguration,
    ADCSSensorMeasurements,
    ADCSStatus,
    ADCSSystem,
    AerodynamicDragTorque,
    AttitudeController,
    AttitudeEstimate,
    AttitudeEstimatorConfiguration,
    AttitudeReference,
    AttitudeState,
    GravityGradientTorque,
    MagnetorquerAssembly,
    MomentumManagementConfiguration,
    ReactionWheelAssembly,
    ResidualMagneticDipoleTorque,
    RigidBody,
    SolarRadiationPressureTorque,
    apply_magnetorquer,
    apply_reaction_wheels,
)
from sat_sim.attitude import (
    SpacecraftAttitude,
    dot,
    quaternion_from_axes,
    quaternion_multiply,
    quaternion_to_axes,
)
from sat_sim.ecs import World
from sat_sim.position import ECIPosition, ECIVelocity
from sat_sim.solar import EARTH_RADIUS_METERS, solar_direction_eci


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
    world.add(
        entity,
        ADCSSensorConfiguration(
            gyro_bias_rad_s=(0.0, 0.0, 0.0),
            gyro_noise_std_rad_s=0.0,
            gyro_bias_drift_std_rad_s2=0.0,
            vector_noise_std=0.0,
        ),
    )
    world.add(entity, ADCSSensorMeasurements())
    world.add(entity, AttitudeEstimate())
    world.add(entity, AttitudeEstimatorConfiguration())
    world.add(entity, ADCSModeState())
    world.add(entity, ADCSFaultState())
    world.add(entity, MagnetorquerAssembly())
    world.add(entity, MomentumManagementConfiguration())
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
        None,
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
        None,
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
        None,
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
        None,
    )

    assert torque == (0.0, 0.0, 0.0)


def test_solar_radiation_pressure_torque_matches_force_and_lever_arm() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    sun = solar_direction_eci(timestamp)
    model = SolarRadiationPressureTorque(
        pressure_n_m2=2.0,
        reflectivity_coefficient=3.0,
        reference_area_m2=4.0,
        center_of_pressure_body_m=(0.0, 0.0, 1.0),
    )

    torque = model.torque_body_nm(
        RigidBody(),
        AttitudeState(),
        ECIPosition(*(7_000_000.0 * value for value in sun)),
        ECIVelocity(0.0, 0.0, 0.0),
        timestamp,
    )

    assert torque == pytest.approx((24.0 * sun[1], -24.0 * sun[0], 0.0))


def test_solar_radiation_pressure_is_zero_in_eclipse() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    sun = solar_direction_eci(timestamp)
    model = SolarRadiationPressureTorque()

    torque = model.torque_body_nm(
        RigidBody(),
        AttitudeState(),
        ECIPosition(*(-7_000_000.0 * value for value in sun)),
        ECIVelocity(0.0, 0.0, 0.0),
        timestamp,
    )

    assert torque == (0.0, 0.0, 0.0)


def test_residual_magnetic_dipole_torque_at_magnetic_equator() -> None:
    model = ResidualMagneticDipoleTorque((0.05, 0.0, 0.0))

    torque = model.torque_body_nm(
        RigidBody(),
        AttitudeState(),
        ECIPosition(EARTH_RADIUS_METERS, 0.0, 0.0),
        ECIVelocity(0.0, 0.0, 0.0),
        None,
    )

    assert torque == pytest.approx((0.0, 0.05 * 3.12e-5, 0.0))


def test_nadir_controller_reduces_ten_degree_pointing_error() -> None:
    world, entity, system = make_adcs_world()
    state = world.get(entity, AttitudeState)
    half_angle = radians(10.0) / 2.0
    error_rotation = (sin(half_angle), 0.0, 0.0, cos(half_angle))
    reference = world.get(entity, AttitudeReference).quaternion_xyzw
    state.quaternion_xyzw = quaternion_multiply(reference, error_rotation)
    state.angular_velocity_body_rad_s = (0.0, 0.0, 0.0)
    world.get(entity, AttitudeEstimate).quaternion_xyzw = state.quaternion_xyzw

    initial_status = system.update(world, entity, 0.02)
    initial_error = initial_status.pointing_error_deg
    for _ in range(500):
        status = system.update(world, entity, 0.02)

    assert initial_error > 9.0
    assert status.pointing_error_deg < 1.0
    assert sum(value * value for value in state.quaternion_xyzw) == pytest.approx(1.0)


def test_sensor_suite_populates_measurements_and_normalized_estimate() -> None:
    world, entity, system = make_adcs_world()

    system.update(
        world,
        entity,
        0.1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    measurements = world.get(entity, ADCSSensorMeasurements)
    estimate = world.get(entity, AttitudeEstimate)
    assert measurements.gyro_valid
    assert measurements.earth_sensor_valid
    assert measurements.magnetometer_valid
    assert measurements.nadir_direction_body is not None
    assert measurements.magnetic_field_body_t is not None
    assert sum(value * value for value in estimate.quaternion_xyzw) == pytest.approx(
        1.0
    )


def test_invalid_sensors_are_excluded_from_estimator() -> None:
    world, entity, system = make_adcs_world()
    sensors = world.get(entity, ADCSSensorConfiguration)
    sensors.gyro_valid = False
    sensors.sun_sensor_valid = False
    sensors.magnetometer_valid = False
    sensors.earth_sensor_valid = False
    estimate = world.get(entity, AttitudeEstimate)
    initial = estimate.quaternion_xyzw

    system.update(
        world,
        entity,
        0.1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    measurements = world.get(entity, ADCSSensorMeasurements)
    assert estimate.quaternion_xyzw == pytest.approx(initial)
    assert not measurements.gyro_valid
    assert not measurements.sun_sensor_valid
    assert not measurements.magnetometer_valid
    assert not measurements.earth_sensor_valid


def test_sensor_fault_enters_safe_mode() -> None:
    world, entity, system = make_adcs_world()
    world.get(entity, ADCSSensorConfiguration).gyro_valid = False

    system.update(
        world,
        entity,
        0.1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert world.get(entity, ADCSModeState).current == ADCSMode.SAFE_MODE
    assert world.get(entity, ADCSFaultState).safe_mode_reason == "sensor fault"


def test_inertial_hold_captures_current_attitude() -> None:
    world, entity, system = make_adcs_world()
    mode = world.get(entity, ADCSModeState)
    state = world.get(entity, AttitudeState)
    expected = state.quaternion_xyzw
    mode.requested = ADCSMode.INERTIAL_HOLD

    system.update(world, entity, 0.1)

    assert mode.current == ADCSMode.INERTIAL_HOLD
    assert mode.inertial_hold_quaternion_xyzw == pytest.approx(expected)


def test_magnetorquer_projects_and_limits_requested_torque() -> None:
    magnetorquer = MagnetorquerAssembly(max_dipole_a_m2=2.0)

    torque = apply_magnetorquer(
        magnetorquer,
        (0.0, 0.0, 1.0),
        (4.0, 0.0, 3.0),
    )

    assert magnetorquer.commanded_dipole_a_m2 == pytest.approx((0.0, 4.0, 0.0))
    assert torque == pytest.approx((2.0, 0.0, 0.0))


def test_detumble_commands_rate_opposing_magnetic_torque() -> None:
    world, entity, system = make_adcs_world()
    mode = world.get(entity, ADCSModeState)
    mode.requested = ADCSMode.DETUMBLE
    estimate = world.get(entity, AttitudeEstimate)
    estimate.angular_velocity_body_rad_s = (0.1, 0.0, 0.0)
    state = world.get(entity, AttitudeState)
    state.angular_velocity_body_rad_s = estimate.angular_velocity_body_rad_s

    system.update(world, entity, 0.1)

    torque = world.get(entity, MagnetorquerAssembly).applied_torque_nm
    assert dot(torque, (0.1, 0.0, 0.0)) < 0.0


def test_momentum_unloading_reduces_high_wheel_speed() -> None:
    world, entity, system = make_adcs_world()
    wheels = world.get(entity, ReactionWheelAssembly)
    wheels.speeds_rad_s = (500.0, 0.0, 0.0)
    initial_speed = wheels.speeds_rad_s[0]
    controller = world.get(entity, AttitudeController)
    controller.proportional_gain_nm = 0.0
    controller.derivative_gain_nms = 0.0

    system.update(world, entity, 0.1)

    assert abs(wheels.speeds_rad_s[0]) < abs(initial_speed)


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
