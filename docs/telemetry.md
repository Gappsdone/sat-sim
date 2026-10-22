# Telemetry

## Frontend telemetry API

The separate `sat_sim_telemetry` package adapts simulation state for browser
frontends without adding transport concerns to `sat_sim`. It provides immutable,
versioned Pydantic wire models and a FastAPI application with:

- `GET /api/v1/scenario` for static units, geometry, and capacities;
- `GET /api/v1/state` for the latest complete state snapshot; and
- `WS /api/v1/telemetry` for timestamped state frames.

Frames contain TEME position and velocity, a normalized body-to-TEME quaternion,
Sun/eclipse state, PCDU telemetry, and all thermal channels. Field names use
lower camel case on the wire. The broadcaster keeps only a small bounded queue
per client, so a slow renderer receives recent simulation state instead of
creating backpressure.

The live server also produces a CRC-protected PUS Service 3 periodic
housekeeping packet (`TM(3,25)`) for every simulation step. Complete PUS packets
are published and consumed exclusively as one packet per UDP datagram; they are
not exposed through the HTTP telemetry API. Its application payload uses the
PUSUtilities `DataSST25` layout implemented by `HousekeepingReport`: an 8-bit
structure ID followed by raw parameter values in the structure order configured
in PUSUtilities. Parameter IDs and types are mission-database metadata and are
not repeated in each report. The CCSDS packet sequence counter carries the
simulation report sequence.

TCS parameter IDs, sizes, types, and source PRID come from `plugin_tcs`'s
`TCS.java` on its `dev` branch: PRID 5, 27 four-byte `FLOAT` thermistors grouped
as three sensors for each of nine heaters, followed by nine four-byte `INTEGER`
heater indicators. Each simulated thermal channel feeds the plugin's three
thermistors for that heater. Heater output is published as the integer activity
indicator expected by the plugin. SID 1 must be configured in PUSUtilities with
those 36 IDs in the order declared by `TCS_HOUSEKEEPING_DEFINITIONS`; the plugin
registers their value metadata but does not create a housekeeping structure.
Illumination and electrical-power values are omitted because `plugin_tcs`
defines no parameter IDs for them.
The reusable `pus_library.HousekeepingService` mirrors PUSUtilities'
`HouseKeeping.Structure` registry and per-requester subscription behavior while
leaving scheduling in the deterministic simulation loop rather than starting a
wall-clock worker thread. SID 1 has a collection interval of one simulator step
and is enabled for ground PRID 0 by default. TC(3,5) and TC(3,6) enable and
disable its periodic reports for the requesting PRID. TC(3,136) requests one
immediate TM(3,25), while TC(3,9) returns its PUSUtilities-compatible TM(3,10)
definition: SID, 16-bit collection interval, 8-bit parameter count, and the
ordered 32-bit parameter IDs. Dynamic structure creation and deletion through
TC(3,1)/(3,3) are not supported because the simulator exposes one fixed
plugin-defined structure.

The bidirectional UDP socket is configured through environment variables:

- `SAT_SIM_PUS_BIND_HOST` and `SAT_SIM_PUS_BIND_PORT` select the local receive
  address (defaults: `127.0.0.1:10025`);
- `SAT_SIM_PUS_DESTINATION_HOST` and `SAT_SIM_PUS_DESTINATION_PORT` select the
  publish destination (defaults: `127.0.0.1:10015`).

Inbound datagrams are parsed as complete PUS source packets and discarded when
their framing or CRC is invalid. Valid packets enter the service-dispatch path;
supported telecommands are wrapped in Service 1 verification reports.

```python
from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim_telemetry import TelemetryStore, create_app, describe_iss_scenario

scenario = ISSScenario()
store = TelemetryStore()
app = create_app(store, lambda: describe_iss_scenario(scenario))
```

Use `ISSTelemetryPublisher` to step the scenario and publish each resulting
frame. A Cesium client can feed the timestamped TEME samples into a
`SampledPositionProperty` and use the supplied quaternion for orientation.

## Cesium frontend

The separate `frontend` package renders the live ISS position and orbit trail
over Esri World Imagery on a Cesium globe, with source attribution displayed on
the map. It transforms timestamped TEME samples into Cesium's pseudo-fixed frame,
applies the streamed body-to-TEME attitude, and shows eclipse, battery,
generation, load, ADCS pointing error, reaction-wheel speed, and all nine
thermal channels in a responsive systems panel.

![Live ISS scenario in the Cesium telemetry dashboard](images/iss-telemetry-dashboard.png)

Start the live simulation API and the frontend in separate terminals:

```shell
uv run sat-sim
cd frontend && npm install && npm run dev
```

Then open `http://127.0.0.1:5173`. Vite proxies both HTTP and WebSocket API
traffic to `http://127.0.0.1:8000`, so no Cesium ion token is required. The Esri
imagery service requires network access from the browser. To use
a custom development hostname, set a comma-separated allowlist before starting
Vite, for example `VITE_ALLOWED_HOSTS=dashboard.example.test npm run dev`. The
client reconnects automatically with bounded exponential backoff if the
telemetry server restarts.

