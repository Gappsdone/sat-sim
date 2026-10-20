"""PUS Service 1 telecommand verification reports.

The application-data layout mirrors PUSUtilities ``VerificationReport`` and
``DataSST1/2/7/8``: the original packet ID and packet sequence control are
followed by a 16-bit fault ID (and optional parameters) on failure reports.
"""

from __future__ import annotations

from pus_library import (
    FaultID,
    PacketCategory,
    SourcePacket,
    TCDataFieldHeader,
    service_data,
)
from sat_sim.services.housekeeping import ISS_APPLICATION_PROCESS_ID

SUPPORTED_TELECOMMANDS = frozenset(
    ((3, 5), (3, 6), (3, 9), (3, 136), (17, 1), (140, 1), (140, 2))
)


def _reference(packet: SourcePacket) -> bytes:
    return (
        packet.packet_header.packet_id.get_bytes()
        + packet.packet_header.sequence_control.get_bytes()
    )


def acceptance_fault(packet: SourcePacket) -> FaultID | None:
    """Return the PUSUtilities-compatible acceptance fault, if any."""
    if not packet.is_tc_packet():
        return FaultID.ILLEGAL_P_TYPE
    packet_id = packet.packet_header.packet_id
    if packet_id.version != 0:
        return FaultID.ILLEGAL_VERSION
    if not packet_id.has_data_field_header:
        return FaultID.ILLEGAL_DFHF
    header = packet.packet_data_field.data_field_header
    if not isinstance(header, TCDataFieldHeader) or header.tc_pus_version_number != 1:
        return FaultID.ILLEGAL_TC_PUS
    data = packet.packet_data_field.data
    if (data.service_type, data.service_sub_type) not in SUPPORTED_TELECOMMANDS:
        return FaultID.UNKNOWN_S_TYPE
    if packet_id.pcat is not PacketCategory.TELECOMMAND:
        return FaultID.ILLEGAL_PCAT
    return None


def verification_report(
    packet: SourcePacket,
    subtype: int,
    sequence: int,
    fault: FaultID | None = None,
    parameters: bytes = b"",
) -> SourcePacket:
    """Create TM(1,1/2/7/8) addressed to the TC source PRID."""
    payload = bytearray(_reference(packet))
    if subtype in (2, 8):
        if fault is None:
            raise ValueError("failure verification reports require a fault ID")
        payload.extend(int(fault).to_bytes(2, "big"))
        payload.extend(parameters)
    elif fault is not None or parameters:
        raise ValueError("success verification reports contain only the TC reference")
    return SourcePacket.get_source_packet(
        service_data(1, subtype, bytes(payload)),
        local_prid=ISS_APPLICATION_PROCESS_ID,
        destination_prid=packet.get_source_prid(),
        sequence_count=sequence,
    )
