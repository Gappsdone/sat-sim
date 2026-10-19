"""Command-line interface for running sat-sim scenarios."""

import argparse
from collections.abc import Sequence

from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim.simulation import Simulation


def positive_float(value: str) -> float:
    """Parse a positive floating-point command-line value."""
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def create_parser() -> argparse.ArgumentParser:
    """Create the sat-sim command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="sat-sim",
        description="Run the live ISS spacecraft simulation.",
    )
    parser.add_argument(
        "--interval",
        default=1.0,
        type=positive_float,
        help="simulation step interval in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--tle-timeout",
        default=10.0,
        type=positive_float,
        help="ISS TLE request timeout in seconds (default: %(default)s)",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    """Parse command-line options and run the ISS simulation."""
    options = create_parser().parse_args(arguments)
    scenario = ISSScenario(timeout=options.tle_timeout)
    simulation = Simulation(scenario, interval=options.interval)

    print("Starting the ISS simulation. Press Ctrl+C to stop.")
    simulation.run()
    print("ISS simulation stopped.")
