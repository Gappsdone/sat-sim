import pytest

from sat_sim.services.tcs import Heater, ThermalControlSystem


def test_default_system_has_nine_paired_sensors_and_heaters() -> None:
    tcs = ThermalControlSystem()

    assert len(tcs.sensors) == 9
    assert len(tcs.heaters) == 9
    assert all(sensor.temperature_celsius == 0.0 for sensor in tcs.sensors)
    assert all(not heater.active for heater in tcs.heaters)


def test_configurable_channel_count_and_initial_temperature() -> None:
    tcs = ThermalControlSystem(
        sensor_count=3,
        initial_temperature=20.0,
        wattages=[5.0, 10.0, 15.0],
    )

    assert len(tcs.sensors) == 3
    assert len(tcs.heaters) == 3
    assert [sensor.temperature_celsius for sensor in tcs.sensors] == [20.0] * 3
    assert [heater.wattage for heater in tcs.heaters] == [5.0, 10.0, 15.0]


def test_active_heater_increases_only_its_paired_sensor() -> None:
    tcs = ThermalControlSystem(sensor_count=3, wattages=[5.0, 10.0, 20.0])
    tcs.activate_heater(1)

    tcs.step(2.0)

    assert [sensor.temperature_celsius for sensor in tcs.sensors] == [0.0, 20.0, 0.0]


def test_heater_can_be_activated_and_deactivated() -> None:
    heater = Heater(10.0)

    heater.activate()
    assert heater.active

    heater.deactivate()
    assert not heater.active


def test_custom_heating_rate_scales_temperature_increase() -> None:
    tcs = ThermalControlSystem(sensor_count=1, wattages=[4.0], heating_rate=0.5)
    tcs.activate_heater(0)

    tcs.step(3.0)

    assert tcs.sensors[0].temperature_celsius == 6.0


def test_invalid_configuration_and_time_are_rejected() -> None:
    with pytest.raises(ValueError, match="sensor_count"):
        ThermalControlSystem(sensor_count=0)
    with pytest.raises(ValueError, match="one value per sensor"):
        ThermalControlSystem(sensor_count=2, wattages=[1.0])
    with pytest.raises(ValueError, match="wattage"):
        Heater(-1.0)
    with pytest.raises(ValueError, match="heating_rate"):
        ThermalControlSystem(heating_rate=-1.0)

    tcs = ThermalControlSystem()
    with pytest.raises(ValueError, match="delta_time"):
        tcs.step(-1.0)


def test_invalid_heater_index_uses_standard_index_error() -> None:
    tcs = ThermalControlSystem(sensor_count=2)

    with pytest.raises(IndexError):
        tcs.activate_heater(2)
    with pytest.raises(IndexError):
        tcs.deactivate_heater(-3)
