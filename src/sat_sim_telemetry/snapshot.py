"""Create immutable telemetry snapshots from an ISS ECS scenario."""

from sat_sim.adcs import (
    ADCSSensorMeasurements,
    ADCSStatus,
    AttitudeEstimate,
    AttitudeReference,
    AttitudeState,
    ReactionWheelAssembly,
)
from sat_sim.scenarios.iss_scenario import ISSScenario, ISSScenarioState
from sat_sim.services.tcs import Heater, HeaterCommand, TemperatureSensor
from sat_sim_telemetry.models import (
    ADCSTelemetry,
    AttitudeTelemetry,
    EntityTelemetry,
    IlluminationTelemetry,
    PowerTelemetry,
    ScenarioDescription,
    TelemetryFrame,
    ThermalChannelDescription,
    ThermalChannelTelemetry,
    Vector3,
)


def snapshot_iss(
    scenario: ISSScenario, state: ISSScenarioState, sequence: int
) -> TelemetryFrame:
    """Capture all frontend-facing dynamic ISS state after a simulation step."""
    if scenario.entity is None:
        raise RuntimeError("ISS scenario must be set up before snapshotting")
    attitude = scenario.world.get(scenario.entity, AttitudeState)
    reference = scenario.world.get(scenario.entity, AttitudeReference)
    adcs_status = scenario.world.get(scenario.entity, ADCSStatus)
    wheels = scenario.world.get(scenario.entity, ReactionWheelAssembly)
    estimate = scenario.world.get(scenario.entity, AttitudeEstimate)
    sensors = scenario.world.get(scenario.entity, ADCSSensorMeasurements)
    illumination = scenario.tcs.illumination_state
    channels = tuple(
        ThermalChannelTelemetry(
            id=sensor.id,
            temperature_c=sensor.temperature_celsius,
            heater_output=command.output_fraction,
            heater_power_w=heater.power * command.output_fraction,
            heater_rated_power_w=heater.power,
            setpoint_c=(
                command.setpoint_celsius
                if command.setpoint_celsius is not None
                else scenario.tcs.heater_threshold_celsius
            ),
        )
        for _entity, sensor, heater, command in scenario.world.query(
            TemperatureSensor, Heater, HeaterCommand
        )
    )
    entity = EntityTelemetry(
        position=Vector3(
            frame="ECI",
            unit="m",
            value=(state.position.x, state.position.y, state.position.z),
        ),
        velocity=Vector3(
            frame="ECI",
            unit="m/s",
            value=(state.velocity.x, state.velocity.y, state.velocity.z),
        ),
        attitude=AttitudeTelemetry(value=attitude.quaternion_xyzw),
        adcs=ADCSTelemetry(
            angular_velocity_body_rad_s=attitude.angular_velocity_body_rad_s,
            pointing_error_deg=adcs_status.pointing_error_deg,
            target_quaternion_xyzw=reference.quaternion_xyzw,
            commanded_torque_nm=adcs_status.commanded_torque_nm,
            applied_torque_nm=adcs_status.applied_torque_nm,
            disturbance_torque_nm=adcs_status.disturbance_torque_nm,
            wheel_speeds_rad_s=wheels.speeds_rad_s,
            wheel_saturated=adcs_status.wheel_saturated,
            estimated_quaternion_xyzw=estimate.quaternion_xyzw,
            measured_angular_velocity_body_rad_s=(sensors.angular_velocity_body_rad_s),
            sensor_valid={
                "gyro": sensors.gyro_valid,
                "sun": sensors.sun_sensor_valid,
                "magnetometer": sensors.magnetometer_valid,
                "earth": sensors.earth_sensor_valid,
            },
        ),
        illumination=IlluminationTelemetry(
            sunlit=state.is_sunlit,
            sun_direction_eci=illumination.sun_direction_eci,
        ),
        power=PowerTelemetry(
            battery_charge_wh=state.battery_charge_wh,
            battery_capacity_wh=scenario.pcdu.capacity_wh,
            state_of_charge=scenario.pcdu.state_of_charge,
            generated_power_w=state.generated_power_w,
            consumed_power_w=state.consumed_power_w,
        ),
        thermal_channels=channels,
    )
    return TelemetryFrame(
        sequence=sequence,
        time=state.timestamp,
        entities={"iss": entity},
    )


def describe_iss_scenario(scenario: ISSScenario) -> ScenarioDescription:
    """Describe static ISS geometry, units, and component capacities."""
    channels = tuple(
        ThermalChannelDescription(
            id=sensor.id,
            position_m=sensor.position,
            sensor_normal_body=sensor.normal_body,
            heater_rated_power_w=heater.power,
        )
        for _entity, sensor, heater in scenario.world.query(TemperatureSensor, Heater)
    )
    return ScenarioDescription(
        scenario="ISS",
        entities=("iss",),
        battery_capacity_wh=scenario.pcdu.capacity_wh,
        solar_panel_peak_power_w=scenario.solar_panel.peak_power_w,
        solar_panel_normal_body=scenario.solar_panel.normal_body,
        thermal_channels=channels,
    )
