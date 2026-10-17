"""FastAPI routes for scenario metadata and live telemetry."""

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from sat_sim_telemetry.models import ScenarioDescription, TelemetryFrame
from sat_sim_telemetry.store import TelemetryStore

DescriptionProvider = Callable[[], ScenarioDescription]
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(
    store: TelemetryStore,
    description: ScenarioDescription | DescriptionProvider,
    *,
    allowed_origins: Sequence[str] = (),
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """Build a versioned telemetry API around a store and scenario description."""
    app = FastAPI(title="sat-sim telemetry", version="1.0.0", lifespan=lifespan)
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    def get_description() -> ScenarioDescription:
        return description() if callable(description) else description

    @app.get("/api/v1/scenario", response_model=ScenarioDescription)
    def scenario_metadata() -> ScenarioDescription:
        return get_description()

    @app.get("/api/v1/state", response_model=TelemetryFrame)
    def current_state() -> TelemetryFrame:
        frame = store.current
        if frame is None:
            raise HTTPException(status_code=503, detail="telemetry is not available")
        return frame

    @app.websocket("/api/v1/telemetry")
    async def telemetry(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            async with store.subscribe() as queue:
                last_sequence = -1
                if store.current is not None:
                    await websocket.send_json(
                        store.current.model_dump(mode="json", by_alias=True)
                    )
                    last_sequence = store.current.sequence
                while True:
                    frame = await queue.get()
                    if frame.sequence > last_sequence:
                        await websocket.send_json(
                            frame.model_dump(mode="json", by_alias=True)
                        )
                        last_sequence = frame.sequence
        except WebSocketDisconnect:
            return

    return app
