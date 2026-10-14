from __future__ import annotations

from .bitfield import PacketSector
from .enums import DEFAULT_BYTE_ORDER, ByteOrder, PacketType
from .headers import (
    DataFieldHeader,
    PacketHeader,
    PacketID,
    PacketSequenceControl,
    TCDataFieldHeader,
    TMDataFieldHeader,
)
from .service import ServiceData, service_data
from .time import CUCSatelliteTime, TimeSyncQuality


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
