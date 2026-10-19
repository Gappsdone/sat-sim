import { Cartesian3, Cartographic, JulianDate, Math as CesiumMath, Matrix3 } from "cesium";
import { describe, expect, it } from "vitest";
import { temeToFixedMatrix } from "./referenceFrames";

describe("TEME reference-frame conversion", () => {
  it("places an ISS TLE sample at its propagated sub-satellite point", () => {
    const time = JulianDate.fromIso8601("2026-10-19T21:05:52.976254Z");
    const teme = new Cartesian3(
      5_620_743.417503053,
      1_387_316.7213493802,
      -3_562_846.760619093,
    );
    const fixed = Matrix3.multiplyByVector(temeToFixedMatrix(time), teme, new Cartesian3());
    const point = Cartographic.fromCartesian(fixed);

    expect(CesiumMath.toDegrees(point.longitude)).toBeCloseTo(29.043233, 5);
    expect(CesiumMath.toDegrees(point.latitude)).toBeCloseTo(-31.769642, 5);
    expect(point.height / 1_000).toBeCloseTo(425.645, 2);
  });
});
