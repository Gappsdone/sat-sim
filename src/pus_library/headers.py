from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .bitfield import PacketSector
from .enums import DEFAULT_BYTE_ORDER, ByteOrder, PacketCategory, PacketType
from .time import CUCSatelliteTime, TimeSyncQuality


@dataclass
class PacketID(PacketSector):
    version: int = 0
    type: PacketType = PacketType.TELEMETRY
    has_data_field_header: bool = False
    prid: int = 0
    pcat: PacketCategory = PacketCategory.TIME
    NUMBER_OF_PACKET_ID_BYTES: ClassVar[int] = 2
    ACCEPTED_VERSION: ClassVar[int] = 0

    def __post_init__(self) -> None:
        self.type = PacketType(self.type)
        self.pcat = PacketCategory.pcat(int(self.pcat))

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        if self.type is PacketType.TELEMETRY and self.prid > 127:
            raise ValueError(
                "local PRID must be smaller than 128 while sending TM packets"
            )
        out = bytes(2)
        for offset, length, value in (
            (0, 3, self.version),
            (3, 1, int(self.type)),
            (4, 1, int(self.has_data_field_header)),
            (5, 7, self.prid),
            (12, 4, int(self.pcat)),
        ):
            out = self.set_parameter_value(out, offset, length, value, byte_order)
        return out

    @classmethod
    def from_bytes(
        cls, data: bytes, byte_order: ByteOrder = DEFAULT_BYTE_ORDER
    ) -> PacketID:
        if len(data) < 2:
            raise ValueError("Packet ID requires 2 bytes")
        return cls(
            cls.get_parameter_value(data, 0, 3, byte_order),
            PacketType(cls.get_parameter_value(data, 3, 1, byte_order)),
            bool(cls.get_parameter_value(data, 4, 1, byte_order)),
            cls.get_parameter_value(data, 5, 7, byte_order),
            PacketCategory.pcat(cls.get_parameter_value(data, 12, 4, byte_order)),
        )

    # Java-style accessors ease porting call sites.
    def getVersion(self) -> int:
        return self.version

    def getType(self) -> PacketType:
        return self.type

    def hasDataFieldHeader(self) -> bool:
        return self.has_data_field_header

    def getPRID(self) -> int:
        return self.prid

    def getPCAT(self) -> PacketCategory:
        return self.pcat


@dataclass
class PacketSequenceControl(PacketSector):
    sequence_flags: int = 0
    sequence_count: int = 0
    NUMBER_OF_PACKET_SEQUENCE_CONTROL_BYTES: ClassVar[int] = 2

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        out = self.set_parameter_value(bytes(2), 0, 2, self.sequence_flags, byte_order)
        return self.set_parameter_value(out, 2, 14, self.sequence_count, byte_order)

    @classmethod
    def from_bytes(
        cls, data: bytes, byte_order: ByteOrder = DEFAULT_BYTE_ORDER
    ) -> PacketSequenceControl:
        if len(data) < 2:
            raise ValueError("sequence control requires 2 bytes")
        return cls(
            cls.get_parameter_value(data, 0, 2, byte_order),
            cls.get_parameter_value(data, 2, 14, byte_order),
        )

    def getSequenceFlags(self) -> int:
        return self.sequence_flags

    def getSequenceCount(self) -> int:
        return self.sequence_count


@dataclass
class PacketHeader(PacketSector):
    packet_id: PacketID
    sequence_control: PacketSequenceControl
    packet_data_field_length: int
    NUMBER_OF_PACKET_HEADER_BYTES: ClassVar[int] = 6
    NUMBER_OF_DATA_FIELD_LENGTH_BYTES: ClassVar[int] = 2

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        if not 1 <= self.packet_data_field_length <= 65536:
            raise ValueError("packet data field length must be from 1 to 65536")
        length = (self.packet_data_field_length - 1).to_bytes(2, byte_order.value)
        return (
            self.packet_id.get_bytes(byte_order)
            + self.sequence_control.get_bytes(byte_order)
            + length
        )

    @classmethod
    def from_bytes(
        cls, data: bytes, byte_order: ByteOrder = DEFAULT_BYTE_ORDER
    ) -> PacketHeader:
        if len(data) < 6:
            raise ValueError("packet header requires 6 bytes")
        size = int.from_bytes(data[4:6], byte_order.value) + 1
        return cls(
            PacketID.from_bytes(data[:2], byte_order),
            PacketSequenceControl.from_bytes(data[2:4], byte_order),
            size,
        )

    def getPacketID(self) -> PacketID:
        return self.packet_id

    def getPacketSequenceControl(self) -> PacketSequenceControl:
        return self.sequence_control

    def getPacketDataFieldLength(self) -> int:
        return self.packet_data_field_length


class DataFieldHeader(PacketSector):
    """Common PUS secondary-header base (service type and subtype)."""

    def __init__(self, service_type: int, service_sub_type: int) -> None:
        self.service_type, self.service_sub_type = service_type, service_sub_type

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        raise NotImplementedError

    def getServiceType(self) -> int:
        return self.service_type

    def getServiceSubType(self) -> int:
        return self.service_sub_type


class TCDataFieldHeader(DataFieldHeader):
    NUMBER_OF_DATA_FIELD_HEADER_BYTES = 4
    ACCEPTED_VERSION = 1

    def __init__(
        self,
        ccsds_secondary_header_flag: int = 0,
        tc_pus_version_number: int = 1,
        request_acceptance_report: bool = True,
        request_start_of_execution_report: bool = False,
        request_progress_of_execution_report: bool = False,
        request_execution_completion_report: bool = True,
        service_type: int = 0,
        service_sub_type: int = 0,
        source_prid: int = 0,
    ) -> None:
        super().__init__(service_type, service_sub_type)
        self.ccsds_secondary_header_flag = ccsds_secondary_header_flag
        self.tc_pus_version_number = tc_pus_version_number
        self.request_acceptance_report = request_acceptance_report
        self.request_start_of_execution_report = request_start_of_execution_report
        self.request_progress_of_execution_report = request_progress_of_execution_report
        self.request_execution_completion_report = request_execution_completion_report
        self.source_prid = source_prid

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        flags = (self.ccsds_secondary_header_flag << 7) | (
            self.tc_pus_version_number << 4
        )
        for idx, value in enumerate(
            (
                self.request_acceptance_report,
                self.request_start_of_execution_report,
                self.request_progress_of_execution_report,
                self.request_execution_completion_report,
            )
        ):
            flags |= int(value) << (3 - idx)
        return bytes(
            (flags, self.service_type, self.service_sub_type, self.source_prid)
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> TCDataFieldHeader:
        if len(data) < 4:
            raise ValueError("TC data field header requires 4 bytes")
        flags = data[0]
        return cls(
            flags >> 7,
            (flags >> 4) & 7,
            bool(flags & 8),
            bool(flags & 4),
            bool(flags & 2),
            bool(flags & 1),
            data[1],
            data[2],
            data[3],
        )

    def getSourcePRID(self) -> int:
        return self.source_prid

    def getTCPUSVersionNumber(self) -> int:
        return self.tc_pus_version_number

    def getCCSDSSecondaryHeaderFlag(self) -> int:
        return self.ccsds_secondary_header_flag

    def requestsAcceptanceReport(self) -> bool:
        return self.request_acceptance_report

    def requestsStartOfExecutionReport(self) -> bool:
        return self.request_start_of_execution_report

    def requestsProgressOfExecutionReport(self) -> bool:
        return self.request_progress_of_execution_report

    def requestsExecutionCompletionReport(self) -> bool:
        return self.request_execution_completion_report


class TMDataFieldHeader(DataFieldHeader):
    NUMBER_OF_DATA_FIELD_HEADER_BYTES = 12
    ACCEPTED_VERSION = 1

    def __init__(
        self,
        tm_pus_version_number: int = 1,
        service_type: int = 0,
        service_sub_type: int = 0,
        destination_prid: int = 0,
        cuc_satellite_time: CUCSatelliteTime | None = None,
        time_sync_quality: TimeSyncQuality | None = None,
    ) -> None:
        super().__init__(service_type, service_sub_type)
        self.tm_pus_version_number = tm_pus_version_number
        self.destination_prid = destination_prid
        self.cuc_satellite_time = cuc_satellite_time or CUCSatelliteTime()
        self.time_sync_quality = time_sync_quality or TimeSyncQuality()

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        version = self.set_parameter_value(
            bytes(1), 1, 3, self.tm_pus_version_number, byte_order
        )
        return (
            version
            + bytes((self.service_type, self.service_sub_type, self.destination_prid))
            + self.cuc_satellite_time.get_bytes(byte_order)
            + self.time_sync_quality.get_bytes(byte_order)
        )

    @classmethod
    def from_bytes(
        cls, data: bytes, byte_order: ByteOrder = DEFAULT_BYTE_ORDER
    ) -> TMDataFieldHeader:
        if len(data) < 12:
            raise ValueError("TM data field header requires 12 bytes")
        return cls(
            cls.get_parameter_value(data[:1], 1, 3, byte_order),
            data[1],
            data[2],
            data[3],
            CUCSatelliteTime(data[4:11], byte_order),
            TimeSyncQuality.from_bytes(data[11:12]),
        )

    def getTMPUSVersionNumber(self) -> int:
        return self.tm_pus_version_number

    def getDestinationPRID(self) -> int:
        return self.destination_prid

    def getCUCSatelliteTime(self) -> CUCSatelliteTime:
        return self.cuc_satellite_time

    def getTimeSyncQuality(self) -> TimeSyncQuality:
        return self.time_sync_quality
