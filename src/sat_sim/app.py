"""Command-line interface for running sat-sim scenarios."""

import argparse
from collections.abc import Sequence

import uvicorn

from sat_sim.factory import simulation_factory
from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim_telemetry.server import create_live_app


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
        description="Run a spacecraft simulation.",
    )
    parser.add_argument(
        "--scenario",
        choices=simulation_factory.names,
        default="iss",
        help="scenario to run (default: %(default)s)",
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
    parser.add_argument("--host", default="127.0.0.1", help="API bind host")
    parser.add_argument("--port", default=8000, type=int, help="API bind port")
    parser.add_argument(
        "--offline", action="store_true", help="run only the terminal simulation"
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    """Parse command-line options and run the selected simulation."""
    options = create_parser().parse_args(arguments)
    simulation = simulation_factory.create(
        options.scenario, interval=options.interval, timeout=options.tle_timeout
    )

    if options.offline:
        print(f"Starting the {options.scenario} simulation. Press Ctrl+C to stop.")
        simulation.run()
        print(f"{options.scenario} simulation stopped.")
        return

    if not isinstance(simulation.scenario, ISSScenario):
        create_parser().error("online telemetry currently supports only ISSScenario")
    uvicorn.run(
        create_live_app(scenario=simulation.scenario, interval=simulation.interval),
        host=options.host,
        port=options.port,
    )
