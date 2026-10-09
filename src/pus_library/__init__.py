"""Python implementation of the core PUS source-packet utilities.

The wire representation follows the former Airbus ``PUSLibrary`` Java API:
6-byte CCSDS primary header, optional PUS data-field header, application data,
and a CRC-16/CCITT-FALSE packet error control field.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, IntEnum
from typing import ClassVar


class ByteOrder(Enum):
    BIG_ENDIAN = "big"
    LITTLE_ENDIAN = "little"


DEFAULT_BYTE_ORDER = ByteOrder.BIG_ENDIAN


class PacketType(IntEnum):
    TELEMETRY = 0
    TELECOMMAND = 1

    @property
    def short_name(self) -> str:
        return "TM" if self is PacketType.TELEMETRY else "TC"

    @classmethod
    def type(cls, value: int) -> PacketType:
        return cls(value)


class PacketCategory(IntEnum):
    TIME = 0
    ACKNOWLEDGE = 1
    HK_RT = 2
    TABLE = 3
    HK_PB = 4
    UNKNOWN = 6
    EVENT = 7
    DIAGNOSTIC = 8
    DUMP = 9
    TELECOMMAND = 12
    OCC_EGSE = 14
    IDLE = 15

    @classmethod
    def pcat(cls, value: int) -> PacketCategory:
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN


class FaultID(IntEnum):
    SYS_FID_INVALID_VALUE = 0x0100
    PRID_NOT_RESPONDING = 0x0101
    PRID_COMMUNICATION_TIMEOUT = 0x0102
    PRID_COMMUNICATION_ERROR = 0x0103
    PRID_COMMUNICATION_LINK_LOST = 0x0104
    PRID_REMOTE_ERROR = 0x0105
    PRID_INVALID_SERVICE_TYPE = 0x0106
    ILLEGAL_APID = 0x0200
    INCOMPLETE_OR_INVALID_LENGTH_PACKET = 0x0201
    INCORRECT_CHECKSUM = 0x0202
    ILLEGAL_PACKET_TYPE = 0x0203
    ILLEGAL_PACKET_SUBTYPE = 0x0204
    ILLEGAL_OR_INCONSISTENT_APPLICATION_DATA = 0x0205
    ILLEGAL_TCS_SF = 0x0206
    ILLEGAL_TCS_MAP_ID = 0x0207
    INVALID_NPAR = 0x0208
    NPAR_LENGTH_DISCREP = 0x0209
    INVALID_SID = 0x020A
    INVALID_COLL_INT = 0x020B
    MAX_HK_NB_EXCEEDED = 0x020C
    MAX_TOTAL_SID_NB = 0x020D
    INVALID_PAR_ID = 0x020E
    UNKNOWN_SID = 0x020F
    SID_ENABLED = 0x0210
    SID_DEFINED = 0x0211
    SID_NOT_DEFINED = 0x0212
    TM_SIZE_EXCEEDED = 0x0213
    SID_UNKNOWN_EID = 0x0214
    INVALID_NFA = 0x0215
    NREP_INCO_INTERVAL = 0x0216
    UNKNOWN_FORW_PID = 0x0220
    FORW_INVALID_RID = 0x0221
    ILLEGAL_VERSION = 0x0222
    ILLEGAL_P_TYPE = 0x0223
    ILLEGAL_DFHF = 0x0224
    UNKNOWN_PRID = 0x0225
    ILLEGAL_PCAT = 0x0226
    ILLEGAL_SF = 0x0227
    ILLEGAL_NPAR = 0x0228
    INVALID_PLENGTH = 0x0229
    LENGTH_DISCREP = 0x022A
    ILLEGAL_SHF = 0x022B
    ILLEGAL_TC_PUS = 0x022C
    UNKNOWN_S_TYPE = 0x0300
    UNKNOWN_S_SUBTYPE = 0x0301
    CS_DISCREP = 0x0302
    TC_INBUF_OVERFLOW = 0x0303
    MTU_TOO_SMALL = 0x0304
    REPORT_ABORTED = 0x0305
    DUMP_ERROR = 0x0400
    TC_POOL_OVERFLOW = 0x0401
    ACT_SERVICE_ENABLED = 0x0402
    DETECTION_OVERFLOW = 0x0403
    UNKNOWN_ACTION = 0x0404
    ACTION_ACTIVE = 0x0405
    NACT_LEN_DISCREP = 0x0406
    FORBIDDEN_EID = 0x0407
    NOT_SET = 0xFFFF

    @classmethod
    def get_from(cls, value: int) -> FaultID:
        try:
            return cls(value)
        except ValueError:
            return cls.NOT_SET


@dataclass
class PacketSector:
    INVALID_VALUE: ClassVar[int] = -(2**31)

    @staticmethod
    def get_parameter_value(
        data: bytes,
        bit_offset: int,
        bit_length: int,
        byte_order: ByteOrder = DEFAULT_BYTE_ORDER,
    ) -> int:
        if bit_length < 1 or bit_length > 32:
            raise ValueError("bit_length must be between 1 and 32")
        if bit_offset < 0 or bit_offset + bit_length > len(data) * 8:
            raise IndexError("bit range exceeds input")
        stream = data if byte_order is ByteOrder.BIG_ENDIAN else data[::-1]
        value = int.from_bytes(stream, "big")
        shift = len(stream) * 8 - bit_offset - bit_length
        return (value >> shift) & ((1 << bit_length) - 1)

    @staticmethod
    def set_parameter_value(
        data: bytes,
        bit_offset: int,
        bit_length: int,
        value: int,
        byte_order: ByteOrder = DEFAULT_BYTE_ORDER,
    ) -> bytes:
        if bit_length < 1 or bit_length > 32:
            raise ValueError("bit_length must be between 1 and 32")
        if bit_offset < 0 or bit_offset + bit_length > len(data) * 8:
            raise IndexError("bit range exceeds output")
        if value < 0 or value >= 1 << bit_length:
            raise ValueError(f"value does not fit in {bit_length} bits")
        stream = bytearray(data if byte_order is ByteOrder.BIG_ENDIAN else data[::-1])
        total = len(stream) * 8
        shift = total - bit_offset - bit_length
        mask = ((1 << bit_length) - 1) << shift
        current = int.from_bytes(stream, "big")
        stream[:] = ((current & ~mask) | (value << shift)).to_bytes(len(stream), "big")
        result = bytes(stream)
        return result if byte_order is ByteOrder.BIG_ENDIAN else result[::-1]

    @staticmethod
    def byte_array_to_string(data: bytes) -> str:
        return "".join(f"{byte:02X} " for byte in data)


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


class CUCSatelliteTime(PacketSector):
    CUC_EPOCH_UTC = 0
    NUMBER_OF_COARSE_TIME_BYTES = 4
    NUMBER_OF_FINE_TIME_BYTES = 3
    NUMBER_OF_SATELLITE_TIME_BYTES = 7
    epoch = CUC_EPOCH_UTC

    def __init__(
        self,
        coarse_time: int | bytes = 0,
        fine_time: float | ByteOrder = 0.0,
        byte_order: ByteOrder = DEFAULT_BYTE_ORDER,
    ) -> None:
        if isinstance(coarse_time, (bytes, bytearray)):
            raw = bytes(coarse_time)
            if len(raw) < 7:
                raise ValueError("CUC time requires 7 bytes")
            order = fine_time if isinstance(fine_time, ByteOrder) else byte_order
            self.coarse_time = int.from_bytes(raw[:4], order.value)
            self.fine_time = int.from_bytes(raw[4:7], order.value) / float(1 << 24)
        else:
            self.coarse_time = int(coarse_time)
            if isinstance(fine_time, ByteOrder):
                raise TypeError("fine_time must be a fraction, not a ByteOrder")
            if not 0 <= fine_time < 1:
                raise ValueError("fine time must be in [0,1)")
            self.fine_time = float(fine_time)

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        coarse = self.coarse_time.to_bytes(4, byte_order.value)
        fine_int = int(self.fine_time * (1 << 24))
        return coarse + fine_int.to_bytes(3, byte_order.value)

    def toUNIXTimestamp(self) -> int:
        return self.coarse_time + self.epoch

    @classmethod
    def now(cls) -> CUCSatelliteTime:
        timestamp = datetime.now(UTC).timestamp() - cls.epoch
        coarse = int(timestamp)
        return cls(coarse, timestamp - coarse)

    @classmethod
    def getEpoch(cls) -> int:
        return cls.epoch

    @classmethod
    def setEpoch(cls, epoch: int) -> None:
        cls.epoch = epoch

    def getCoarseTime(self) -> int:
        return self.coarse_time

    def getFineTime(self) -> float:
        return self.fine_time


class TimeSyncQuality(PacketSector):
    class TimeType(IntEnum):
        S_C_ELAPSED_TIME = 0
        ON_BOARD_TIME = 1

    class SyncSource(IntEnum):
        INTERNAL = 0
        EXTERNAL = 1

    class SyncMethod(IntEnum):
        MIL_BUS_MAJOR = 0
        ONE_HZ_PULSE = 1

    class SyncStatus(IntEnum):
        NO_SYNC = 0
        SYNC = 1

    def __init__(
        self,
        time_type: TimeType | int = TimeType.S_C_ELAPSED_TIME,
        sync_source: SyncSource | int = SyncSource.INTERNAL,
        sync_method: SyncMethod | int = SyncMethod.MIL_BUS_MAJOR,
        sync_status: SyncStatus | int = SyncStatus.NO_SYNC,
        synchronization_enabled: bool = False,
    ) -> None:
        self.time_type = self.TimeType(time_type)
        self.sync_source = self.SyncSource(sync_source)
        self.sync_method = self.SyncMethod(sync_method)
        self.sync_status = self.SyncStatus(sync_status)
        self.synchronization_enabled = synchronization_enabled

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        val = (
            (int(self.time_type) << 4)
            | (int(self.sync_source) << 3)
            | (int(self.sync_method) << 2)
            | (int(self.sync_status) << 1)
            | int(self.synchronization_enabled)
        )
        return bytes((val,))

    @classmethod
    def from_bytes(cls, data: bytes) -> TimeSyncQuality:
        if not data:
            raise ValueError("time sync quality requires one byte")
        b = data[0]
        return cls((b >> 4) & 1, (b >> 3) & 1, (b >> 2) & 1, (b >> 1) & 1, bool(b & 1))

    def getTimeType(self) -> TimeType:
        return self.time_type

    def getSyncSource(self) -> SyncSource:
        return self.sync_source

    def getSyncMethod(self) -> SyncMethod:
        return self.sync_method

    def getSyncStatus(self) -> SyncStatus:
        return self.sync_status

    def getSynchronizationEnabled(self) -> bool:
        return self.synchronization_enabled


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


@dataclass
class ServiceData(PacketSector):
    data: bytes = b""
    packet_type: PacketType = PacketType.TELEMETRY
    packet_category: PacketCategory = PacketCategory.UNKNOWN
    service_type: int = 0
    service_sub_type: int = 0

    def __post_init__(self) -> None:
        self.data = bytes(self.data)
        self.packet_type = PacketType(self.packet_type)
        self.packet_category = PacketCategory.pcat(int(self.packet_category))

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        return self.data

    def getByteOrder(self) -> ByteOrder:
        return DEFAULT_BYTE_ORDER


# Wire-level service type/subtype classification sourced from the Java service classes.
_SERVICE_META = {
    (1, 1): (PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
    (1, 2): (PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
    (1, 7): (PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
    (1, 8): (PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
    (3, 1): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (3, 3): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (3, 5): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (3, 6): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (3, 9): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (3, 10): (PacketType.TELEMETRY, PacketCategory.TABLE),
    (3, 25): (PacketType.TELEMETRY, PacketCategory.TABLE),
    (3, 136): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (5, 1): (PacketType.TELEMETRY, PacketCategory.EVENT),
    (5, 2): (PacketType.TELEMETRY, PacketCategory.EVENT),
    (5, 3): (PacketType.TELEMETRY, PacketCategory.EVENT),
    (5, 4): (PacketType.TELEMETRY, PacketCategory.EVENT),
    (5, 5): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (5, 6): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (8, 1): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (9, 2): (PacketType.TELEMETRY, PacketCategory.TIME),
    (9, 128): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (12, 1): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (12, 2): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (17, 1): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (17, 2): (PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
    (140, 1): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (140, 2): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (140, 3): (PacketType.TELEMETRY, PacketCategory.TABLE),
    (140, 31): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (140, 32): (PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
    (140, 33): (PacketType.TELEMETRY, PacketCategory.TABLE),
    (140, 34): (PacketType.TELEMETRY, PacketCategory.TABLE),
}


def service_data(
    service_type: int, service_sub_type: int, data: bytes = b""
) -> ServiceData:
    """Create a service payload object for a known ST/SST pair."""
    try:
        packet_type, pcat = _SERVICE_META[(service_type, service_sub_type)]
    except KeyError as exc:
        raise ValueError(
            f"unsupported PUS service ({service_type}, {service_sub_type})"
        ) from exc
    return ServiceData(bytes(data), packet_type, pcat, service_type, service_sub_type)


class PacketErrorControl(PacketSector):
    NUMBER_OF_PACKET_ERROR_CONTROL_BYTES = 2

    @staticmethod
    def _crc_raw(data: bytes) -> int:
        crc = 0xFFFF
        for value in data:
            for bit in range(8):
                mix = ((value << bit) & 0x80) ^ ((crc & 0x8000) >> 8)
                crc = ((crc << 1) ^ (0x1021 if mix else 0)) & 0xFFFF
        return crc

    def __init__(self, crc: int) -> None:
        self.crc = crc

    @staticmethod
    def calculate_crc(packet_bytes: bytes) -> int:
        """CRC-16/CCITT-FALSE, polynomial 0x1021, initial value 0xffff."""
        if len(packet_bytes) < 8:
            raise ValueError(
                "a PUS packet must include its 6-byte header and 2-byte PEC"
            )
        header = PacketHeader.from_bytes(packet_bytes[:6])
        packet_len = min(len(packet_bytes), 6 + header.packet_data_field_length)
        return PacketErrorControl._crc_raw(packet_bytes[: packet_len - 2])

    @staticmethod
    def get_packet_crc(packet_bytes: bytes) -> int:
        if len(packet_bytes) < 8:
            raise ValueError("packet too short for PEC")
        header = PacketHeader.from_bytes(packet_bytes[:6])
        packet_len = min(len(packet_bytes), 6 + header.packet_data_field_length)
        return int.from_bytes(packet_bytes[packet_len - 2 : packet_len], "big")

    @classmethod
    def verify_crc(cls, packet_bytes: bytes) -> bool:
        try:
            return cls.get_packet_crc(packet_bytes) == cls.calculate_crc(packet_bytes)
        except (ValueError, IndexError, OverflowError):
            return False

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        return self.crc.to_bytes(2, byte_order.value)

    calculateCRC = calculate_crc
    getPacketCRC = get_packet_crc
    verifyCRC = verify_crc

    def getCRC(self) -> int:
        return self.crc


class PacketDataField(PacketSector):
    def __init__(
        self,
        data_field_header: DataFieldHeader | None,
        data: ServiceData,
        packet_error_control: PacketErrorControl | None = None,
    ) -> None:
        self.data_field_header, self.data, self.packet_error_control = (
            data_field_header,
            data,
            packet_error_control,
        )

    def get_number_of_bytes(self) -> int:
        return len(self.get_bytes())

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        header = (
            self.data_field_header.get_bytes(byte_order)
            if self.data_field_header
            else b""
        )
        return (
            header
            + self.data.get_bytes(byte_order)
            + (
                self.packet_error_control.get_bytes(byte_order)
                if self.packet_error_control
                else b"\x00\x00"
            )
        )

    def getDataFieldHeader(self) -> DataFieldHeader | None:
        return self.data_field_header

    def getData(self) -> ServiceData:
        return self.data

    def getPacketErrorControl(self) -> PacketErrorControl | None:
        return self.packet_error_control

    getNumberOfBytes = get_number_of_bytes


class SourcePacket(PacketSector):
    DEFAULT_BYTE_ORDER = DEFAULT_BYTE_ORDER
    MAX_PACKET_LENGTH_TM = 65542
    MAX_PACKET_LENGTH_TC = 246
    DEFAULT_TC_ACKNOWLEDGEMENT_FLAGS = 0b1111

    def __init__(
        self,
        packet_header: PacketHeader | bytes,
        packet_data_field: PacketDataField | ByteOrder,
        byte_order: ByteOrder = DEFAULT_BYTE_ORDER,
    ) -> None:
        self.received_bytes: bytes | None = None
        if isinstance(packet_header, (bytes, bytearray)):
            raw = bytes(packet_header)
            order = (
                packet_data_field
                if isinstance(packet_data_field, ByteOrder)
                else byte_order
            )
            self.received_bytes = raw
            header = PacketHeader.from_bytes(raw[:6], order)
            if len(raw) < 6 + header.packet_data_field_length:
                raise ValueError(
                    "source packet is shorter than the data-field length in its header"
                )
            field = raw[6 : 6 + header.packet_data_field_length]
            parsed = self._parse_data_field(header, field, order)
            self.packet_header, self.packet_data_field = header, parsed
        else:
            self.packet_header = packet_header
            if not isinstance(packet_data_field, PacketDataField):
                raise TypeError("packet_data_field must be PacketDataField")
            self.packet_data_field = packet_data_field
            if self.packet_data_field.packet_error_control is None:
                # CRC covers the header and data, excluding the trailing PEC.
                body = self.packet_header.get_bytes(
                    byte_order
                ) + self.packet_data_field.get_bytes(byte_order)
                self.packet_data_field.packet_error_control = PacketErrorControl(
                    self._crc_raw(body[:-2])
                )

    @staticmethod
    def _crc_raw(data: bytes) -> int:
        crc = 0xFFFF
        for value in data:
            for bit in range(8):
                mix = ((value << bit) & 0x80) ^ ((crc & 0x8000) >> 8)
                crc = ((crc << 1) ^ (0x1021 if mix else 0)) & 0xFFFF
        return crc

    @staticmethod
    def _parse_data_field(
        header: PacketHeader, raw: bytes, byte_order: ByteOrder
    ) -> PacketDataField:
        if len(raw) < 2:
            raise ValueError("packet data field must contain at least PEC")
        packet_id = header.packet_id
        data = raw[:-2]
        dfh: DataFieldHeader | None = None
        if packet_id.has_data_field_header:
            if packet_id.type is PacketType.TELECOMMAND:
                dfh = TCDataFieldHeader.from_bytes(data)
            else:
                dfh = TMDataFieldHeader.from_bytes(data, byte_order)
            payload = data[len(dfh.get_bytes(byte_order)) :]
        else:
            payload = data
        st, sst = (dfh.service_type, dfh.service_sub_type) if dfh else (0, 0)
        try:
            obj = service_data(st, sst, payload)
        except ValueError:
            obj = ServiceData(payload, packet_id.type, packet_id.pcat, st, sst)
        return PacketDataField(
            dfh, obj, PacketErrorControl(int.from_bytes(raw[-2:], byte_order.value))
        )

    def get_bytes(self, byte_order: ByteOrder = DEFAULT_BYTE_ORDER) -> bytes:
        return self.packet_header.get_bytes(
            byte_order
        ) + self.packet_data_field.get_bytes(byte_order)

    @classmethod
    def get_source_packet(
        cls,
        data: ServiceData,
        service_type: int | None = None,
        service_sub_type: int | None = None,
        local_prid: int = 0,
        destination_prid: int = 0,
    ) -> SourcePacket:
        st = data.service_type if service_type is None else service_type
        sst = data.service_sub_type if service_sub_type is None else service_sub_type
        dfh: DataFieldHeader
        if data.packet_type is PacketType.TELECOMMAND:
            dfh = TCDataFieldHeader(0, 1, True, True, True, True, st, sst, local_prid)
            prid = destination_prid
        else:
            dfh = TMDataFieldHeader(
                1, st, sst, destination_prid, CUCSatelliteTime.now(), TimeSyncQuality()
            )
            prid = local_prid
        packet_id = PacketID(0, data.packet_type, True, prid, data.packet_category)
        field = PacketDataField(dfh, data)
        header = PacketHeader(
            packet_id,
            PacketSequenceControl(3, 0),
            len(dfh.get_bytes()) + len(data.data) + 2,
        )
        return cls(header, field)

    def get_packet_type(self) -> PacketType:
        return self.packet_header.packet_id.type

    def get_packet_data_field(self) -> PacketDataField:
        return self.packet_data_field

    def is_tc_packet(self) -> bool:
        return self.get_packet_type() is PacketType.TELECOMMAND

    def is_tm_packet(self) -> bool:
        return self.get_packet_type() is PacketType.TELEMETRY

    def get_source_prid(self) -> int:
        dfh = self.packet_data_field.data_field_header
        return (
            dfh.source_prid
            if isinstance(dfh, TCDataFieldHeader)
            else self.packet_header.packet_id.prid
        )

    def get_destination_prid(self) -> int:
        dfh = self.packet_data_field.data_field_header
        return (
            dfh.destination_prid
            if isinstance(dfh, TMDataFieldHeader)
            else self.packet_header.packet_id.prid
        )

    def verify_crc(self) -> bool:
        return PacketErrorControl.verify_crc(self.get_bytes())

    def getPacketHeader(self) -> PacketHeader:
        return self.packet_header

    def getPacketDataField(self) -> PacketDataField:
        return self.packet_data_field

    getPacketType = get_packet_type
    isTCPacket = is_tc_packet
    isTMPacket = is_tm_packet
    getSourcePRID = get_source_prid
    getDestinationPRID = get_destination_prid
    getBytes = get_bytes
    getSourcePacket = get_source_packet


# Java enum had three known IDs; parser callables are omitted.
class EventID(IntEnum):
    EID_IOH_STATE_TRANSITION_FAILED = 0xF100
    EID_PCDU_EQUIPMENT_SWITCH_STATUS_CHANGE = 0x1234
    EID_DUMMY = 0xFFFF

    @classmethod
    def get_from(cls, value: int) -> EventID:
        try:
            return cls(value)
        except ValueError:
            return cls.EID_DUMMY

    getFrom = get_from


# Public Java-like aliases and expected conventional Python spellings.
DataFieldHeaderTC = TCDataFieldHeader
DataFieldHeaderTM = TMDataFieldHeader

__all__ = [
    "DEFAULT_BYTE_ORDER",
    "ByteOrder",
    "CUCSatelliteTime",
    "DataFieldHeader",
    "DataFieldHeaderTC",
    "DataFieldHeaderTM",
    "EventID",
    "FaultID",
    "PacketCategory",
    "PacketDataField",
    "PacketErrorControl",
    "PacketHeader",
    "PacketID",
    "PacketSector",
    "PacketSequenceControl",
    "PacketType",
    "ServiceData",
    "SourcePacket",
    "TCDataFieldHeader",
    "TMDataFieldHeader",
    "TimeSyncQuality",
    "service_data",
]
