"""Rigid-body attitude dynamics, nadir control, and reaction-wheel actuation."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import acos, ceil, isfinite, pi, sqrt
from random import Random
from typing import Protocol

from sat_sim.attitude import (
    Quaternion,
    SpacecraftAttitude,
    Vector3,
    cross,
    dot,
    nadir_pointing_axes,
    normalize_quaternion,
    quaternion_conjugate,
    quaternion_from_axes,
    quaternion_multiply,
    quaternion_to_axes,
    unit_vector,
)
from sat_sim.constants import (
    EARTH_ANGULAR_VELOCITY_RAD_S,
    EARTH_EQUATORIAL_MAGNETIC_FIELD_T,
    EARTH_GRAVITATIONAL_PARAMETER_M3_S2,
    EARTH_MEAN_RADIUS_METERS,
    SOLAR_RADIATION_PRESSURE_N_M2,
)
from sat_sim.ecs import Entity, World
from sat_sim.position import ECIPosition, ECIVelocity
from sat_sim.solar import satellite_is_sunlit, solar_direction_eci


@dataclass
class RigidBody:
    """Spacecraft principal moments of inertia in body axes."""

    inertia_kg_m2: Vector3 = (120.0, 100.0, 80.0)

    def __post_init__(self) -> None:
        _require_vector("inertia_kg_m2", self.inertia_kg_m2, positive=True)


@dataclass
class AttitudeState:
    """Body-to-ECI orientation and body-frame angular velocity."""

    quaternion_xyzw: Quaternion = (0.0, 0.0, 0.0, 1.0)
    angular_velocity_body_rad_s: Vector3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        self.quaternion_xyzw = normalize_quaternion(self.quaternion_xyzw)
        _require_vector("angular_velocity_body_rad_s", self.angular_velocity_body_rad_s)


@dataclass
class AttitudeReference:
    """Desired body-to-ECI orientation and inertial rotation rate."""

    quaternion_xyzw: Quaternion = (0.0, 0.0, 0.0, 1.0)
    angular_velocity_eci_rad_s: Vector3 = (0.0, 0.0, 0.0)


@dataclass
class AttitudeController:
    """Quaternion-error proportional/derivative controller gains."""

    proportional_gain_nm: float = 0.8
    derivative_gain_nms: float = 8.0

    def __post_init__(self) -> None:
        _require_nonnegative("proportional_gain_nm", self.proportional_gain_nm)
        _require_nonnegative("derivative_gain_nms", self.derivative_gain_nms)


@dataclass
class ReactionWheelAssembly:
    """Three orthogonal reaction wheels aligned with the body axes."""

    rotor_inertia_kg_m2: float = 0.02
    max_torque_nm: float = 0.2
    max_speed_rad_s: float = 600.0
    speeds_rad_s: Vector3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        _require_positive("rotor_inertia_kg_m2", self.rotor_inertia_kg_m2)
        _require_positive("max_torque_nm", self.max_torque_nm)
        _require_positive("max_speed_rad_s", self.max_speed_rad_s)
        _require_vector("speeds_rad_s", self.speeds_rad_s)
        if any(abs(speed) > self.max_speed_rad_s for speed in self.speeds_rad_s):
            raise ValueError("wheel speed must not exceed max_speed_rad_s")


@dataclass
class ADCSStatus:
    """Latest controller, actuator, and pointing telemetry."""

    pointing_error_deg: float = 0.0
    commanded_torque_nm: Vector3 = (0.0, 0.0, 0.0)
    applied_torque_nm: Vector3 = (0.0, 0.0, 0.0)
    disturbance_torque_nm: Vector3 = (0.0, 0.0, 0.0)
    wheel_saturated: tuple[bool, bool, bool] = (False, False, False)


@dataclass
class ADCSSensorConfiguration:
    """Noise, bias, and availability for illustrative ADCS sensors."""

    gyro_bias_rad_s: Vector3 = (1.0e-5, -1.0e-5, 5.0e-6)
    gyro_noise_std_rad_s: float = 2.0e-6
    gyro_bias_drift_std_rad_s2: float = 1.0e-8
    vector_noise_std: float = 1.0e-4
    gyro_valid: bool = True
    sun_sensor_valid: bool = True
    magnetometer_valid: bool = True
    earth_sensor_valid: bool = True

    def __post_init__(self) -> None:
        _require_vector("gyro_bias_rad_s", self.gyro_bias_rad_s)
        _require_nonnegative("gyro_noise_std_rad_s", self.gyro_noise_std_rad_s)
        _require_nonnegative(
            "gyro_bias_drift_std_rad_s2", self.gyro_bias_drift_std_rad_s2
        )
        _require_nonnegative("vector_noise_std", self.vector_noise_std)


@dataclass
class ADCSSensorMeasurements:
    """Latest body-frame sensor measurements and validity flags."""

    angular_velocity_body_rad_s: Vector3 = (0.0, 0.0, 0.0)
    sun_direction_body: Vector3 | None = None
    magnetic_field_body_t: Vector3 | None = None
    nadir_direction_body: Vector3 | None = None
    gyro_valid: bool = False
    sun_sensor_valid: bool = False
    magnetometer_valid: bool = False
    earth_sensor_valid: bool = False


@dataclass
class AttitudeEstimate:
    """Estimated body-to-ECI attitude and body angular velocity."""

    quaternion_xyzw: Quaternion = (0.0, 0.0, 0.0, 1.0)
    angular_velocity_body_rad_s: Vector3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        self.quaternion_xyzw = normalize_quaternion(self.quaternion_xyzw)
        _require_vector("angular_velocity_body_rad_s", self.angular_velocity_body_rad_s)


@dataclass
class AttitudeEstimatorConfiguration:
    """Complementary-estimator vector correction gain."""

    correction_gain_rad_s: float = 0.2

    def __post_init__(self) -> None:
        _require_nonnegative("correction_gain_rad_s", self.correction_gain_rad_s)


class ADCSMode(StrEnum):
    NADIR_POINTING = "NADIR_POINTING"
    INERTIAL_HOLD = "INERTIAL_HOLD"
    SUN_POINTING = "SUN_POINTING"
    SAFE_MODE = "SAFE_MODE"
    DETUMBLE = "DETUMBLE"


@dataclass
class ADCSModeState:
    """Requested/current control mode and inertial-hold target."""

    requested: ADCSMode = ADCSMode.NADIR_POINTING
    current: ADCSMode = ADCSMode.NADIR_POINTING
    inertial_hold_quaternion_xyzw: Quaternion = (0.0, 0.0, 0.0, 1.0)


@dataclass
class ADCSFaultState:
    """Latched sensor/actuator fault summary and automatic-mode reason."""

    sensor_fault: bool = False
    wheel_fault: bool = False
    safe_mode_reason: str | None = None


@dataclass
class MagnetorquerAssembly:
    """Three-axis magnetic dipole actuator with per-axis saturation."""

    max_dipole_a_m2: float = 20.0
    commanded_dipole_a_m2: Vector3 = (0.0, 0.0, 0.0)
    applied_torque_nm: Vector3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        _require_positive("max_dipole_a_m2", self.max_dipole_a_m2)


@dataclass
class MomentumManagementConfiguration:
    """Wheel unloading and magnetic detumble gains and thresholds."""

    unload_threshold_fraction: float = 0.7
    unload_gain_per_s: float = 0.05
    detumble_gain_nms: float = 2.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.unload_threshold_fraction <= 1.0:
            raise ValueError("unload_threshold_fraction must be between zero and one")
        _require_nonnegative("unload_gain_per_s", self.unload_gain_per_s)
        _require_nonnegative("detumble_gain_nms", self.detumble_gain_nms)


class DisturbanceTorqueModel(Protocol):
    """Calculate an environmental torque in spacecraft body axes."""

    def torque_body_nm(
        self,
        body: RigidBody,
        state: AttitudeState,
        position: ECIPosition,
        velocity: ECIVelocity,
        timestamp: datetime | None,
    ) -> Vector3: ...


@dataclass(frozen=True)
class GravityGradientTorque:
    """Gravity-gradient torque from a point-mass Earth model."""

    gravitational_parameter_m3_s2: float = EARTH_GRAVITATIONAL_PARAMETER_M3_S2

    def __post_init__(self) -> None:
        _require_positive(
            "gravitational_parameter_m3_s2", self.gravitational_parameter_m3_s2
        )

    def torque_body_nm(
        self,
        body: RigidBody,
        state: AttitudeState,
        position: ECIPosition,
        velocity: ECIVelocity,
        timestamp: datetime | None,
    ) -> Vector3:
        """Return ``3 mu / r^3 * (r_hat cross I r_hat)`` in body axes."""
        del velocity, timestamp
        position_eci = (position.x, position.y, position.z)
        radius = sqrt(dot(position_eci, position_eci))
        if not isfinite(radius) or radius <= 0.0:
            raise ValueError("position radius must be finite and greater than zero")
        radial_body = _eci_to_body(
            tuple(value / radius for value in position_eci),  # type: ignore[arg-type]
            state.quaternion_xyzw,
        )
        inertia_radial = tuple(
            body.inertia_kg_m2[index] * radial_body[index] for index in range(3)
        )
        scale = 3.0 * self.gravitational_parameter_m3_s2 / radius**3
        torque = cross(radial_body, inertia_radial)  # type: ignore[arg-type]
        return tuple(scale * value for value in torque)  # type: ignore[return-value]


@dataclass(frozen=True)
class AerodynamicDragTorque:
    """Free-molecular drag torque using a constant atmospheric density."""

    atmospheric_density_kg_m3: float = 4.0e-12
    drag_coefficient: float = 2.2
    reference_area_m2: float = 10.0
    center_of_pressure_body_m: Vector3 = (0.0, 0.5, 0.0)
    atmosphere_angular_velocity_rad_s: float = EARTH_ANGULAR_VELOCITY_RAD_S

    def __post_init__(self) -> None:
        _require_nonnegative(
            "atmospheric_density_kg_m3", self.atmospheric_density_kg_m3
        )
        _require_positive("drag_coefficient", self.drag_coefficient)
        _require_positive("reference_area_m2", self.reference_area_m2)
        _require_vector("center_of_pressure_body_m", self.center_of_pressure_body_m)
        _require_nonnegative(
            "atmosphere_angular_velocity_rad_s",
            self.atmosphere_angular_velocity_rad_s,
        )

    def torque_body_nm(
        self,
        body: RigidBody,
        state: AttitudeState,
        position: ECIPosition,
        velocity: ECIVelocity,
        timestamp: datetime | None,
    ) -> Vector3:
        """Return center-of-pressure lever arm crossed with body-frame drag."""
        del body, timestamp
        atmosphere_velocity_eci = (
            -self.atmosphere_angular_velocity_rad_s * position.y,
            self.atmosphere_angular_velocity_rad_s * position.x,
            0.0,
        )
        relative_velocity_eci = (
            velocity.x - atmosphere_velocity_eci[0],
            velocity.y - atmosphere_velocity_eci[1],
            velocity.z - atmosphere_velocity_eci[2],
        )
        speed = sqrt(dot(relative_velocity_eci, relative_velocity_eci))
        if not isfinite(speed):
            raise ValueError("relative atmospheric velocity must be finite")
        if speed == 0.0 or self.atmospheric_density_kg_m3 == 0.0:
            return (0.0, 0.0, 0.0)
        force_scale = (
            -0.5
            * self.atmospheric_density_kg_m3
            * self.drag_coefficient
            * self.reference_area_m2
            * speed
        )
        force_body = _eci_to_body(
            tuple(force_scale * value for value in relative_velocity_eci),  # type: ignore[arg-type]
            state.quaternion_xyzw,
        )
        return cross(self.center_of_pressure_body_m, force_body)


@dataclass(frozen=True)
class SolarRadiationPressureTorque:
    """Cannonball solar-radiation-pressure torque at a fixed body lever arm."""

    pressure_n_m2: float = SOLAR_RADIATION_PRESSURE_N_M2
    reflectivity_coefficient: float = 1.5
    reference_area_m2: float = 10.0
    center_of_pressure_body_m: Vector3 = (0.0, 0.0, 0.5)

    def __post_init__(self) -> None:
        _require_nonnegative("pressure_n_m2", self.pressure_n_m2)
        _require_nonnegative("reflectivity_coefficient", self.reflectivity_coefficient)
        _require_positive("reference_area_m2", self.reference_area_m2)
        _require_vector("center_of_pressure_body_m", self.center_of_pressure_body_m)

    def torque_body_nm(
        self,
        body: RigidBody,
        state: AttitudeState,
        position: ECIPosition,
        velocity: ECIVelocity,
        timestamp: datetime | None,
    ) -> Vector3:
        """Return zero in eclipse or without time, otherwise pressure torque."""
        del body, velocity
        if timestamp is None:
            return (0.0, 0.0, 0.0)
        position_eci = (position.x, position.y, position.z)
        if not satellite_is_sunlit(position_eci, timestamp):
            return (0.0, 0.0, 0.0)
        sun_direction = solar_direction_eci(timestamp)
        force_magnitude = (
            self.pressure_n_m2 * self.reflectivity_coefficient * self.reference_area_m2
        )
        force_body = _eci_to_body(
            tuple(-force_magnitude * value for value in sun_direction),  # type: ignore[arg-type]
            state.quaternion_xyzw,
        )
        return cross(self.center_of_pressure_body_m, force_body)


def earth_magnetic_field_eci(position: ECIPosition) -> Vector3:
    """Approximate Earth's field as an axial centered dipole in ECI."""
    position_eci = (position.x, position.y, position.z)
    radius = sqrt(dot(position_eci, position_eci))
    if not isfinite(radius) or radius <= 0.0:
        raise ValueError("position radius must be finite and greater than zero")
    radial = tuple(value / radius for value in position_eci)
    dipole_axis: Vector3 = (0.0, 0.0, 1.0)
    projection = dot(dipole_axis, radial)  # type: ignore[arg-type]
    scale = EARTH_EQUATORIAL_MAGNETIC_FIELD_T * (EARTH_MEAN_RADIUS_METERS / radius) ** 3
    return tuple(
        scale * (3.0 * projection * radial[index] - dipole_axis[index])
        for index in range(3)
    )  # type: ignore[return-value]


@dataclass(frozen=True)
class ResidualMagneticDipoleTorque:
    """Torque from a fixed spacecraft residual dipole in Earth's field."""

    residual_dipole_body_a_m2: Vector3 = (0.05, 0.0, 0.0)

    def __post_init__(self) -> None:
        _require_vector("residual_dipole_body_a_m2", self.residual_dipole_body_a_m2)

    def torque_body_nm(
        self,
        body: RigidBody,
        state: AttitudeState,
        position: ECIPosition,
        velocity: ECIVelocity,
        timestamp: datetime | None,
    ) -> Vector3:
        del body, velocity, timestamp
        field_body = _eci_to_body(
            earth_magnetic_field_eci(position), state.quaternion_xyzw
        )
        return cross(self.residual_dipole_body_a_m2, field_body)


class ADCSSystem:
    """Track the orbital nadir frame through limited reaction-wheel torque."""

    def __init__(
        self,
        max_substep_s: float = 0.1,
        disturbance_models: Iterable[DisturbanceTorqueModel] = (),
        random_seed: int = 0,
    ) -> None:
        _require_positive("max_substep_s", max_substep_s)
        self.max_substep_s = float(max_substep_s)
        self.disturbance_models = tuple(disturbance_models)
        self.random = Random(random_seed)

    def initialize(self, world: World, entity: Entity) -> None:
        """Initialize truth and reference attitude to the current nadir frame."""
        reference = self._reference(world, entity, None)
        stored_reference = world.get(entity, AttitudeReference)
        stored_reference.quaternion_xyzw = reference.quaternion_xyzw
        stored_reference.angular_velocity_eci_rad_s = (
            reference.angular_velocity_eci_rad_s
        )
        state = world.get(entity, AttitudeState)
        state.quaternion_xyzw = reference.quaternion_xyzw
        state.angular_velocity_body_rad_s = _eci_to_body(
            reference.angular_velocity_eci_rad_s, state.quaternion_xyzw
        )
        world.get(entity, SpacecraftAttitude).set_quaternion(state.quaternion_xyzw)
        if world.has(entity, AttitudeEstimate):
            estimate = world.get(entity, AttitudeEstimate)
            estimate.quaternion_xyzw = state.quaternion_xyzw
            estimate.angular_velocity_body_rad_s = state.angular_velocity_body_rad_s
        if world.has(entity, ADCSModeState):
            mode = world.get(entity, ADCSModeState)
            mode.inertial_hold_quaternion_xyzw = state.quaternion_xyzw

    def update(
        self,
        world: World,
        entity: Entity,
        delta_time: float,
        timestamp: datetime | None = None,
    ) -> ADCSStatus:
        """Advance controller, wheels, and rigid-body truth state."""
        _require_positive("delta_time", delta_time)
        self._update_mode_and_faults(world, entity)
        reference = self._reference(world, entity, timestamp)
        stored_reference = world.get(entity, AttitudeReference)
        stored_reference.quaternion_xyzw = reference.quaternion_xyzw
        stored_reference.angular_velocity_eci_rad_s = (
            reference.angular_velocity_eci_rad_s
        )
        steps = max(1, ceil(delta_time / self.max_substep_s))
        substep = delta_time / steps
        status = world.get(entity, ADCSStatus)
        for _ in range(steps):
            self._substep(world, entity, reference, status, substep, timestamp)
        state = world.get(entity, AttitudeState)
        world.get(entity, SpacecraftAttitude).set_quaternion(state.quaternion_xyzw)
        return status

    @staticmethod
    def _reference(
        world: World, entity: Entity, timestamp: datetime | None
    ) -> AttitudeReference:
        position = world.get(entity, ECIPosition)
        velocity = world.get(entity, ECIVelocity)
        position_vector = (position.x, position.y, position.z)
        velocity_vector = (velocity.x, velocity.y, velocity.z)
        axes = nadir_pointing_axes(position_vector, velocity_vector)
        radius_squared = dot(position_vector, position_vector)
        orbital_momentum = cross(position_vector, velocity_vector)
        orbital_rate = (
            orbital_momentum[0] / radius_squared,
            orbital_momentum[1] / radius_squared,
            orbital_momentum[2] / radius_squared,
        )
        if world.has(entity, ADCSModeState):
            mode = world.get(entity, ADCSModeState)
            if mode.current in (ADCSMode.INERTIAL_HOLD, ADCSMode.DETUMBLE):
                return AttitudeReference(
                    mode.inertial_hold_quaternion_xyzw, (0.0, 0.0, 0.0)
                )
            if mode.current in (ADCSMode.SUN_POINTING, ADCSMode.SAFE_MODE):
                if timestamp is None:
                    return AttitudeReference(
                        mode.inertial_hold_quaternion_xyzw, (0.0, 0.0, 0.0)
                    )
                z_axis = solar_direction_eci(timestamp)
                along_z = dot(velocity_vector, z_axis)
                projected_velocity: Vector3 = tuple(
                    velocity_vector[index] - along_z * z_axis[index]
                    for index in range(3)
                )  # type: ignore[assignment]
                x_axis = unit_vector(
                    "Sun-pointing projected velocity", projected_velocity
                )
                y_axis = cross(z_axis, x_axis)
                return AttitudeReference(
                    quaternion_from_axes(x_axis, y_axis, z_axis),
                    (0.0, 0.0, 0.0),
                )
        return AttitudeReference(
            quaternion_from_axes(*axes),
            orbital_rate,
        )

    def _substep(
        self,
        world: World,
        entity: Entity,
        reference: AttitudeReference,
        status: ADCSStatus,
        delta_time: float,
        timestamp: datetime | None,
    ) -> None:
        body = world.get(entity, RigidBody)
        state = world.get(entity, AttitudeState)
        controller = world.get(entity, AttitudeController)
        wheels = world.get(entity, ReactionWheelAssembly)
        position = world.get(entity, ECIPosition)
        velocity = world.get(entity, ECIVelocity)
        estimate = self._update_estimator(
            world, entity, state, position, timestamp, delta_time
        )
        control_quaternion = (
            estimate.quaternion_xyzw if estimate is not None else state.quaternion_xyzw
        )
        control_rate = (
            estimate.angular_velocity_body_rad_s
            if estimate is not None
            else state.angular_velocity_body_rad_s
        )
        mode = (
            world.get(entity, ADCSModeState).current
            if world.has(entity, ADCSModeState)
            else ADCSMode.NADIR_POINTING
        )
        error = quaternion_multiply(
            quaternion_conjugate(control_quaternion), reference.quaternion_xyzw
        )
        if error[3] < 0.0:
            error = tuple(-value for value in error)  # type: ignore[assignment]
        desired_rate = _eci_to_body(
            reference.angular_velocity_eci_rad_s, control_quaternion
        )
        commanded = tuple(
            2.0 * controller.proportional_gain_nm * error[index]
            + controller.derivative_gain_nms
            * (desired_rate[index] - control_rate[index])
            for index in range(3)
        )
        if mode == ADCSMode.DETUMBLE:
            commanded = (0.0, 0.0, 0.0)
        magnetic_torque = (0.0, 0.0, 0.0)
        if world.has(entity, MagnetorquerAssembly) and world.has(
            entity, MomentumManagementConfiguration
        ):
            magnetorquer = world.get(entity, MagnetorquerAssembly)
            management = world.get(entity, MomentumManagementConfiguration)
            field_body = _eci_to_body(
                earth_magnetic_field_eci(position), state.quaternion_xyzw
            )
            desired_magnetic_torque: Vector3 = (0.0, 0.0, 0.0)
            if mode == ADCSMode.DETUMBLE:
                desired_magnetic_torque = tuple(
                    -management.detumble_gain_nms * value for value in control_rate
                )  # type: ignore[assignment]
            else:
                unload = tuple(
                    max(
                        -wheels.max_torque_nm,
                        min(
                            wheels.max_torque_nm,
                            management.unload_gain_per_s
                            * wheels.rotor_inertia_kg_m2
                            * speed,
                        ),
                    )
                    if abs(speed) / wheels.max_speed_rad_s
                    >= management.unload_threshold_fraction
                    else 0.0
                    for speed in wheels.speeds_rad_s
                )
                commanded = tuple(
                    commanded[index] + unload[index] for index in range(3)
                )
                desired_magnetic_torque = tuple(-value for value in unload)  # type: ignore[assignment]
            magnetic_torque = apply_magnetorquer(
                magnetorquer, field_body, desired_magnetic_torque
            )
        applied, saturated = apply_reaction_wheels(wheels, commanded, delta_time)
        model_torques = tuple(
            model.torque_body_nm(body, state, position, velocity, timestamp)
            for model in self.disturbance_models
        )
        disturbance = tuple(
            sum(torque[index] for torque in model_torques) for index in range(3)
        )
        momentum = (
            body.inertia_kg_m2[0] * state.angular_velocity_body_rad_s[0],
            body.inertia_kg_m2[1] * state.angular_velocity_body_rad_s[1],
            body.inertia_kg_m2[2] * state.angular_velocity_body_rad_s[2],
        )
        gyroscopic = cross(state.angular_velocity_body_rad_s, momentum)
        acceleration = tuple(
            (
                applied[index]
                + magnetic_torque[index]
                + disturbance[index]
                - gyroscopic[index]
            )
            / body.inertia_kg_m2[index]
            for index in range(3)
        )
        state.angular_velocity_body_rad_s = tuple(
            state.angular_velocity_body_rad_s[index] + acceleration[index] * delta_time
            for index in range(3)
        )  # type: ignore[assignment]
        omega: Quaternion = (*state.angular_velocity_body_rad_s, 0.0)
        derivative = quaternion_multiply(state.quaternion_xyzw, omega)
        state.quaternion_xyzw = normalize_quaternion(
            tuple(
                state.quaternion_xyzw[index] + 0.5 * derivative[index] * delta_time
                for index in range(4)
            )  # type: ignore[arg-type]
        )
        status.pointing_error_deg = 2.0 * acos(min(1.0, abs(error[3]))) * 180.0 / pi
        status.commanded_torque_nm = commanded  # type: ignore[assignment]
        status.applied_torque_nm = applied
        status.disturbance_torque_nm = disturbance  # type: ignore[assignment]
        status.wheel_saturated = saturated

    @staticmethod
    def _update_mode_and_faults(world: World, entity: Entity) -> None:
        if not world.has(entity, ADCSModeState):
            return
        mode = world.get(entity, ADCSModeState)
        state = world.get(entity, AttitudeState)
        faults = (
            world.get(entity, ADCSFaultState)
            if world.has(entity, ADCSFaultState)
            else None
        )
        sensors = (
            world.get(entity, ADCSSensorConfiguration)
            if world.has(entity, ADCSSensorConfiguration)
            else None
        )
        sensor_fault = sensors is not None and (
            not sensors.gyro_valid
            or not any(
                (
                    sensors.sun_sensor_valid,
                    sensors.magnetometer_valid,
                    sensors.earth_sensor_valid,
                )
            )
        )
        wheels = world.get(entity, ReactionWheelAssembly)
        wheel_fault = any(
            abs(speed) > wheels.max_speed_rad_s for speed in wheels.speeds_rad_s
        )
        if faults is not None:
            faults.sensor_fault = sensor_fault
            faults.wheel_fault = wheel_fault
        requested = (
            ADCSMode.SAFE_MODE if sensor_fault or wheel_fault else mode.requested
        )
        if requested != mode.current:
            if requested in (ADCSMode.INERTIAL_HOLD, ADCSMode.DETUMBLE):
                mode.inertial_hold_quaternion_xyzw = state.quaternion_xyzw
            mode.current = requested
        if faults is not None:
            faults.safe_mode_reason = (
                "sensor fault"
                if sensor_fault
                else "reaction-wheel fault"
                if wheel_fault
                else None
            )

    def _update_estimator(
        self,
        world: World,
        entity: Entity,
        truth: AttitudeState,
        position: ECIPosition,
        timestamp: datetime | None,
        delta_time: float,
    ) -> AttitudeEstimate | None:
        required = (
            ADCSSensorConfiguration,
            ADCSSensorMeasurements,
            AttitudeEstimate,
            AttitudeEstimatorConfiguration,
        )
        if not all(world.has(entity, component) for component in required):
            return None
        sensors = world.get(entity, ADCSSensorConfiguration)
        measurements = world.get(entity, ADCSSensorMeasurements)
        estimate = world.get(entity, AttitudeEstimate)
        estimator = world.get(entity, AttitudeEstimatorConfiguration)
        if sensors.gyro_valid:
            sensors.gyro_bias_rad_s = tuple(
                sensors.gyro_bias_rad_s[index]
                + self.random.gauss(0.0, sensors.gyro_bias_drift_std_rad_s2)
                * delta_time
                for index in range(3)
            )  # type: ignore[assignment]
            measurements.angular_velocity_body_rad_s = tuple(
                truth.angular_velocity_body_rad_s[index]
                + sensors.gyro_bias_rad_s[index]
                + self.random.gauss(0.0, sensors.gyro_noise_std_rad_s)
                for index in range(3)
            )  # type: ignore[assignment]
        measurements.gyro_valid = sensors.gyro_valid

        position_vector = (position.x, position.y, position.z)
        radius = sqrt(dot(position_vector, position_vector))
        nadir_eci: Vector3 = tuple(-value / radius for value in position_vector)  # type: ignore[assignment]
        measurements.nadir_direction_body = (
            _noisy_unit_vector(
                _eci_to_body(nadir_eci, truth.quaternion_xyzw),
                sensors.vector_noise_std,
                self.random,
            )
            if sensors.earth_sensor_valid
            else None
        )
        measurements.earth_sensor_valid = measurements.nadir_direction_body is not None

        field_eci = earth_magnetic_field_eci(position)
        measurements.magnetic_field_body_t = (
            _noisy_vector(
                _eci_to_body(field_eci, truth.quaternion_xyzw),
                sensors.vector_noise_std * sqrt(dot(field_eci, field_eci)),
                self.random,
            )
            if sensors.magnetometer_valid
            else None
        )
        measurements.magnetometer_valid = measurements.magnetic_field_body_t is not None

        sun_eci = solar_direction_eci(timestamp) if timestamp is not None else None
        sun_available = (
            sensors.sun_sensor_valid
            and sun_eci is not None
            and satellite_is_sunlit(position_vector, timestamp)  # type: ignore[arg-type]
        )
        measurements.sun_direction_body = (
            _noisy_unit_vector(
                _eci_to_body(sun_eci, truth.quaternion_xyzw),  # type: ignore[arg-type]
                sensors.vector_noise_std,
                self.random,
            )
            if sun_available
            else None
        )
        measurements.sun_sensor_valid = measurements.sun_direction_body is not None

        rate = (
            measurements.angular_velocity_body_rad_s
            if measurements.gyro_valid
            else estimate.angular_velocity_body_rad_s
        )
        correction = [0.0, 0.0, 0.0]
        vector_pairs: list[tuple[Vector3, Vector3]] = []
        if measurements.nadir_direction_body is not None:
            vector_pairs.append((nadir_eci, measurements.nadir_direction_body))
        if measurements.magnetic_field_body_t is not None:
            field_magnitude = sqrt(dot(field_eci, field_eci))
            vector_pairs.append(
                (
                    tuple(value / field_magnitude for value in field_eci),  # type: ignore[arg-type]
                    tuple(
                        value
                        / sqrt(
                            dot(
                                measurements.magnetic_field_body_t,
                                measurements.magnetic_field_body_t,
                            )
                        )
                        for value in measurements.magnetic_field_body_t
                    ),
                )
            )
        if sun_eci is not None and measurements.sun_direction_body is not None:
            vector_pairs.append((sun_eci, measurements.sun_direction_body))
        for inertial, measured_body in vector_pairs:
            predicted_body = _eci_to_body(inertial, estimate.quaternion_xyzw)
            vector_error = cross(measured_body, predicted_body)
            for index in range(3):
                correction[index] += vector_error[index]
        if vector_pairs:
            correction = [value / len(vector_pairs) for value in correction]
        estimate.angular_velocity_body_rad_s = rate
        corrected_rate: Vector3 = tuple(
            rate[index] + estimator.correction_gain_rad_s * correction[index]
            for index in range(3)
        )  # type: ignore[assignment]
        omega: Quaternion = (*corrected_rate, 0.0)
        derivative = quaternion_multiply(estimate.quaternion_xyzw, omega)
        estimate.quaternion_xyzw = normalize_quaternion(
            tuple(
                estimate.quaternion_xyzw[index] + 0.5 * derivative[index] * delta_time
                for index in range(4)
            )  # type: ignore[arg-type]
        )
        return estimate


def apply_magnetorquer(
    magnetorquer: MagnetorquerAssembly,
    magnetic_field_body_t: Vector3,
    desired_torque_nm: Vector3,
) -> Vector3:
    """Command the limited dipole that best realizes torque perpendicular to B."""
    field_squared = dot(magnetic_field_body_t, magnetic_field_body_t)
    if field_squared == 0.0:
        magnetorquer.commanded_dipole_a_m2 = (0.0, 0.0, 0.0)
        magnetorquer.applied_torque_nm = (0.0, 0.0, 0.0)
        return magnetorquer.applied_torque_nm
    commanded = tuple(
        value / field_squared
        for value in cross(magnetic_field_body_t, desired_torque_nm)
    )
    magnetorquer.commanded_dipole_a_m2 = commanded  # type: ignore[assignment]
    limited: Vector3 = tuple(
        max(-magnetorquer.max_dipole_a_m2, min(magnetorquer.max_dipole_a_m2, value))
        for value in commanded
    )  # type: ignore[assignment]
    magnetorquer.applied_torque_nm = cross(limited, magnetic_field_body_t)
    return magnetorquer.applied_torque_nm


def apply_reaction_wheels(
    wheels: ReactionWheelAssembly,
    commanded: tuple[float, ...],
    delta_time: float,
) -> tuple[Vector3, tuple[bool, bool, bool]]:
    """Apply torque and momentum limits, returning spacecraft torque."""
    applied: list[float] = []
    speeds: list[float] = []
    saturated: list[bool] = []
    for torque, speed in zip(commanded, wheels.speeds_rad_s, strict=True):
        limited = max(-wheels.max_torque_nm, min(wheels.max_torque_nm, torque))
        next_speed = speed - limited * delta_time / wheels.rotor_inertia_kg_m2
        if abs(next_speed) > wheels.max_speed_rad_s:
            next_speed = max(
                -wheels.max_speed_rad_s, min(wheels.max_speed_rad_s, next_speed)
            )
            limited = (speed - next_speed) * wheels.rotor_inertia_kg_m2 / delta_time
        applied.append(limited)
        speeds.append(next_speed)
        saturated.append(abs(limited - torque) > 1e-12)
    wheels.speeds_rad_s = tuple(speeds)  # type: ignore[assignment]
    return tuple(applied), tuple(saturated)  # type: ignore[return-value]


def _eci_to_body(vector_eci: Vector3, quaternion_xyzw: Quaternion) -> Vector3:
    axes = quaternion_to_axes(quaternion_xyzw)
    return tuple(dot(vector_eci, axis) for axis in axes)  # type: ignore[return-value]


def _noisy_vector(vector: Vector3, noise_std: float, random: Random) -> Vector3:
    return tuple(value + random.gauss(0.0, noise_std) for value in vector)  # type: ignore[return-value]


def _noisy_unit_vector(vector: Vector3, noise_std: float, random: Random) -> Vector3:
    noisy = _noisy_vector(vector, noise_std, random)
    magnitude = sqrt(dot(noisy, noisy))
    if magnitude == 0.0:
        return vector
    return tuple(value / magnitude for value in noisy)  # type: ignore[return-value]


def _require_vector(name: str, values: Vector3, *, positive: bool = False) -> None:
    if len(values) != 3 or not all(isfinite(value) for value in values):
        raise ValueError(f"{name} must contain three finite values")
    if positive and any(value <= 0.0 for value in values):
        raise ValueError(f"{name} values must be greater than zero")


def _require_nonnegative(name: str, value: float) -> None:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative")


def _require_positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and greater than zero")
