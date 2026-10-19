import {
  ArcGisMapServerImageryProvider,
  Cartesian3,
  ClockRange,
  Color,
  Entity,
  HeadingPitchRange,
  ImageryLayer,
  Ion,
  JulianDate,
  Matrix3,
  NearFarScalar,
  PathGraphics,
  PointGraphics,
  Quaternion,
  SampledPositionProperty,
  SampledProperty,
  Transforms,
  Viewer,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import "./styles.css";
import {
  componentLabel,
  illuminationLabel,
  issComponents,
  telemetryWebSocketUrl,
  temperatureRange,
  type ComponentSnapshot,
  type EntityTelemetry,
  type TelemetryFrame,
} from "./telemetry";

Ion.defaultAccessToken = "";

document.querySelector<HTMLDivElement>("#app")!.innerHTML = `
  <main class="shell">
    <section class="globe-panel">
      <div id="cesium" aria-label="3D view of the International Space Station"></div>
      <div class="brand"><span class="brand-mark">◫</span><span>SAT-SIM</span></div>
      <div class="connection"><span id="connection-dot"></span><span id="connection-text">Connecting</span></div>
      <div class="imagery-attribution">Imagery: <a href="https://www.esri.com/" target="_blank" rel="noopener noreferrer">Esri</a>, Vantor, Earthstar Geographics, and the GIS User Community</div>
    </section>
    <aside class="telemetry-panel">
      <header><p class="eyebrow">LIVE SCENARIO</p><h1>International<br/>Space Station</h1><p id="timestamp">Waiting for telemetry</p></header>
      <nav class="panel-tabs" role="tablist" aria-label="ISS information">
        <button id="telemetry-tab" type="button" role="tab" aria-selected="true" aria-controls="telemetry-view" data-panel="telemetry-view">Telemetry</button>
        <button id="components-tab" type="button" role="tab" aria-selected="false" aria-controls="components-view" data-panel="components-view" tabindex="-1">Components</button>
      </nav>
      <div id="telemetry-view" class="tab-panel" role="tabpanel" aria-labelledby="telemetry-tab">
        <section class="metric-grid">
          <article><span>ILLUMINATION</span><strong id="illumination">—</strong></article>
          <article><span>BATTERY</span><strong id="battery">—</strong><div class="meter"><i id="battery-meter"></i></div></article>
          <article><span>GENERATION</span><strong id="generation">—</strong></article>
          <article><span>LOAD</span><strong id="load">—</strong></article>
          <article><span>POINTING ERROR</span><strong id="pointing-error">—</strong></article>
          <article><span>MAX WHEEL SPEED</span><strong id="wheel-speed">—</strong></article>
        </section>
        <section class="thermal">
          <div class="section-heading"><div><p class="eyebrow">THERMAL CONTROL</p><h2>Channel Array</h2></div><strong id="temperature-range">—</strong></div>
          <div id="thermal-grid" class="thermal-grid"></div>
        </section>
      </div>
      <div id="components-view" class="tab-panel components-view" role="tabpanel" aria-labelledby="components-tab" hidden>
        <section class="components">
          <div class="section-heading"><div><p class="eyebrow">ENTITY INVENTORY</p><h2>ISS Components</h2></div><strong id="component-count">—</strong></div>
          <p class="components-intro">ECS components currently attached to the primary ISS entity.</p>
          <div id="component-list" class="component-list" aria-live="polite"><p class="components-status">Loading component inventory…</p></div>
        </section>
      </div>
      <footer><span>ECI LIVE TELEMETRY</span><span id="sequence">SEQ —</span></footer>
    </aside>
  </main>`;

const tabs = Array.from(document.querySelectorAll<HTMLButtonElement>("[role='tab']"));

function selectTab(selected: HTMLButtonElement): void {
  for (const tab of tabs) {
    const active = tab === selected;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    document.querySelector<HTMLElement>(`#${tab.dataset.panel}`)!.hidden = !active;
  }
}

for (const tab of tabs) {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const offset = event.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(tabs.indexOf(tab) + offset + tabs.length) % tabs.length]!;
    selectTab(next);
    next.focus();
  });
}

function formatComponentValue(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value) || typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderComponents(components: ComponentSnapshot[]): void {
  const list = document.querySelector<HTMLDivElement>("#component-list")!;
  const cards = components.map(({ name, values }) => {
    const card = document.createElement("article");
    const label = document.createElement("strong");
    const type = document.createElement("code");
    const fields = document.createElement("dl");
    label.textContent = componentLabel(name);
    type.textContent = name;
    for (const [field, value] of Object.entries(values)) {
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = componentLabel(field);
      description.textContent = formatComponentValue(value);
      fields.append(term, description);
    }
    card.append(label, type, fields);
    return card;
  });
  list.replaceChildren(...cards);
  setText("component-count", `${components.length} TOTAL`);
}

async function loadComponents(): Promise<void> {
  let refreshDelay = 1_000;
  try {
    const response = await fetch("/api/v1/scenario");
    if (!response.ok) throw new Error(`scenario request failed: ${response.status}`);
    renderComponents(issComponents(await response.json()));
  } catch {
    document.querySelector<HTMLDivElement>("#component-list")!.innerHTML =
      '<p class="components-status error">Component inventory unavailable. Retrying…</p>';
    refreshDelay = 5_000;
  }
  window.setTimeout(loadComponents, refreshDelay);
}

const viewer = new Viewer("cesium", {
  animation: false,
  baseLayerPicker: false,
  fullscreenButton: false,
  geocoder: false,
  homeButton: false,
  infoBox: false,
  navigationHelpButton: false,
  sceneModePicker: false,
  selectionIndicator: false,
  timeline: false,
  baseLayer: ImageryLayer.fromProviderAsync(
    ArcGisMapServerImageryProvider.fromUrl(
      "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
      { enablePickFeatures: false },
    ),
  ),
  requestRenderMode: true,
});
viewer.scene.backgroundColor = Color.fromCssColorString("#020609");
viewer.scene.globe.baseColor = Color.fromCssColorString("#102838");
viewer.scene.globe.enableLighting = true;
if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show = true;
viewer.clock.clockRange = ClockRange.UNBOUNDED;

const positions = new SampledPositionProperty();
positions.setInterpolationOptions({ interpolationDegree: 2 });
const orientations = new SampledProperty(Quaternion);
const iss = new Entity({
  id: "iss",
  name: "International Space Station",
  position: positions,
  orientation: orientations,
  point: new PointGraphics({
    color: Color.fromCssColorString("#7ce7ff"),
    pixelSize: 10,
    outlineColor: Color.WHITE,
    outlineWidth: 2,
    scaleByDistance: new NearFarScalar(1e5, 1.4, 2e7, 0.5),
  }),
  path: new PathGraphics({
    leadTime: 0,
    trailTime: 5_400,
    width: 2,
    material: Color.fromCssColorString("#30d6ff").withAlpha(0.7),
  }),
});
viewer.entities.add(iss);

let hasFramed = false;
let reconnectDelay = 1_000;

function fixedTransform(time: JulianDate): Matrix3 {
  return Transforms.computeIcrfToFixedMatrix(time) ?? Matrix3.IDENTITY;
}

function ingest(frame: TelemetryFrame): void {
  const state = frame.entities.iss;
  const time = JulianDate.fromIso8601(frame.time);
  const transform = fixedTransform(time);
  const eci = Cartesian3.fromArray(state.position.value);
  const fixed = Matrix3.multiplyByVector(transform, eci, new Cartesian3());
  positions.addSample(time, fixed);

  const [x, y, z, w] = state.attitude.value;
  const bodyToEci = new Quaternion(x, y, z, w);
  const eciToFixed = Quaternion.fromRotationMatrix(transform);
  orientations.addSample(time, Quaternion.multiply(eciToFixed, bodyToEci, new Quaternion()));

  viewer.clock.currentTime = time;
  viewer.scene.requestRender();
  if (!hasFramed) {
    hasFramed = true;
    void viewer.flyTo(iss, {
      duration: 1.5,
      offset: new HeadingPitchRange(0, -0.45, 12_000_000),
    });
  }
  updateDashboard(frame, state);
}

function updateDashboard(frame: TelemetryFrame, state: EntityTelemetry): void {
  setText("timestamp", new Date(frame.time).toLocaleString());
  setText("illumination", illuminationLabel(state.illumination.sunlit));
  setText("battery", `${(state.power.stateOfCharge * 100).toFixed(1)}%`);
  setText("generation", `${state.power.generatedPowerW.toFixed(1)} W`);
  setText("load", `${state.power.consumedPowerW.toFixed(1)} W`);
  setText("pointing-error", `${state.adcs.pointingErrorDeg.toFixed(3)}°`);
  setText(
    "wheel-speed",
    `${Math.max(...state.adcs.wheelSpeedsRadS.map(Math.abs)).toFixed(2)} rad/s`,
  );
  setText("temperature-range", temperatureRange(state.thermalChannels));
  setText("sequence", `SEQ ${frame.sequence}`);
  document.querySelector<HTMLElement>("#battery-meter")!.style.width = `${Math.max(0, Math.min(100, state.power.stateOfCharge * 100))}%`;
  document.querySelector<HTMLDivElement>("#thermal-grid")!.innerHTML = state.thermalChannels
    .map((channel) => `<article><span>CH ${String(channel.id + 1).padStart(2, "0")}</span><strong>${channel.temperatureC.toFixed(1)}°</strong><small>${(channel.heaterOutput * 100).toFixed(0)}% HEAT</small></article>`)
    .join("");
}

function setText(id: string, text: string): void {
  document.querySelector<HTMLElement>(`#${id}`)!.textContent = text;
}

function setConnection(connected: boolean): void {
  document.querySelector("#connection-dot")?.classList.toggle("online", connected);
  setText("connection-text", connected ? "Live" : "Reconnecting");
}

function connect(): void {
  const socket = new WebSocket(telemetryWebSocketUrl(window.location));
  socket.addEventListener("open", () => {
    reconnectDelay = 1_000;
    setConnection(true);
  });
  socket.addEventListener("message", (event) => ingest(JSON.parse(String(event.data)) as TelemetryFrame));
  socket.addEventListener("close", () => {
    setConnection(false);
    window.setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(15_000, reconnectDelay * 2);
  });
  socket.addEventListener("error", () => socket.close());
}

connect();
void loadComponents();
