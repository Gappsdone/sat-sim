import math
from dataclasses import dataclass

# WGS84 ellipsoid constants
a = 6378137.0  # semi-major axis in meters
e2 = 6.69437999014e-3  # square of eccentricity


@dataclass(slots=True)
class Position:
    """Earth-Centered, Earth-Fixed (ECEF) Cartesian position in meters."""

    x: float
    y: float
    z: float


def from_lat_lon_alt(latitude: float, longitude: float, altitude: float) -> Position:
    """Convert latitude, longitude, and altitude to ECEF Cartesian coordinates."""

    lat_rad = math.radians(latitude)
    lon_rad = math.radians(longitude)

    N = a / math.sqrt(1 - e2 * (math.sin(lat_rad) ** 2))

    x = (N + altitude) * math.cos(lat_rad) * math.cos(lon_rad)
    y = (N + altitude) * math.cos(lat_rad) * math.sin(lon_rad)
    z = ((1 - e2) * N + altitude) * math.sin(lat_rad)

    return Position(x, y, z)
