from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum

from .bitfield import PacketSector
from .enums import DEFAULT_BYTE_ORDER, ByteOrder


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
