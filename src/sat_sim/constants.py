"""Physical constants used by the spacecraft simulation.

All values use SI units. Spacecraft-specific design values and tunable model
parameters belong to their owning components rather than this module.
"""

# Earth geometry
EARTH_MEAN_RADIUS_METERS = 6_371_000.0
WGS84_SEMI_MAJOR_AXIS_METERS = 6_378_137.0
WGS84_ECCENTRICITY_SQUARED = 6.69437999014e-3

# Earth environment
EARTH_GRAVITATIONAL_PARAMETER_M3_S2 = 3.986004418e14
EARTH_ANGULAR_VELOCITY_RAD_S = 7.2921159e-5
EARTH_EQUATORIAL_MAGNETIC_FIELD_T = 3.12e-5

# Mean solar radiation pressure near Earth at one astronomical unit
SOLAR_RADIATION_PRESSURE_N_M2 = 4.56e-6
