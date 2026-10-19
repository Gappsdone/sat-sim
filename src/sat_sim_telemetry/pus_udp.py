"""Bidirectional UDP transport for complete PUS source packets."""

from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass

from pus_library import ByteOrder, SourcePacket

MAX_UDP_PAYLOAD = 65_507


@dataclass(frozen=True)
class PUSUDPConfiguration:
    """Local bind and remote destination for the PUS UDP channel."""

    bind_host: str
    bind_port: int
    destination_host: str
    destination_port: int

    def __post_init__(self) -> None:
        for name, port in (
            ("bind_port", self.bind_port),
            ("destination_port", self.destination_port),
        ):
            if not 0 <= port <= 65_535:
                raise ValueError(f"{name} must be between 0 and 65535")

    @classmethod
    def from_environment(cls) -> PUSUDPConfiguration:
        """Read deployment-specific addresses from the process environment."""
        return cls(
            bind_host=os.getenv("SAT_SIM_PUS_BIND_HOST", "127.0.0.1"),
            bind_port=_environment_port("SAT_SIM_PUS_BIND_PORT", 10_025),
            destination_host=os.getenv("SAT_SIM_PUS_DESTINATION_HOST", "127.0.0.1"),
            destination_port=_environment_port("SAT_SIM_PUS_DESTINATION_PORT", 10_015),
        )


def _environment_port(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


class PUSUDPChannel:
    """Send and receive one complete CRC-protected PUS packet per datagram."""

    def __init__(self, configuration: PUSUDPConfiguration) -> None:
        self.configuration = configuration
        self._socket: socket.socket | None = None

    @property
    def local_address(self) -> tuple[str, int]:
        """Return the bound IPv4 address after the channel has opened."""
        if self._socket is None:
            raise RuntimeError("PUS UDP channel is not open")
        host, port = self._socket.getsockname()
        return str(host), int(port)

    def open(self) -> None:
        """Create and bind the nonblocking datagram socket."""
        if self._socket is not None:
            raise RuntimeError("PUS UDP channel is already open")
        channel = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            channel.bind((self.configuration.bind_host, self.configuration.bind_port))
            channel.setblocking(False)
        except BaseException:
            channel.close()
            raise
        self._socket = channel

    def publish(self, packet: SourcePacket) -> None:
        """Send one source packet as one UDP datagram."""
        if self._socket is None:
            raise RuntimeError("PUS UDP channel is not open")
        payload = packet.get_bytes()
        if len(payload) > MAX_UDP_PAYLOAD:
            raise ValueError("PUS packet exceeds the maximum UDP payload")
        self._socket.sendto(
            payload,
            (
                self.configuration.destination_host,
                self.configuration.destination_port,
            ),
        )

    async def consume(self) -> tuple[SourcePacket, tuple[str, int]]:
        """Receive, parse, and CRC-validate one PUS packet datagram."""
        if self._socket is None:
            raise RuntimeError("PUS UDP channel is not open")
        payload, address = await asyncio.get_running_loop().sock_recvfrom(
            self._socket, MAX_UDP_PAYLOAD
        )
        packet = SourcePacket(payload, ByteOrder.BIG_ENDIAN)
        if packet.get_bytes() != payload:
            raise ValueError("UDP datagram must contain exactly one PUS packet")
        if not packet.verify_crc():
            raise ValueError("received PUS packet has an invalid CRC")
        host, port = address
        return packet, (str(host), int(port))

    def close(self) -> None:
        """Close the channel; repeated calls are harmless."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None
