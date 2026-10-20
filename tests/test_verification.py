import pytest

from pus_library import (
    ByteOrder,
    FaultID,
    PacketCategory,
    SourcePacket,
    TCDataFieldHeader,
    service_data,
)
from sat_sim.services.housekeeping import ISS_APPLICATION_PROCESS_ID
from sat_sim.services.verification import acceptance_fault, verification_report


def _command() -> SourcePacket:
    return SourcePacket.get_source_packet(
        service_data(17, 1),
        local_prid=23,
        destination_prid=ISS_APPLICATION_PROCESS_ID,
        sequence_count=0x1234,
    )


def test_success_report_matches_pusutilities_tc_reference_layout() -> None:
    command = _command()
    report = verification_report(command, 1, 9)
    restored = SourcePacket(report.get_bytes(), ByteOrder.BIG_ENDIAN)

    assert restored.packet_data_field.data.data == command.get_bytes()[:4]
    assert restored.get_source_prid() == ISS_APPLICATION_PROCESS_ID
    assert restored.get_destination_prid() == 23
    assert restored.packet_header.sequence_control.sequence_count == 9
    assert restored.verify_crc()


def test_failure_report_appends_big_endian_fault_and_parameters() -> None:
    command = _command()
    report = verification_report(
        command, 8, 10, FaultID.INVALID_PAR_ID, b"\x01\x02\x03\x04"
    )

    assert report.packet_data_field.data.data == (
        command.get_bytes()[:4]
        + int(FaultID.INVALID_PAR_ID).to_bytes(2, "big")
        + b"\x01\x02\x03\x04"
    )


def test_acceptance_validation_reports_header_and_service_faults() -> None:
    command = _command()
    assert acceptance_fault(command) is None

    command.packet_header.packet_id.version = 1
    assert acceptance_fault(command) is FaultID.ILLEGAL_VERSION
    command.packet_header.packet_id.version = 0
    header = command.packet_data_field.data_field_header
    assert isinstance(header, TCDataFieldHeader)
    header.tc_pus_version_number = 2
    assert acceptance_fault(command) is FaultID.ILLEGAL_TC_PUS
    header.tc_pus_version_number = 1
    command.packet_header.packet_id.pcat = PacketCategory.EVENT
    assert acceptance_fault(command) is FaultID.ILLEGAL_PCAT


def test_acceptance_validation_rejects_unsupported_telecommand() -> None:
    command = SourcePacket.get_source_packet(service_data(8, 1))
    assert acceptance_fault(command) is FaultID.UNKNOWN_S_TYPE


def test_success_report_rejects_failure_fields() -> None:
    with pytest.raises(ValueError, match="success"):
        verification_report(_command(), 7, 0, FaultID.DUMP_ERROR)


def test_failure_report_requires_fault() -> None:
    with pytest.raises(ValueError, match="fault ID"):
        verification_report(_command(), 2, 0)
