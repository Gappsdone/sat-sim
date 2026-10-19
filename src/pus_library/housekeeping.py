"""PUSUtilities-compatible application payloads for Service 3 reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from struct import pack, unpack
from typing import Literal

from .enums import DEFAULT_BYTE_ORDER, ByteOrder
from .service import ServiceData, service_data

HOUSEKEEPING_SERVICE_TYPE = 3
HOUSEKEEPING_REPORT_SUBTYPE = 25


class HousekeepingParameterType(IntEnum):
    """PUSUtilities parameter value types supported by this implementation."""

    SIGNED_INTEGER = 1
    FLOAT = 2


HousekeepingValue = int | float


def _byte_order_name(byte_order: ByteOrder) -> Literal["big", "little"]:
    return "big" if byte_order is ByteOrder.BIG_ENDIAN else "little"


@dataclass(frozen=True)
class HousekeepingParameterDefinition:
    """Mission-database metadata for one parameter in a structure."""

    parameter_id: int
    number_of_bytes: int
    parameter_type: HousekeepingParameterType

    def __post_init__(self) -> None:
        if not 0 <= self.parameter_id <= 0xFFFFFFFF:
            raise ValueError("parameter_id must fit in an unsigned 32-bit integer")
        allowed_sizes: tuple[int, ...]
        if self.parameter_type is HousekeepingParameterType.SIGNED_INTEGER:
            allowed_sizes = (1, 2, 4, 8)
        else:
            allowed_sizes = (4, 8)
        if self.number_of_bytes not in allowed_sizes:
            raise ValueError(
                f"unsupported {self.parameter_type.name.lower()} parameter width"
            )


@dataclass(frozen=True)
class HousekeepingParameter:
    """One value paired with its mission-database definition."""

    definition: HousekeepingParameterDefinition
    value: HousekeepingValue

    @property
    def parameter_id(self) -> int:
        """Return the database ID, which is metadata and not sent in TM(3,25)."""
        return self.definition.parameter_id

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        """Encode only the raw value as required by PUSUtilities ``DataSST25``."""
        order = _byte_order_name(byte_order)
        if self.definition.parameter_type is HousekeepingParameterType.FLOAT:
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise TypeError("floating-point housekeeping values must be numeric")
            format_code = "f" if self.definition.number_of_bytes == 4 else "d"
            return pack((">" if order == "big" else "<") + format_code, self.value)
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError("integer housekeeping values must be integers")
        try:
            return self.value.to_bytes(
                self.definition.number_of_bytes, order, signed=True
            )
        except OverflowError as error:
            raise ValueError(
                "integer housekeeping value does not fit its width"
            ) from error


@dataclass(frozen=True)
class HousekeepingReport:
    """A PUSUtilities ``DataSST25`` structure report.

    Parameter IDs and types live in the mission database. The wire payload is
    the unsigned 8-bit SID followed by raw values in configured structure order.
    """

    structure_id: int
    parameters: tuple[HousekeepingParameter, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.structure_id <= 0xFF:
            raise ValueError("structure_id must fit in an unsigned 8-bit integer")
        identifiers = [parameter.parameter_id for parameter in self.parameters]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("housekeeping parameter IDs must be unique")

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        """Serialize as SID followed by raw values in structure order."""
        return bytes((self.structure_id,)) + b"".join(
            parameter.get_bytes(byte_order) for parameter in self.parameters
        )

    def to_service_data(self) -> ServiceData:
        """Wrap this report as PUS periodic housekeeping telemetry."""
        return service_data(
            HOUSEKEEPING_SERVICE_TYPE,
            HOUSEKEEPING_REPORT_SUBTYPE,
            self.get_bytes(),
        )

    @classmethod
    def from_service_data(
        cls,
        data: ServiceData,
        definitions: tuple[HousekeepingParameterDefinition, ...],
        byte_order: ByteOrder = DEFAULT_BYTE_ORDER,
    ) -> HousekeepingReport:
        """Decode using the receiving PUSUtilities structure definition."""
        if (
            data.service_type != HOUSEKEEPING_SERVICE_TYPE
            or data.service_sub_type != HOUSEKEEPING_REPORT_SUBTYPE
        ):
            raise ValueError("service data must be a TM(3,25) housekeeping report")
        if not data.data:
            raise ValueError("housekeeping report is missing its structure ID")
        expected_size = 1 + sum(item.number_of_bytes for item in definitions)
        if len(data.data) != expected_size:
            raise ValueError("housekeeping report length does not match its structure")
        order = _byte_order_name(byte_order)
        offset = 1
        parameters: list[HousekeepingParameter] = []
        for definition in definitions:
            raw = data.data[offset : offset + definition.number_of_bytes]
            if definition.parameter_type is HousekeepingParameterType.FLOAT:
                format_code = "f" if definition.number_of_bytes == 4 else "d"
                value: HousekeepingValue = unpack(
                    (">" if order == "big" else "<") + format_code, raw
                )[0]
            else:
                value = int.from_bytes(raw, order, signed=True)
            parameters.append(HousekeepingParameter(definition, value))
            offset += definition.number_of_bytes
        return cls(data.data[0], tuple(parameters))
