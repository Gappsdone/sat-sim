export interface Vector3Telemetry {
  frame: "TEME";
  unit: string;
  value: [number, number, number];
}

export interface ThermalChannelTelemetry {
  id: number;
  temperatureC: number;
  heaterOutput: number;
  heaterPowerW: number;
  heaterRatedPowerW: number;
  setpointC: number | null;
}

export interface EntityTelemetry {
  position: Vector3Telemetry;
  velocity: Vector3Telemetry;
  attitude: {
    frame: "BODY_TO_TEME";
    representation: "quaternion";
    order: "xyzw";
    value: [number, number, number, number];
  };
  adcs: {
    angularVelocityBodyRadS: [number, number, number];
    pointingErrorDeg: number;
    targetQuaternionXyzw: [number, number, number, number];
    commandedTorqueNm: [number, number, number];
    appliedTorqueNm: [number, number, number];
    disturbanceTorqueNm: [number, number, number];
    wheelSpeedsRadS: [number, number, number];
    wheelSaturated: [boolean, boolean, boolean];
    estimatedQuaternionXyzw: [number, number, number, number];
    measuredAngularVelocityBodyRadS: [number, number, number];
    sensorValid: Record<string, boolean>;
    mode: string;
    faultReason: string | null;
    magnetorquerDipoleAM2: [number, number, number];
    magnetorquerTorqueNm: [number, number, number];
  };
  illumination: {
    sunlit: boolean | null;
    sunDirectionEci: [number, number, number] | null;
  };
  power: {
    batteryChargeWh: number;
    batteryCapacityWh: number;
    stateOfCharge: number;
    generatedPowerW: number;
    consumedPowerW: number;
  };
  thermalChannels: ThermalChannelTelemetry[];
}

export interface TelemetryFrame {
  schemaVersion: 1;
  sequence: number;
  time: string;
  entities: { iss: EntityTelemetry };
}

export interface ScenarioDescription {
  schemaVersion: 1;
  scenario: string;
  entities: string[];
  entityComponents: Record<string, string[]>;
  entityComponentValues: Record<string, Record<string, Record<string, unknown>>>;
}

export interface ComponentSnapshot {
  name: string;
  values: Record<string, unknown>;
}

export function issComponents(value: unknown): ComponentSnapshot[] {
  if (typeof value !== "object" || value === null) {
    throw new TypeError("scenario description must be an object");
  }
  const componentValues = (value as { entityComponentValues?: unknown }).entityComponentValues;
  if (typeof componentValues !== "object" || componentValues === null) {
    throw new TypeError("scenario description is missing entityComponentValues");
  }
  const components = (componentValues as { iss?: unknown }).iss;
  if (typeof components !== "object" || components === null || Array.isArray(components)) {
    throw new TypeError("scenario description is missing the ISS component values");
  }
  return Object.entries(components).map(([name, values]) => {
    if (typeof values !== "object" || values === null || Array.isArray(values)) {
      throw new TypeError(`component ${name} values must be an object`);
    }
    return { name, values: values as Record<string, unknown> };
  });
}

export function telemetryWebSocketUrl(location: Location): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/api/v1/telemetry`;
}

export function componentLabel(name: string): string {
  return name
    .replaceAll("_", " ")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2");
}

export function illuminationLabel(sunlit: boolean | null): string {
  if (sunlit === null) return "Unknown";
  return sunlit ? "Sunlit" : "Eclipse";
}

export function temperatureRange(channels: ThermalChannelTelemetry[]): string {
  if (channels.length === 0) return "—";
  const values = channels.map((channel) => channel.temperatureC);
  return `${Math.min(...values).toFixed(1)}–${Math.max(...values).toFixed(1)} °C`;
}
