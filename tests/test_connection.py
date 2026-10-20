from pus_library import ByteOrder, SourcePacket, service_data
from sat_sim.services.connection import handle_connection_test
from sat_sim.services.housekeeping import ISS_APPLICATION_PROCESS_ID


def test_connection_test_returns_empty_response_to_command_source() -> None:
    request = SourcePacket.get_source_packet(
        service_data(17, 1),
        local_prid=23,
        destination_prid=ISS_APPLICATION_PROCESS_ID,
    )

    response = handle_connection_test(request, sequence=42)

    assert response is not None
    wire_response = SourcePacket(response.get_bytes(), ByteOrder.BIG_ENDIAN)
    assert wire_response.is_tm_packet()
    assert wire_response.packet_data_field.data.service_type == 17
    assert wire_response.packet_data_field.data.service_sub_type == 2
    assert wire_response.packet_data_field.data.data == b""
    assert wire_response.get_source_prid() == ISS_APPLICATION_PROCESS_ID
    assert wire_response.get_destination_prid() == 23
    assert wire_response.packet_header.sequence_control.sequence_count == 42
    assert wire_response.verify_crc()


def test_connection_test_ignores_unrelated_packets() -> None:
    foreign_request = SourcePacket.get_source_packet(
        service_data(17, 1), local_prid=23, destination_prid=12
    )
    response = SourcePacket.get_source_packet(
        service_data(17, 2),
        local_prid=ISS_APPLICATION_PROCESS_ID,
        destination_prid=23,
    )

    assert handle_connection_test(foreign_request, sequence=0) is None
    assert handle_connection_test(response, sequence=0) is None
