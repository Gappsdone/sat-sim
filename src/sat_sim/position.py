import math
from dataclasses import dataclass

# WGS84 ellipsoid constants
WGS84_SEMI_MAJOR_AXIS = 6378137.0  # meters
WGS84_ECCENTRICITY_SQUARED = 6.69437999014e-3  # square of first eccentricity


@dataclass(slots=True, repr=False)
class ECEFPosition:
    """Earth-Centered, Earth-Fixed (ECEF) Cartesian position in meters."""

    x: float
    y: float
    z: float

    @staticmethod
    def from_lat_lon_alt(
        latitude: float, longitude: float, altitude: float
    ) -> "ECEFPosition":
        """Convert latitude, longitude, and altitude to ECEF Cartesian coordinates."""

        lat_rad = math.radians(latitude)
        lon_rad = math.radians(longitude)

        prime_vertical_radius = WGS84_SEMI_MAJOR_AXIS / math.sqrt(
            1 - WGS84_ECCENTRICITY_SQUARED * (math.sin(lat_rad) ** 2)
        )

        x = (prime_vertical_radius + altitude) * math.cos(lat_rad) * math.cos(lon_rad)
        y = (prime_vertical_radius + altitude) * math.cos(lat_rad) * math.sin(lon_rad)
        z = (
            (1 - WGS84_ECCENTRICITY_SQUARED) * prime_vertical_radius + altitude
        ) * math.sin(lat_rad)

        return ECEFPosition(x, y, z)

    def __repr__(self) -> str:
        return f"ECEFPosition(x={self.x:.5f}, y={self.y:.5f}, z={self.z:.5f})"


@dataclass(slots=True, repr=False)
class ECIPosition:
    """Earth-Centered Inertial Cartesian position in meters."""

    x: float
    y: float
    z: float

    def __repr__(self) -> str:
        return f"ECIPosition(x={self.x:.5f}, y={self.y:.5f}, z={self.z:.5f})"


@dataclass(slots=True, repr=False)
class ECIVelocity:
    """Earth-Centered Inertial Cartesian velocity in meters per second."""

    x: float
    y: float
    z: float

    def __repr__(self) -> str:
        return f"ECIVelocity(x={self.x:.5f}, y={self.y:.5f}, z={self.z:.5f})"
