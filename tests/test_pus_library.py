from __future__ import annotations

import pytest

from pus_library import (
    ByteOrder,
    CUCSatelliteTime,
    EventID,
    FaultID,
    PacketCategory,
    PacketDataField,
    PacketErrorControl,
    PacketHeader,
    PacketID,
    PacketSequenceControl,
    PacketType,
    ServiceData,
    SourcePacket,
    TCDataFieldHeader,
    TimeSyncQuality,
    TMDataFieldHeader,
    service_data,
)


@pytest.mark.parametrize("order", list(ByteOrder))
def test_packet_id_and_sequence_control_round_trip(order: ByteOrder) -> None:
    packet_id = PacketID(
        0, PacketType.TELECOMMAND, True, 100, PacketCategory.TELECOMMAND
    )
    control = PacketSequenceControl(3, 0x1234)
    assert PacketID.from_bytes(packet_id.get_bytes(order), order) == packet_id
    assert PacketSequenceControl.from_bytes(control.get_bytes(order), order) == control


def test_packet_header_uses_wire_length_minus_one() -> None:
    header = PacketHeader(
        PacketID(0, PacketType.TELEMETRY, True, 4, PacketCategory.EVENT),
        PacketSequenceControl(3, 0),
        17,
    )
    raw = header.get_bytes()
    assert len(raw) == 6
    assert raw[4:] == b"\x00\x10"
    assert PacketHeader.from_bytes(raw).packet_data_field_length == 17


def test_tc_secondary_header_round_trip_and_flags() -> None:
    header = TCDataFieldHeader(0, 1, True, False, True, True, 17, 1, 5)
    encoded = header.get_bytes()
    assert encoded == bytes((0x1B, 17, 1, 5))
    decoded = TCDataFieldHeader.from_bytes(encoded)
    assert decoded.getServiceType() == 17
    assert decoded.getServiceSubType() == 1
    assert decoded.getSourcePRID() == 5
    assert decoded.requestsAcceptanceReport()
    assert not decoded.requestsStartOfExecutionReport()
    assert decoded.requestsProgressOfExecutionReport()
    assert decoded.requestsExecutionCompletionReport()


def test_tm_secondary_header_round_trip() -> None:
    quality = TimeSyncQuality(
        TimeSyncQuality.TimeType.ON_BOARD_TIME,
        TimeSyncQuality.SyncSource.EXTERNAL,
        TimeSyncQuality.SyncMethod.ONE_HZ_PULSE,
        TimeSyncQuality.SyncStatus.SYNC,
        True,
    )
    header = TMDataFieldHeader(1, 5, 2, 9, CUCSatelliteTime(1234, 0.5), quality)
    encoded = header.get_bytes()
    assert len(encoded) == 12
    assert TMDataFieldHeader.from_bytes(encoded).get_bytes() == encoded


def test_cuc_time_encodes_and_decodes_fine_fraction() -> None:
    raw = CUCSatelliteTime(7, 0.25).get_bytes()
    assert raw[:4] == b"\x00\x00\x00\x07"
    restored = CUCSatelliteTime(raw)
    assert restored.getCoarseTime() == 7
    assert restored.getFineTime() == 0.25
    assert restored.toUNIXTimestamp() == 7


def test_packet_creation_crc_round_trip_and_corruption_detection() -> None:
    data = service_data(17, 1)
    packet = SourcePacket.get_source_packet(data, local_prid=3, destination_prid=7)
    raw = packet.get_bytes()
    assert len(raw) == 6 + packet.packet_header.packet_data_field_length
    assert PacketErrorControl.verify_crc(raw)
    parsed = SourcePacket(raw, ByteOrder.BIG_ENDIAN)
    assert parsed.get_packet_type() is PacketType.TELECOMMAND
    assert parsed.get_source_prid() == 3
    assert parsed.get_destination_prid() == 7
    assert parsed.get_packet_data_field().data.service_type == 17
    damaged = raw[:-1] + bytes((raw[-1] ^ 1,))
    assert not PacketErrorControl.verify_crc(damaged)


def test_tm_packet_serialization_round_trip() -> None:
    packet = SourcePacket.get_source_packet(
        service_data(5, 1, b"\x01\x02"), local_prid=9, destination_prid=11
    )
    restored = SourcePacket(packet.get_bytes(), ByteOrder.BIG_ENDIAN)
    assert restored.is_tm_packet()
    assert restored.get_source_prid() == 9
    assert restored.get_destination_prid() == 11
    assert restored.packet_data_field.data.data == b"\x01\x02"
    assert restored.verify_crc()


def test_unknown_service_metadata_is_rejected_by_factory() -> None:
    with pytest.raises(ValueError, match="unsupported PUS service"):
        service_data(250, 250)


def test_crc_known_vector_and_fault_enum_fallback() -> None:
    assert PacketErrorControl._crc_raw(b"123456789") == 0x29B1
    assert FaultID.get_from(773) is FaultID.REPORT_ABORTED
    assert FaultID.get_from(1) is FaultID.NOT_SET


def test_tm_prid_range_is_checked() -> None:
    packet_id = PacketID(0, PacketType.TELEMETRY, False, 128, PacketCategory.TIME)
    with pytest.raises(ValueError, match="smaller than 128"):
        packet_id.get_bytes()


@pytest.mark.parametrize(
    ("service_type", "subtypes"),
    [
        (
            1,
            [
                (1, PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
                (2, PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
                (7, PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
                (8, PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
            ],
        ),
        (
            3,
            [
                (1, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (3, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (5, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (6, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (9, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (10, PacketType.TELEMETRY, PacketCategory.TABLE),
                (25, PacketType.TELEMETRY, PacketCategory.TABLE),
                (136, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
            ],
        ),
        (
            5,
            [
                (1, PacketType.TELEMETRY, PacketCategory.EVENT),
                (2, PacketType.TELEMETRY, PacketCategory.EVENT),
                (3, PacketType.TELEMETRY, PacketCategory.EVENT),
                (4, PacketType.TELEMETRY, PacketCategory.EVENT),
                (5, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (6, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
            ],
        ),
        (8, [(1, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND)]),
        (
            9,
            [
                (2, PacketType.TELEMETRY, PacketCategory.TIME),
                (128, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
            ],
        ),
        (
            12,
            [
                (1, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (2, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
            ],
        ),
        (
            17,
            [
                (1, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (2, PacketType.TELEMETRY, PacketCategory.ACKNOWLEDGE),
            ],
        ),
        (
            140,
            [
                (1, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (2, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (3, PacketType.TELEMETRY, PacketCategory.TABLE),
                (31, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (32, PacketType.TELECOMMAND, PacketCategory.TELECOMMAND),
                (33, PacketType.TELEMETRY, PacketCategory.TABLE),
                (34, PacketType.TELEMETRY, PacketCategory.TABLE),
            ],
        ),
    ],
)
def test_service_metadata_parity(
    service_type: int,
    subtypes: list[tuple[int, PacketType, PacketCategory]],
) -> None:
    for subtype, packet_type, category in subtypes:
        service = service_data(service_type, subtype, b"payload")
        assert service.packet_type is packet_type
        assert service.packet_category is category
        assert service.data == b"payload"


def test_event_and_fault_enum_lookup_compatibility() -> None:
    assert len(EventID) == 3
    assert EventID.get_from(1) is EventID.EID_DUMMY
    assert EventID.get_from(0x1234) is EventID.EID_PCDU_EQUIPMENT_SWITCH_STATUS_CHANGE


def test_manual_packetdatafield_and_packet_constructor() -> None:
    payload = ServiceData(b"hello", PacketType.TELEMETRY, PacketCategory.EVENT, 5, 1)
    secondary = TMDataFieldHeader(1, 5, 1, 3)
    field = PacketDataField(secondary, payload)
    header = PacketHeader(
        PacketID(0, PacketType.TELEMETRY, True, 2, PacketCategory.EVENT),
        PacketSequenceControl(3, 4),
        field.get_number_of_bytes(),
    )
    packet = SourcePacket(header, field)
    assert packet.get_bytes()[:6] == header.get_bytes()
    assert packet.verify_crc()
