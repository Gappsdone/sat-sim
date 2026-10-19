import { JulianDate, Matrix3, Transforms } from "cesium";

export function temeToFixedMatrix(time: JulianDate): Matrix3 {
  return Transforms.computeTemeToPseudoFixedMatrix(time);
}
