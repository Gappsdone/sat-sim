import asyncio
import socket

import pytest

from pus_library import ByteOrder, SourcePacket, service_data
from sat_sim_telemetry.pus_udp import PUSUDPChannel, PUSUDPConfiguration


def test_udp_channel_publishes_and_consumes_complete_pus_packets() -> None:
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(1.0)
    receiver_host, receiver_port = receiver.getsockname()
    channel = PUSUDPChannel(
        PUSUDPConfiguration(
            bind_host="127.0.0.1",
            bind_port=0,
            destination_host=str(receiver_host),
            destination_port=int(receiver_port),
        )
    )
    channel.open()
    packet = SourcePacket.get_source_packet(service_data(17, 1))

    try:
        channel.publish(packet)
        outbound, _address = receiver.recvfrom(65_507)
        assert SourcePacket(outbound, ByteOrder.BIG_ENDIAN).verify_crc()

        receiver.sendto(packet.get_bytes(), channel.local_address)
        inbound, source = asyncio.run(channel.consume())
        assert inbound.get_bytes() == packet.get_bytes()
        assert source[1] == receiver_port
    finally:
        channel.close()
        receiver.close()


def test_udp_channel_rejects_invalid_crc() -> None:
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    channel = PUSUDPChannel(PUSUDPConfiguration("127.0.0.1", 0, "127.0.0.1", 9))
    channel.open()
    packet = SourcePacket.get_source_packet(service_data(17, 1)).get_bytes()
    damaged = packet[:-1] + bytes((packet[-1] ^ 1,))

    try:
        sender.sendto(damaged, channel.local_address)
        with pytest.raises(ValueError, match="invalid CRC"):
            asyncio.run(channel.consume())
    finally:
        channel.close()
        sender.close()


def test_udp_channel_rejects_trailing_datagram_data() -> None:
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    channel = PUSUDPChannel(PUSUDPConfiguration("127.0.0.1", 0, "127.0.0.1", 9))
    channel.open()
    packet = SourcePacket.get_source_packet(service_data(17, 1)).get_bytes()

    try:
        sender.sendto(packet + b"extra", channel.local_address)
        with pytest.raises(ValueError, match="exactly one"):
            asyncio.run(channel.consume())
    finally:
        channel.close()
        sender.close()


def test_udp_configuration_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAT_SIM_PUS_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("SAT_SIM_PUS_BIND_PORT", "12001")
    monkeypatch.setenv("SAT_SIM_PUS_DESTINATION_HOST", "ground.example.test")
    monkeypatch.setenv("SAT_SIM_PUS_DESTINATION_PORT", "12002")

    configuration = PUSUDPConfiguration.from_environment()

    assert configuration == PUSUDPConfiguration(
        "0.0.0.0", 12001, "ground.example.test", 12002
    )
