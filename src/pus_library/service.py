from __future__ import annotations

from dataclasses import dataclass

from .bitfield import PacketSector
from .enums import DEFAULT_BYTE_ORDER, ByteOrder, PacketCategory, PacketType

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
