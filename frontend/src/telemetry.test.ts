import { describe, expect, it } from "vitest";
import {
  componentLabel,
  illuminationLabel,
  issComponents,
  temperatureRange,
  telemetryWebSocketUrl,
} from "./telemetry";

describe("telemetry presentation", () => {
  it("reads the ISS component values from scenario metadata", () => {
    expect(
      issComponents({
        entityComponentValues: {
          iss: { PCDU: { chargeWh: 500 }, SolarPanel: { peakPowerW: 100 } },
        },
      }),
    ).toEqual([
      { name: "PCDU", values: { chargeWh: 500 } },
      { name: "SolarPanel", values: { peakPowerW: 100 } },
    ]);
  });

  it("rejects scenario metadata without a valid ISS inventory", () => {
    expect(() => issComponents({ entities: ["iss"] })).toThrow(/entityComponentValues/);
    expect(() => issComponents({ entityComponentValues: { iss: [] } })).toThrow(
      /ISS component values/,
    );
  });

  it("selects the WebSocket scheme from the page URL", () => {
    expect(telemetryWebSocketUrl({ protocol: "http:", host: "localhost:5173" } as Location)).toBe("ws://localhost:5173/api/v1/telemetry");
    expect(telemetryWebSocketUrl({ protocol: "https:", host: "mission.test" } as Location)).toBe("wss://mission.test/api/v1/telemetry");
  });

  it("labels all illumination states", () => {
    expect(illuminationLabel(true)).toBe("Sunlit");
    expect(illuminationLabel(false)).toBe("Eclipse");
    expect(illuminationLabel(null)).toBe("Unknown");
  });

  it("formats the thermal range", () => {
    const channel = (temperatureC: number) => ({ id: 0, temperatureC, heaterOutput: 0, heaterPowerW: 0, heaterRatedPowerW: 10, setpointC: 22 });
    expect(temperatureRange([channel(20.14), channel(23.76)])).toBe("20.1–23.8 °C");
    expect(temperatureRange([])).toBe("—");
  });

  it("formats ECS component class names for display", () => {
    expect(componentLabel("ECIPosition")).toBe("ECI Position");
    expect(componentLabel("ADCSSensorConfiguration")).toBe("ADCS Sensor Configuration");
    expect(componentLabel("ReactionWheelAssembly")).toBe("Reaction Wheel Assembly");
    expect(componentLabel("angular_velocity_body_rad_s")).toBe("angular velocity body rad s");
  });
});
