"""Typed application payloads for PUS Service 3 housekeeping reports.

The ECSS PUS standard leaves the encoding of individual monitored parameters to
the mission database.  This module defines the compact application profile used
by sat-sim: a structure identifier followed by typed parameter samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from struct import pack, unpack
from typing import Literal

from .enums import DEFAULT_BYTE_ORDER, ByteOrder
from .service import ServiceData, service_data

HOUSEKEEPING_SERVICE_TYPE = 3
HOUSEKEEPING_REPORT_SUBTYPE = 25
HOUSEKEEPING_STRUCTURE_ID_BYTES = 1
HOUSEKEEPING_PARAMETER_ID_BYTES = 4


class HousekeepingParameterType(IntEnum):
    """Wire type assigned to a housekeeping parameter value."""

    BOOLEAN = 1
    SIGNED_INTEGER = 2
    FLOAT = 3


HousekeepingValue = bool | int | float


def _byte_order_name(byte_order: ByteOrder) -> Literal["big", "little"]:
    return "big" if byte_order is ByteOrder.BIG_ENDIAN else "little"


@dataclass(frozen=True)
class HousekeepingParameter:
    """One identified value in a housekeeping report."""

    parameter_id: int
    value: HousekeepingValue

    def __post_init__(self) -> None:
        if not 0 <= self.parameter_id <= 0xFFFFFFFF:
            raise ValueError("parameter_id must fit in an unsigned 32-bit integer")
        if not isinstance(self.value, (bool, int, float)):
            raise TypeError("housekeeping values must be bool, int, or float")
        if (
            isinstance(self.value, int)
            and not isinstance(self.value, bool)
            and not -(2**63) <= self.value < 2**63
        ):
            raise ValueError("integer housekeeping value must fit in 64 bits")


@dataclass(frozen=True)
class HousekeepingReport:
    """A named collection of typed parameter samples for TM(3,25)."""

    structure_id: int
    sequence: int
    parameters: tuple[HousekeepingParameter, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.structure_id <= 0xFF:
            raise ValueError("structure_id must fit in an unsigned 8-bit integer")
        if not 0 <= self.sequence <= 0xFFFFFFFF:
            raise ValueError("sequence must fit in an unsigned 32-bit integer")
        if len(self.parameters) > 0xFFFF:
            raise ValueError("a report cannot contain more than 65535 parameters")
        identifiers = [parameter.parameter_id for parameter in self.parameters]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("housekeeping parameter IDs must be unique")

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        """Serialize using the sat-sim Service 3 application profile."""
        order = _byte_order_name(byte_order)
        encoded = bytearray()
        encoded.extend(
            self.structure_id.to_bytes(HOUSEKEEPING_STRUCTURE_ID_BYTES, order)
        )
        encoded.extend(self.sequence.to_bytes(4, order))
        encoded.extend(len(self.parameters).to_bytes(2, order))
        for parameter in self.parameters:
            encoded.extend(
                parameter.parameter_id.to_bytes(HOUSEKEEPING_PARAMETER_ID_BYTES, order)
            )
            if isinstance(parameter.value, bool):
                encoded.append(HousekeepingParameterType.BOOLEAN)
                encoded.append(int(parameter.value))
            elif isinstance(parameter.value, int):
                encoded.append(HousekeepingParameterType.SIGNED_INTEGER)
                encoded.extend(parameter.value.to_bytes(8, order, signed=True))
            else:
                encoded.append(HousekeepingParameterType.FLOAT)
                encoded.extend(pack(">d" if order == "big" else "<d", parameter.value))
        return bytes(encoded)

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
        byte_order: ByteOrder = DEFAULT_BYTE_ORDER,
    ) -> HousekeepingReport:
        """Parse a TM(3,25) payload encoded by :meth:`to_service_data`."""
        if (
            data.service_type != HOUSEKEEPING_SERVICE_TYPE
            or data.service_sub_type != HOUSEKEEPING_REPORT_SUBTYPE
        ):
            raise ValueError("service data must be a TM(3,25) housekeeping report")
        raw = data.data
        header_size = HOUSEKEEPING_STRUCTURE_ID_BYTES + 4 + 2
        if len(raw) < header_size:
            raise ValueError("housekeeping report is shorter than its header")
        order = _byte_order_name(byte_order)
        structure_id = raw[0]
        sequence = int.from_bytes(raw[1:5], order)
        count = int.from_bytes(raw[5:7], order)
        offset = header_size
        parameters: list[HousekeepingParameter] = []
        for _index in range(count):
            parameter_header_size = HOUSEKEEPING_PARAMETER_ID_BYTES + 1
            if offset + parameter_header_size > len(raw):
                raise ValueError("housekeeping parameter header is truncated")
            parameter_id = int.from_bytes(
                raw[offset : offset + HOUSEKEEPING_PARAMETER_ID_BYTES], order
            )
            try:
                parameter_type = HousekeepingParameterType(
                    raw[offset + HOUSEKEEPING_PARAMETER_ID_BYTES]
                )
            except ValueError as error:
                raise ValueError("unknown housekeeping parameter type") from error
            offset += parameter_header_size
            if parameter_type is HousekeepingParameterType.BOOLEAN:
                if offset >= len(raw) or raw[offset] not in (0, 1):
                    raise ValueError("invalid boolean housekeeping value")
                value: HousekeepingValue = bool(raw[offset])
                offset += 1
            else:
                if offset + 8 > len(raw):
                    raise ValueError("housekeeping parameter value is truncated")
                value_bytes = raw[offset : offset + 8]
                if parameter_type is HousekeepingParameterType.SIGNED_INTEGER:
                    value = int.from_bytes(value_bytes, order, signed=True)
                else:
                    value = unpack(">d" if order == "big" else "<d", value_bytes)[0]
                offset += 8
            parameters.append(HousekeepingParameter(parameter_id, value))
        if offset != len(raw):
            raise ValueError("housekeeping report contains trailing bytes")
        return cls(structure_id, sequence, tuple(parameters))
