import pytest

from sat_sim.position import (
    WGS84_ECCENTRICITY_SQUARED,
    WGS84_SEMI_MAJOR_AXIS,
    from_lat_lon_alt,
)


def test_origin_maps_to_semi_major_axis_on_x() -> None:
    position = from_lat_lon_alt(0.0, 0.0, 0.0)

    assert position.x == pytest.approx(WGS84_SEMI_MAJOR_AXIS)
    assert position.y == pytest.approx(0.0)
    assert position.z == pytest.approx(0.0)


def test_pole_maps_to_polar_radius_on_z() -> None:
    position = from_lat_lon_alt(90.0, 0.0, 0.0)

    polar_radius = WGS84_SEMI_MAJOR_AXIS * (1 - WGS84_ECCENTRICITY_SQUARED) ** 0.5
    assert position.x == pytest.approx(0.0, abs=1e-6)
    assert position.y == pytest.approx(0.0, abs=1e-6)
    assert position.z == pytest.approx(polar_radius)


def test_altitude_extends_radius_above_equator() -> None:
    position = from_lat_lon_alt(0.0, 0.0, 100.0)

    assert position.x == pytest.approx(WGS84_SEMI_MAJOR_AXIS + 100.0)
    assert position.y == pytest.approx(0.0)
    assert position.z == pytest.approx(0.0)
