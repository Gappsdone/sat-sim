import { describe, expect, it } from "vitest";
import { componentLabel, illuminationLabel, temperatureRange, telemetryWebSocketUrl } from "./telemetry";

describe("telemetry presentation", () => {
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
  });
});
