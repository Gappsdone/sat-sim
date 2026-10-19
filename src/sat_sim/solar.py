"""Approximate solar direction and Earth eclipse calculations."""

from datetime import UTC, datetime
from math import cos, isfinite, radians, sin, sqrt

from sat_sim.constants import EARTH_MEAN_RADIUS_METERS


def solar_direction_eci(timestamp: datetime) -> tuple[float, float, float]:
    """Approximate the Sun's unit direction in the ECI frame for a UTC time."""
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    utc_time = timestamp.astimezone(UTC)
    days_since_j2000 = (
        utc_time - datetime(2000, 1, 1, 12, tzinfo=UTC)
    ).total_seconds() / 86_400.0
    mean_longitude = radians((280.460 + 0.9856474 * days_since_j2000) % 360.0)
    mean_anomaly = radians((357.528 + 0.9856003 * days_since_j2000) % 360.0)
    ecliptic_longitude = (
        mean_longitude
        + radians(1.915) * sin(mean_anomaly)
        + radians(0.020) * sin(2.0 * mean_anomaly)
    )
    obliquity = radians(23.439 - 0.0000004 * days_since_j2000)
    return (
        cos(ecliptic_longitude),
        cos(obliquity) * sin(ecliptic_longitude),
        sin(obliquity) * sin(ecliptic_longitude),
    )


def satellite_is_sunlit(
    satellite_position_m: tuple[float, float, float], timestamp: datetime
) -> bool:
    """Return false only when Earth blocks the Sun (cylindrical umbra model)."""
    if len(satellite_position_m) != 3 or not all(
        isfinite(coordinate) for coordinate in satellite_position_m
    ):
        raise ValueError("satellite_position_m must contain three finite coordinates")
    sun_direction = solar_direction_eci(timestamp)
    along_sun = sum(
        coordinate * direction
        for coordinate, direction in zip(
            satellite_position_m, sun_direction, strict=True
        )
    )
    if along_sun >= 0.0:
        return True
    distance_from_shadow_axis = sqrt(
        max(
            0.0,
            sum(coordinate * coordinate for coordinate in satellite_position_m)
            - along_sun * along_sun,
        )
    )
    return distance_from_shadow_axis >= EARTH_MEAN_RADIUS_METERS
