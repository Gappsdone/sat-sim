"""Python implementation of core PUS source-packet utilities.

The package is split by concern; this module re-exports the stable public API.
"""

from .bitfield import PacketSector
from .enums import (
    DEFAULT_BYTE_ORDER,
    ByteOrder,
    EventID,
    FaultID,
    PacketCategory,
    PacketType,
)
from .headers import (
    DataFieldHeader,
    PacketHeader,
    PacketID,
    PacketSequenceControl,
    TCDataFieldHeader,
    TMDataFieldHeader,
)
from .packet import PacketDataField, PacketErrorControl, SourcePacket
from .service import ServiceData, service_data
from .time import CUCSatelliteTime, TimeSyncQuality

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
