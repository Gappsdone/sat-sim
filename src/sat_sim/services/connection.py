"""PUS Service 17 connection-test handling."""

from pus_library import SourcePacket, service_data
from sat_sim.services.housekeeping import ISS_APPLICATION_PROCESS_ID


def handle_connection_test(packet: SourcePacket, sequence: int) -> SourcePacket | None:
    """Return an empty TM(17,2) response for a TC(17,1) ping.

    This mirrors PUSUtilities ``st17.DataSST1``: the response contains no
    application data and is addressed back to the telecommand source PRID.
    """
    data = packet.packet_data_field.data
    if not packet.is_tc_packet() or data.service_type != 17:
        return None
    if data.service_sub_type != 1:
        return None
    if packet.get_destination_prid() != ISS_APPLICATION_PROCESS_ID:
        return None
    return SourcePacket.get_source_packet(
        service_data(17, 2),
        local_prid=ISS_APPLICATION_PROCESS_ID,
        destination_prid=packet.get_source_prid(),
        sequence_count=sequence,
    )
