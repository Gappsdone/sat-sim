from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .enums import DEFAULT_BYTE_ORDER, ByteOrder


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
