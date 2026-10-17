"""Create immutable telemetry snapshots from an ISS ECS scenario."""

from math import sqrt

from sat_sim.attitude import SpacecraftAttitude
from sat_sim.scenarios.iss_scenario import ISSScenario, ISSScenarioState
from sat_sim.services.tcs import Heater, HeaterCommand, TemperatureSensor
from sat_sim_telemetry.models import (
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
    attitude = scenario.world.get(scenario.entity, SpacecraftAttitude)
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
        attitude=AttitudeTelemetry(value=_attitude_quaternion(attitude)),
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


def _attitude_quaternion(
    attitude: SpacecraftAttitude,
) -> tuple[float, float, float, float]:
    """Convert body-axis columns of a body-to-ECI matrix to [x, y, z, w]."""
    matrix = (
        (attitude.x_axis_eci[0], attitude.y_axis_eci[0], attitude.z_axis_eci[0]),
        (attitude.x_axis_eci[1], attitude.y_axis_eci[1], attitude.z_axis_eci[1]),
        (attitude.x_axis_eci[2], attitude.y_axis_eci[2], attitude.z_axis_eci[2]),
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
        quaternion = _quaternion_for_nonpositive_trace(matrix)
    length = sqrt(sum(component * component for component in quaternion))
    return tuple(component / length for component in quaternion)  # type: ignore[return-value]


def _quaternion_for_nonpositive_trace(
    matrix: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ],
) -> tuple[float, float, float, float]:
    diagonal = (matrix[0][0], matrix[1][1], matrix[2][2])
    index = diagonal.index(max(diagonal))
    if index == 0:
        scale = sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
        return (
            0.25 * scale,
            (matrix[0][1] + matrix[1][0]) / scale,
            (matrix[0][2] + matrix[2][0]) / scale,
            (matrix[2][1] - matrix[1][2]) / scale,
        )
    if index == 1:
        scale = sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
        return (
            (matrix[0][1] + matrix[1][0]) / scale,
            0.25 * scale,
            (matrix[1][2] + matrix[2][1]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
        )
    scale = sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
    return (
        (matrix[0][2] + matrix[2][0]) / scale,
        (matrix[1][2] + matrix[2][1]) / scale,
        0.25 * scale,
        (matrix[1][0] - matrix[0][1]) / scale,
    )
