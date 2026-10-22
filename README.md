# sat-sim

A runnable spacecraft simulator built on a simple entity-component system (ECS),
with a live ISS scenario and Cesium telemetry dashboard.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js and npm for the optional frontend

## Quickstart

```shell
uv sync
uv run sat-sim
```

The live telemetry API listens on `127.0.0.1:8000`. In another terminal, start
the frontend:

```shell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Run `uv run sat-sim --help` for CLI options.

## Documentation

[Read the full documentation on GitHub Pages](https://gappsdone.github.io/sat-sim/)
for scenarios, simulation systems, telemetry, the frontend, and the PUS library.
Documentation sources live in [`docs/`](docs/). To preview locally:

```shell
uv run --group docs mkdocs serve
```

## Checks

```shell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
cd frontend && npm run check
```
