import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.request import Request, urlopen

from sat_sim import __version__

_TLE_LINE1_PATTERN = re.compile(r"^1 \d{5}[A-Z ]")
_TLE_LINE2_PATTERN = re.compile(r"^2 \d{5} ")

DEFAULT_TIMEOUT = 10.0
DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY = 1.0
TleFetcher = Callable[[str, float], str]
Sleeper = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class TLE:
    """A satellite name and its two-line element data."""

    name: str
    line1: str
    line2: str


def download_text(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": f"sat-sim/{__version__}"})
    with urlopen(request, timeout=timeout) as response:
        text: str = response.read().decode("utf-8")
        return text


def parse_tle(text: str) -> TLE:
    """Extract the first valid two-line element set from ``text``."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for index, line1 in enumerate(lines[:-1]):
        line2 = lines[index + 1]
        if _TLE_LINE1_PATTERN.match(line1) and _TLE_LINE2_PATTERN.match(line2):
            name = lines[index - 1] if index else "ISS"
            return TLE(name=name, line1=line1, line2=line2)

    raise ValueError("ISS TLE response does not contain a valid two-line element set")
