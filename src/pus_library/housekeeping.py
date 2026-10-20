"""PUSUtilities-compatible application payloads for Service 3 reports."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import IntEnum
from struct import pack, unpack
from typing import Literal

from .enums import DEFAULT_BYTE_ORDER, ByteOrder, FaultID
from .packet import SourcePacket
from .service import ServiceData, service_data

HOUSEKEEPING_SERVICE_TYPE = 3
HOUSEKEEPING_DEFINITION_REPORT_SUBTYPE = 10
HOUSEKEEPING_REPORT_SUBTYPE = 25
MAX_HOUSEKEEPING_PARAMETERS = 55


class HousekeepingParameterType(IntEnum):
    """PUSUtilities parameter value types supported by this implementation."""

    SIGNED_INTEGER = 1
    FLOAT = 2


HousekeepingValue = int | float


@dataclass(frozen=True)
class HousekeepingStructureDefinition:
    """A PUSUtilities ``DataSST10`` housekeeping structure definition."""

    structure_id: int
    collection_interval: int
    parameter_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.structure_id <= 0xFF:
            raise ValueError("structure_id must fit in an unsigned 8-bit integer")
        if not 1 <= self.collection_interval <= 0xFFFF:
            raise ValueError(
                "collection_interval must fit in a nonzero unsigned 16-bit integer"
            )
        if not 1 <= len(self.parameter_ids) <= MAX_HOUSEKEEPING_PARAMETERS:
            raise ValueError("parameter_ids must contain between 1 and 55 entries")
        if any(not 0 <= item <= 0xFFFFFFFF for item in self.parameter_ids):
            raise ValueError("parameter IDs must fit in unsigned 32-bit integers")

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        """Serialize as SID, collection interval, NPAR, and parameter IDs."""
        order = _byte_order_name(byte_order)
        return (
            bytes((self.structure_id,))
            + self.collection_interval.to_bytes(2, order)
            + bytes((len(self.parameter_ids),))
            + b"".join(item.to_bytes(4, order) for item in self.parameter_ids)
        )

    def to_service_data(self) -> ServiceData:
        """Wrap this definition as TM(3,10)."""
        return service_data(
            HOUSEKEEPING_SERVICE_TYPE,
            HOUSEKEEPING_DEFINITION_REPORT_SUBTYPE,
            self.get_bytes(),
        )

    @classmethod
    def from_service_data(
        cls,
        data: ServiceData,
        byte_order: ByteOrder = DEFAULT_BYTE_ORDER,
    ) -> HousekeepingStructureDefinition:
        """Decode a PUSUtilities ``DataSST10`` payload."""
        if (
            data.service_type != HOUSEKEEPING_SERVICE_TYPE
            or data.service_sub_type != HOUSEKEEPING_DEFINITION_REPORT_SUBTYPE
        ):
            raise ValueError("service data must be a TM(3,10) definition report")
        if len(data.data) < 4:
            raise ValueError("housekeeping definition is shorter than its header")
        count = data.data[3]
        if len(data.data) != 4 + count * 4:
            raise ValueError("housekeeping definition length does not match NPAR")
        order = _byte_order_name(byte_order)
        return cls(
            data.data[0],
            int.from_bytes(data.data[1:3], order),
            tuple(
                int.from_bytes(data.data[offset : offset + 4], order)
                for offset in range(4, len(data.data), 4)
            ),
        )


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


class HousekeepingCommandError(ValueError):
    """A Service 3 management command failed validation or execution."""

    def __init__(self, fault: FaultID) -> None:
        super().__init__(fault.name)
        self.fault = fault


class HousekeepingStructure:
    """Registered PUSUtilities housekeeping structure and its subscribers.

    This is the deterministic simulator equivalent of
    ``HouseKeeping.Structure``. Scheduling remains with the simulation loop;
    this object owns the structure metadata and per-requester subscriptions.
    """

    def __init__(
        self,
        definition: HousekeepingStructureDefinition,
        parameter_definitions: tuple[HousekeepingParameterDefinition, ...],
        enabled_destinations: Iterable[int] = (),
    ) -> None:
        parameter_ids = tuple(item.parameter_id for item in parameter_definitions)
        if parameter_ids != definition.parameter_ids:
            raise ValueError(
                "parameter definitions must match the structure parameter IDs"
            )
        self.definition = definition
        self.parameter_definitions = parameter_definitions
        self.enabled_destinations = set(enabled_destinations)

    @property
    def structure_id(self) -> int:
        """Return the registered SID."""
        return self.definition.structure_id

    def add_subscriber(self, destination_prid: int) -> None:
        """Enable periodic reports for a requester PRID."""
        self.enabled_destinations.add(destination_prid)

    def remove_subscriber(self, destination_prid: int) -> None:
        """Disable periodic reports for a requester PRID."""
        self.enabled_destinations.discard(destination_prid)

    def report(self, values: Iterable[HousekeepingValue]) -> HousekeepingReport:
        """Build a TM(3,25) report in registered parameter order."""
        value_tuple = tuple(values)
        if len(value_tuple) != len(self.parameter_definitions):
            raise ValueError("housekeeping values must match the structure definition")
        return HousekeepingReport(
            self.structure_id,
            tuple(
                HousekeepingParameter(definition, value)
                for definition, value in zip(
                    self.parameter_definitions, value_tuple, strict=True
                )
            ),
        )


HousekeepingReportFactory = Callable[[HousekeepingStructure], HousekeepingReport]


class HousekeepingService:
    """PUSUtilities-compatible Service 3 structure registry and dispatcher."""

    def __init__(self, local_prid: int) -> None:
        self.local_prid = local_prid
        self._structures: dict[int, HousekeepingStructure] = {}

    def add_structure(self, structure: HousekeepingStructure) -> None:
        """Register or replace a structure by SID, as PUSUtilities does."""
        self._structures[structure.structure_id] = structure

    def get_structure(self, structure_id: int) -> HousekeepingStructure | None:
        """Return a registered structure, if present."""
        return self._structures.get(structure_id)

    def remove_structure(self, structure_id: int) -> None:
        """Remove a structure from the registry."""
        self._structures.pop(structure_id, None)

    def periodic_packets(
        self,
        report_factory: HousekeepingReportFactory,
        first_sequence: int,
    ) -> tuple[SourcePacket, ...]:
        """Create reports for every enabled structure/requester pair."""
        packets: list[SourcePacket] = []
        for structure_id in sorted(self._structures):
            structure = self._structures[structure_id]
            if not structure.enabled_destinations:
                continue
            report = report_factory(structure)
            for destination in sorted(structure.enabled_destinations):
                packets.append(
                    self._packet(report, first_sequence + len(packets), destination)
                )
        return tuple(packets)

    def handle_command(
        self,
        packet: SourcePacket,
        report_factory: HousekeepingReportFactory | None,
        sequence: int,
    ) -> SourcePacket | None:
        """Handle TC(3,5/6/9/136), returning telemetry where applicable."""
        data = packet.packet_data_field.data
        if (
            data.service_type != HOUSEKEEPING_SERVICE_TYPE
            or data.service_sub_type
            not in (
                5,
                6,
                9,
                136,
            )
        ):
            return None
        if len(data.data) != 1:
            raise HousekeepingCommandError(FaultID.LENGTH_DISCREP)
        structure = self.get_structure(data.data[0])
        if structure is None:
            raise HousekeepingCommandError(FaultID.SID_NOT_DEFINED)

        destination = packet.get_source_prid()
        if data.service_sub_type == 5:
            structure.add_subscriber(destination)
            return None
        if data.service_sub_type == 6:
            structure.remove_subscriber(destination)
            return None
        if data.service_sub_type == 9:
            return SourcePacket.get_source_packet(
                structure.definition.to_service_data(),
                local_prid=self.local_prid,
                destination_prid=destination,
                sequence_count=sequence,
            )
        if report_factory is None:
            raise HousekeepingCommandError(FaultID.REPORT_ABORTED)
        return self._packet(report_factory(structure), sequence, destination)

    def _packet(
        self, report: HousekeepingReport, sequence: int, destination_prid: int
    ) -> SourcePacket:
        return SourcePacket.get_source_packet(
            report.to_service_data(),
            local_prid=self.local_prid,
            destination_prid=destination_prid,
            sequence_count=sequence,
        )
