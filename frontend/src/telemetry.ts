export interface Vector3Telemetry {
  frame: "ECI";
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
    frame: "BODY_TO_ECI";
    representation: "quaternion";
    order: "xyzw";
    value: [number, number, number, number];
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

export function telemetryWebSocketUrl(location: Location): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/api/v1/telemetry`;
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
