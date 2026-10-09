from datetime import UTC, datetime
from math import isclose, log1p

import pytest

from sat_sim.ecs import World
from sat_sim.position import ECIPosition
from sat_sim.services.tcs import (
    EARTH_RADIUS_METERS,
    Heater,
    HeaterCommand,
    IlluminationState,
    PIDController,
    PIDState,
    TemperatureSensor,
    ThermalControlSystem,
    satellite_is_sunlit,
    solar_direction_eci,
)

REFERENCE_TIME = datetime(2000, 1, 1, 12, tzinfo=UTC)


def make_tcs(**kwargs: object) -> ThermalControlSystem:
    """Build a heater-focused TCS with environmental/threshold effects disabled."""
    kwargs.setdefault("heater_threshold_celsius", None)
    kwargs.setdefault("sunlit_warming_rate_celsius_per_second", 0.0)
    kwargs.setdefault("eclipse_cooling_rate_celsius_per_second", 0.0)
    return ThermalControlSystem(**kwargs)  # type: ignore[arg-type]


def advance(
    tcs: ThermalControlSystem,
    delta_time: float,
    position: tuple[float, float, float] | None = None,
) -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    satellite_position = position or (
        sun[0] * 7_000_000.0,
        sun[1] * 7_000_000.0,
        sun[2] * 7_000_000.0,
    )
    tcs.step(delta_time, satellite_position, REFERENCE_TIME)


def test_default_system_pairs_nine_channels_in_row_major_three_by_three_grid() -> None:
    tcs = make_tcs()

    assert len(tcs.sensors) == len(tcs.heaters) == 9
    assert [sensor.id for sensor in tcs.sensors] == list(range(9))
    assert [heater.id for heater in tcs.heaters] == list(range(9))
    assert [heater.sensor_id for heater in tcs.heaters] == list(range(9))
    assert [sensor.position for sensor in tcs.sensors] == [
        (0.0, 0.0),
        (1.0, 0.0),
        (2.0, 0.0),
        (0.0, 1.0),
        (1.0, 1.0),
        (2.0, 1.0),
        (0.0, 2.0),
        (1.0, 2.0),
        (2.0, 2.0),
    ]
    assert [heater.position for heater in tcs.heaters] == [
        sensor.position for sensor in tcs.sensors
    ]
    assert all(sensor.temperature_celsius == 0.0 for sensor in tcs.sensors)
    assert all(not heater.active for heater in tcs.heaters)


def test_configurable_channels_use_first_cells_and_pair_each_heater() -> None:
    tcs = make_tcs(
        sensor_count=3,
        initial_temperature=20.0,
        wattages=[5.0, 10.0, 15.0],
    )

    assert [sensor.position for sensor in tcs.sensors] == [
        (0.0, 0.0),
        (1.0, 0.0),
        (2.0, 0.0),
    ]
    assert [sensor.temperature_celsius for sensor in tcs.sensors] == [20.0] * 3
    assert [heater.power for heater in tcs.heaters] == [5.0, 10.0, 15.0]


def test_thermal_channel_state_is_stored_as_ecs_components() -> None:
    tcs = make_tcs(sensor_count=2)

    channels = list(tcs.world.query(TemperatureSensor, Heater, HeaterCommand, PIDState))
    assert len(channels) == 2
    assert [entity for entity, *_components in channels] == tcs.thermal_entities
    assert tcs.spacecraft_entity is not None
    assert tcs.world.has(tcs.spacecraft_entity, IlluminationState)
    assert tcs.world.has(tcs.spacecraft_entity, ECIPosition)


def test_tcs_can_bind_to_scenario_world_and_spacecraft_entity() -> None:
    world = World()
    spacecraft = world.create()
    world.add(spacecraft, ECIPosition(7_000_000.0, 0.0, 0.0))
    tcs = make_tcs(sensor_count=1)
    tcs.bind_world(world)
    tcs.bind_spacecraft_entity(spacecraft)

    assert tcs.world is world
    assert tcs.thermal_entities[0] != spacecraft
    assert world.has(tcs.thermal_entities[0], TemperatureSensor)
    assert world.has(spacecraft, IlluminationState)


def test_setpoint_pid_modulates_heater_and_stops_at_setpoint() -> None:
    tcs = make_tcs(sensor_count=1, wattages=[10.0], kp=0.1)
    tcs.set_setpoint(0, 5.0)

    advance(tcs, 1.0)
    assert tcs.sensors[0].temperature_celsius == 5.0
    assert tcs.heaters[0].output_fraction == 0.5

    advance(tcs, 1.0)
    assert tcs.sensors[0].temperature_celsius == 5.0
    assert tcs.heaters[0].output_fraction == 0.0
    assert not tcs.heaters[0].active


def test_pid_integral_and_derivative_terms_affect_bounded_output() -> None:
    pid = PIDController(kp=0.05, ki=0.01, kd=0.1)

    first = pid.update(10.0, 0.0, 1.0)
    second = pid.update(10.0, 1.0, 1.0)

    assert first == pytest.approx(0.6)
    assert 0.0 <= second < first


def test_manual_activation_runs_full_power_and_deactivation_resets_control() -> None:
    heater = Heater(0, 10.0)
    heater.activate()
    assert heater.active

    tcs = make_tcs(sensor_count=1, wattages=[10.0], heater_threshold_celsius=10.0)
    tcs.activate_heater(0)
    advance(tcs, 2.0)
    assert tcs.sensors[0].temperature_celsius == 20.0

    tcs.set_setpoint(0, 100.0)
    tcs.deactivate_heater(0)
    assert not tcs.heaters[0].active
    assert tcs.heaters[0].setpoint_celsius is None
    advance(tcs, 1.0)
    assert not tcs.heaters[0].active
    assert tcs.heaters[0].output_fraction == 0.0
    tcs.sensors[0].temperature_celsius = 5.0
    tcs.enable_automatic_control(0)
    advance(tcs, 1.0)
    assert tcs.heaters[0].active


def test_heater_heat_attenuates_logarithmically_with_grid_distance() -> None:
    tcs = make_tcs(sensor_count=9, wattages=[1.0] + [0.0] * 8)
    tcs.activate_heater(0)

    advance(tcs, 1.0)

    expected_neighbor = 1.0 / (1.0 + log1p(1.0))
    expected_two_meters = 1.0 / (1.0 + log1p(2.0))
    assert tcs.sensors[0].temperature_celsius == 1.0
    assert isclose(tcs.sensors[1].temperature_celsius, expected_neighbor)
    assert isclose(tcs.sensors[2].temperature_celsius, expected_two_meters)
    assert (
        tcs.sensors[0].temperature_celsius
        > tcs.sensors[1].temperature_celsius
        > tcs.sensors[2].temperature_celsius
    )


def test_heaters_contribute_independently_to_all_sensors() -> None:
    tcs = make_tcs(sensor_count=2, wattages=[1.0, 1.0])
    tcs.activate_heater(0)
    tcs.activate_heater(1)

    advance(tcs, 1.0)

    adjacent_attenuation = 1.0 / (1.0 + log1p(1.0))
    assert isclose(tcs.sensors[0].temperature_celsius, 1.0 + adjacent_attenuation)
    assert isclose(tcs.sensors[1].temperature_celsius, 1.0 + adjacent_attenuation)


def test_custom_spacing_and_heating_rate_scale_heat_transfer() -> None:
    tcs = make_tcs(
        sensor_count=2,
        wattages=[4.0, 0.0],
        heating_rate=0.5,
        grid_spacing_m=2.0,
    )
    tcs.activate_heater(0)

    advance(tcs, 3.0)

    assert tcs.sensors[0].temperature_celsius == 6.0
    assert isclose(tcs.sensors[1].temperature_celsius, 6.0 / (1.0 + log1p(2.0)))


def test_sunlight_warms_all_sensors_and_tracks_satellite_position() -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    position = (
        sun[0] * 7_000_000.0,
        sun[1] * 7_000_000.0,
        sun[2] * 7_000_000.0,
    )
    tcs = ThermalControlSystem(
        sensor_count=2,
        wattages=[0.0, 0.0],
        heater_threshold_celsius=None,
        sunlit_warming_rate_celsius_per_second=0.2,
        eclipse_cooling_rate_celsius_per_second=0.1,
    )

    tcs.step(5.0, position, REFERENCE_TIME)

    assert tcs.is_sunlit is True
    assert tcs.satellite_position_m == position
    assert [sensor.temperature_celsius for sensor in tcs.sensors] == [1.0, 1.0]


def test_earth_shadow_cools_all_sensors_without_heaters() -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    radius = EARTH_RADIUS_METERS + 300_000.0
    position = (-sun[0] * radius, -sun[1] * radius, -sun[2] * radius)
    tcs = ThermalControlSystem(
        sensor_count=2,
        initial_temperature=10.0,
        wattages=[0.0, 0.0],
        heater_threshold_celsius=None,
        sunlit_warming_rate_celsius_per_second=0.2,
        eclipse_cooling_rate_celsius_per_second=0.1,
    )

    tcs.step(5.0, position, REFERENCE_TIME)

    assert tcs.is_sunlit is False
    assert [sensor.temperature_celsius for sensor in tcs.sensors] == [9.5, 9.5]


def test_solar_geometry_uses_cylindrical_earth_shadow() -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    sunward_position = (
        sun[0] * 7_000_000.0,
        sun[1] * 7_000_000.0,
        sun[2] * 7_000_000.0,
    )
    anti_sun_position = (
        -sun[0] * 7_000_000.0,
        -sun[1] * 7_000_000.0,
        -sun[2] * 7_000_000.0,
    )
    perpendicular = (-sun[1], sun[0], 0.0)
    perpendicular_length = sum(component**2 for component in perpendicular) ** 0.5
    perpendicular = (
        perpendicular[0] / perpendicular_length,
        perpendicular[1] / perpendicular_length,
        perpendicular[2] / perpendicular_length,
    )
    offset = EARTH_RADIUS_METERS + 10_000.0
    outside_shadow = (
        -sun[0] * 7_000_000.0 + offset * perpendicular[0],
        -sun[1] * 7_000_000.0 + offset * perpendicular[1],
        -sun[2] * 7_000_000.0 + offset * perpendicular[2],
    )

    assert satellite_is_sunlit(sunward_position, REFERENCE_TIME)
    assert not satellite_is_sunlit(anti_sun_position, REFERENCE_TIME)
    assert satellite_is_sunlit(outside_shadow, REFERENCE_TIME)


def test_below_threshold_auto_activates_paired_heater_but_warm_sensor_does_not() -> (
    None
):
    tcs = ThermalControlSystem(
        sensor_count=2,
        initial_temperature=5.0,
        wattages=[10.0, 10.0],
        heater_threshold_celsius=10.0,
        kp=0.1,
        heating_rate=0.1,
        sunlit_warming_rate_celsius_per_second=0.0,
        eclipse_cooling_rate_celsius_per_second=0.0,
    )
    tcs.sensors[1].temperature_celsius = 12.0

    advance(tcs, 1.0)

    assert tcs.heaters[0].active
    assert tcs.heaters[0].output_fraction == 0.5
    assert not tcs.heaters[1].active
    assert tcs.heaters[1].output_fraction == 0.0
    assert tcs.sensors[0].temperature_celsius > 5.0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"sensor_count": 0}, "sensor_count"),
        ({"sensor_count": 10}, "sensor_count"),
        ({"sensor_count": 2, "wattages": [1.0]}, "one value per sensor"),
        ({"sensor_count": 1, "wattages": [float("nan")]}, "finite"),
        ({"sensor_count": 1, "wattages": [-1.0]}, "wattage"),
        ({"heating_rate": -1.0}, "heating_rate"),
        ({"grid_spacing_m": 0.0}, "grid_spacing_m"),
        ({"kp": float("inf")}, "finite"),
    ],
)
def test_invalid_configuration_is_rejected(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ThermalControlSystem(**kwargs)  # type: ignore[arg-type]


def test_invalid_heater_and_pid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="wattage"):
        Heater(0, -1.0)
    with pytest.raises(ValueError, match="finite"):
        Heater(0, float("inf"))
    with pytest.raises(ValueError, match="output limits"):
        PIDController(output_min=1.0, output_max=1.0)
    with pytest.raises(ValueError, match="must not be negative"):
        ThermalControlSystem(sunlit_warming_rate_celsius_per_second=-1.0)


def test_invalid_time_position_and_timezone_are_rejected() -> None:
    tcs = make_tcs()
    for delta_time in (0.0, -1.0, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="delta_time"):
            tcs.step(delta_time, (7_000_000.0, 0.0, 0.0), REFERENCE_TIME)
    with pytest.raises(ValueError, match="finite"):
        tcs.set_setpoint(0, float("nan"))
    with pytest.raises(ValueError, match="three finite coordinates"):
        tcs.step(1.0, (float("nan"), 0.0, 0.0), REFERENCE_TIME)
    with pytest.raises(ValueError, match="timezone-aware"):
        solar_direction_eci(datetime(2000, 1, 1, 12))


def test_invalid_heater_index_uses_standard_index_error() -> None:
    tcs = make_tcs(sensor_count=2)

    with pytest.raises(IndexError):
        tcs.activate_heater(2)
    with pytest.raises(IndexError):
        tcs.deactivate_heater(-3)
