"""ISS orbital scenario with integrated thermal-control telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import sleep

from sat_sim.ecs import Entity
from sat_sim.orbital import (
    OrbitalLike,
    create_satellite_from_orbital,
    propagate_orbital,
)
from sat_sim.position import ECIPosition, ECIVelocity
from sat_sim.scenario import Scenario
from sat_sim.services.tcs import (
    DEFAULT_HEATER_THRESHOLD_CELSIUS,
    ThermalControlSystem,
)
from sat_sim.simulation import Simulation
from sat_sim.tle import (
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TIMEOUT,
    TLE,
    Sleeper,
    TleFetcher,
    download_text,
    parse_tle,
)

ISS_TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?NAME=ISS&FORMAT=tle"
DEFAULT_THERMAL_THRESHOLD_CELSIUS = DEFAULT_HEATER_THRESHOLD_CELSIUS


@dataclass(frozen=True)
class ISSScenarioState:
    """Snapshot of ISS orbital and thermal state after one simulation step."""

    timestamp: datetime
    position: ECIPosition
    velocity: ECIVelocity
    temperatures_celsius: tuple[float, ...]
    heater_outputs: tuple[float, ...]
    is_sunlit: bool | None


def fetch_iss_tle(
    timeout: float = DEFAULT_TIMEOUT,
    fetcher: TleFetcher | None = None,
    *,
    retries: int = DEFAULT_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    sleeper: Sleeper = sleep,
) -> TLE:
    """Fetch and validate the current ISS TLE from CelesTrak.

    Transient network errors are retried up to ``retries`` times, waiting
    ``retry_delay`` seconds between attempts.
    """
    if retries < 0:
        raise ValueError("retries must not be negative")
    get_text = fetcher or download_text

    last_error: OSError | None = None
    for attempt in range(retries + 1):
        try:
            text = get_text(ISS_TLE_URL, timeout)
        except OSError as error:
            last_error = error
            if attempt < retries:
                sleeper(retry_delay)
        else:
            return parse_tle(text)

    assert last_error is not None
    raise last_error


def create_iss_orbital(
    timeout: float = DEFAULT_TIMEOUT,
    fetcher: TleFetcher | None = None,
) -> OrbitalLike:
    """Fetch the current ISS TLE and create a pyorbital-compatible object."""
    from pyorbital.orbital import Orbital

    tle = fetch_iss_tle(timeout=timeout, fetcher=fetcher)
    orbital: OrbitalLike = Orbital(tle.name, line1=tle.line1, line2=tle.line2)
    return orbital


class ISSScenario(Scenario):
    """Propagate the ISS and simulate a paired 3x3 thermal-control array."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        fetcher: TleFetcher | None = None,
        *,
        thermal_control_system: ThermalControlSystem | None = None,
        thermal_threshold_celsius: float = DEFAULT_THERMAL_THRESHOLD_CELSIUS,
    ) -> None:
        super().__init__()
        self.timeout = timeout
        self.fetcher = fetcher
        self.orbital: OrbitalLike | None = None
        self.entity: Entity | None = None
        # A modest model scale and proportional gain keep this illustrative
        # simulation responsive without treating watts as a real spacecraft
        # thermal model.
        self.tcs = thermal_control_system or ThermalControlSystem(
            initial_temperature=20.0,
            wattages=[10.0] * 9,
            heating_rate=0.01,
            kp=0.1,
            ki=0.001,
            kd=0.02,
            heater_threshold_celsius=thermal_threshold_celsius,
        )
        self.thermal_threshold_celsius = thermal_threshold_celsius
        self._last_thermal_timestamp: datetime | None = None

    def setup(self, timestamp: datetime) -> None:
        """Fetch the ISS TLE and initialize orbital and thermal state."""
        if self.entity is not None:
            raise RuntimeError("ISS scenario is already set up")
        self.orbital = create_iss_orbital(
            timeout=self.timeout,
            fetcher=self.fetcher,
        )
        self.entity = create_satellite_from_orbital(
            self.world,
            self.orbital,
            timestamp,
        )
        self._last_thermal_timestamp = timestamp

    def step(self, timestamp: datetime) -> ISSScenarioState:
        """Advance orbit and thermal simulation, then return a state snapshot."""
        if self.orbital is None or self.entity is None:
            raise RuntimeError("ISS scenario must be set up before stepping")

        previous_timestamp = self._last_thermal_timestamp
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise ValueError("step timestamp must not precede the previous step")

        position, velocity = propagate_orbital(self.orbital, timestamp)
        current_position = self.world.get(self.entity, ECIPosition)
        current_velocity = self.world.get(self.entity, ECIVelocity)
        current_position.x = position.x
        current_position.y = position.y
        current_position.z = position.z
        current_velocity.x = velocity.x
        current_velocity.y = velocity.y
        current_velocity.z = velocity.z

        if previous_timestamp is not None:
            delta_time = (timestamp - previous_timestamp).total_seconds()
            if delta_time > 0:
                self.tcs.step(
                    delta_time,
                    (current_position.x, current_position.y, current_position.z),
                    timestamp,
                )
        self._last_thermal_timestamp = timestamp

        state = ISSScenarioState(
            timestamp=timestamp,
            position=ECIPosition(
                current_position.x, current_position.y, current_position.z
            ),
            velocity=ECIVelocity(
                current_velocity.x, current_velocity.y, current_velocity.z
            ),
            temperatures_celsius=tuple(
                sensor.temperature_celsius for sensor in self.tcs.sensors
            ),
            heater_outputs=tuple(heater.output_fraction for heater in self.tcs.heaters),
            is_sunlit=self.tcs.is_sunlit,
        )
        self.print_state(state)
        return state

    def print_state(self, state: ISSScenarioState) -> None:
        """Print current orbital state and per-channel thermal telemetry."""
        print(f"Simulation step: {state.timestamp.isoformat(sep=' ')}")
        print(f"\tPosition: {state.position}")
        print(f"\tVelocity: {state.velocity}")
        illumination = (
            "unknown"
            if state.is_sunlit is None
            else "sunlit"
            if state.is_sunlit
            else "eclipse"
        )
        print(f"\tThermal control ({illumination}):")
        for sensor, heater in zip(self.tcs.sensors, self.tcs.heaters, strict=True):
            setpoint_text = (
                "manual"
                if heater.manual_override
                else f"{self.tcs.heater_threshold_celsius:.1f} °C"
                if self.tcs.heater_threshold_celsius is not None
                else "disabled"
            )
            heater_watts = heater.power * heater.output_fraction
            print(
                f"\t\tChannel {sensor.id}: {sensor.temperature_celsius:.2f} °C; "
                f"heater {heater.output_fraction * 100:.1f}% "
                f"({heater_watts:.2f}/{heater.power:.2f} W); "
                f"threshold {setpoint_text}"
            )


def main() -> None:
    """Print ISS orbital and thermal state once per second until interrupted."""
    simulation = Simulation(ISSScenario())
    print("Press Ctrl+C to stop the ISS scenario.")
    simulation.run()
    print("ISS scenario stopped.")


if __name__ == "__main__":
    main()
