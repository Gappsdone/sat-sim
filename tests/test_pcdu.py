from datetime import UTC, datetime

import pytest

from sat_sim.attitude import SpacecraftAttitude
from sat_sim.ecs import World
from sat_sim.pcdu import PCDU, PCDUSystem, PowerConsumer, SolarPanel
from sat_sim.position import ECIPosition
from sat_sim.solar import solar_direction_eci

REFERENCE_TIME = datetime(2000, 1, 1, 12, tzinfo=UTC)


def make_power_world(
    panel_normal: tuple[float, float, float],
    *,
    position_sign: float = 1.0,
    charge_wh: float = 50.0,
) -> tuple[World, int, PCDU]:
    world = World()
    spacecraft = world.create()
    sun = solar_direction_eci(REFERENCE_TIME)
    world.add(
        spacecraft,
        ECIPosition(*(position_sign * 7_000_000.0 * value for value in sun)),
    )
    world.add(spacecraft, SpacecraftAttitude(auto_orient=False))
    pcdu = world.add(spacecraft, PCDU(100.0, charge_wh))
    world.add(spacecraft, SolarPanel(100.0, panel_normal))
    return world, spacecraft, pcdu


def test_sun_facing_panel_charges_battery_at_peak_rate() -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    world, spacecraft, pcdu = make_power_world(sun)
    PCDUSystem.update(world, spacecraft, 360.0, REFERENCE_TIME)
    assert pcdu.is_sunlit is True
    assert pcdu.generated_power_w == pytest.approx(100.0)
    assert pcdu.charge_wh == pytest.approx(60.0)


def test_zero_duration_update_initializes_power_without_charging() -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    world, spacecraft, pcdu = make_power_world(sun)
    load_entity = world.create()
    world.add(load_entity, PowerConsumer(25.0))

    PCDUSystem.update(world, spacecraft, 0.0, REFERENCE_TIME)

    assert pcdu.is_sunlit is True
    assert pcdu.generated_power_w == pytest.approx(100.0)
    assert pcdu.consumed_power_w == 25.0
    assert pcdu.charge_wh == 50.0


def test_panel_angle_scales_charging_and_back_face_produces_nothing() -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    perpendicular_length = (sun[0] ** 2 + sun[1] ** 2) ** 0.5
    perpendicular = (
        -sun[1] / perpendicular_length,
        sun[0] / perpendicular_length,
        0.0,
    )
    angled = (
        (sun[0] + perpendicular[0]) / 2**0.5,
        (sun[1] + perpendicular[1]) / 2**0.5,
        (sun[2] + perpendicular[2]) / 2**0.5,
    )
    world, spacecraft, pcdu = make_power_world(angled)
    PCDUSystem.update(world, spacecraft, 360.0, REFERENCE_TIME)
    assert pcdu.generated_power_w == pytest.approx(100.0 / 2**0.5)

    world.get(spacecraft, SolarPanel).normal_body = (-sun[0], -sun[1], -sun[2])
    PCDUSystem.update(world, spacecraft, 1.0, REFERENCE_TIME)
    assert pcdu.generated_power_w == 0.0


def test_eclipse_stops_generation_and_consumers_discharge_battery() -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    world, spacecraft, pcdu = make_power_world(sun, position_sign=-1.0)
    load_entity = world.create()
    world.add(load_entity, PowerConsumer(25.0))
    PCDUSystem.update(world, spacecraft, 720.0, REFERENCE_TIME)
    assert pcdu.is_sunlit is False
    assert pcdu.generated_power_w == 0.0
    assert pcdu.consumed_power_w == 25.0
    assert pcdu.charge_wh == pytest.approx(45.0)


def test_pcdu_clamps_charge_to_battery_bounds() -> None:
    sun = solar_direction_eci(REFERENCE_TIME)
    world, spacecraft, pcdu = make_power_world(sun, charge_wh=99.0)
    PCDUSystem.update(world, spacecraft, 3600.0, REFERENCE_TIME)
    assert pcdu.charge_wh == 100.0

    position = world.get(spacecraft, ECIPosition)
    position.x, position.y, position.z = -position.x, -position.y, -position.z
    load_entity = world.create()
    world.add(load_entity, PowerConsumer(1_000.0))
    PCDUSystem.update(world, spacecraft, 3600.0, REFERENCE_TIME)
    assert pcdu.charge_wh == 0.0


def test_invalid_configuration_and_runtime_load_are_rejected() -> None:
    with pytest.raises(ValueError, match="capacity_wh"):
        PCDU(0.0, 0.0)
    with pytest.raises(ValueError, match="exceed"):
        PCDU(10.0, 11.0)
    with pytest.raises(ValueError, match="peak_power_w"):
        SolarPanel(-1.0)
    with pytest.raises(ValueError, match="normal_body"):
        SolarPanel(1.0, (0.0, 0.0, 0.0))

    sun = solar_direction_eci(REFERENCE_TIME)
    world, spacecraft, _pcdu = make_power_world(sun)
    load_entity = world.create()
    world.add(load_entity, PowerConsumer(-1.0))
    with pytest.raises(ValueError, match="requested_power_w"):
        PCDUSystem.update(world, spacecraft, 1.0, REFERENCE_TIME)
