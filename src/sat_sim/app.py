"""Application logic for sat-sim."""


def greeting(name: str = "sat-sim") -> str:
    """Return a friendly greeting for the application."""
    return f"Hello from {name}!"


def main() -> None:
    """Run the application."""
    print(greeting())
