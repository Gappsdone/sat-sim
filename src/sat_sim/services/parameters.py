"""PUS service 140 parameter access for the ISS thermal channels.

Wire layout follows PUSUtilities ParameterManagementData and DataSST2:
8-bit NPAR, then 32-bit big-endian IDs, with raw values on SST 1/3.
"""

from __future__ import annotations

from struct import pack, unpack

from pus_library import SourcePacket, service_data
from sat_sim.scenarios.iss_scenario import ISSScenarioState
from sat_sim.services.housekeeping import (
    ISS_APPLICATION_PROCESS_ID,
    TCS_HEATER_INDICATOR_IDS,
    TCS_THERMISTOR_IDS,
)
from sat_sim.services.tcs import ThermalControlSystem


class ParameterCommandError(ValueError):
    """Invalid or unsupported parameter telecommand."""


_THERMISTOR_CHANNELS = {
    parameter_id: channel
    for channel, group in enumerate(TCS_THERMISTOR_IDS)
    for parameter_id in group
}
_HEATER_CHANNELS = {
    parameter_id: channel
    for channel, parameter_id in enumerate(TCS_HEATER_INDICATOR_IDS)
}


def handle_parameter_command(
    packet: SourcePacket,
    state: ISSScenarioState,
    tcs: ThermalControlSystem,
    sequence: int,
) -> SourcePacket | None:
    """Apply TC(140,1) or return TM(140,3) for TC(140,2).

    Thermistors are read-only; heater indicators accept only 0 and 1.
    Commands are validated in full before any heater state changes.
    """
    data = packet.packet_data_field.data
    if not packet.is_tc_packet() or data.service_type != 140:
        return None
    if packet.get_destination_prid() != ISS_APPLICATION_PROCESS_ID:
        return None
    if data.service_sub_type not in (1, 2):
        return None
    payload = data.data
    if not payload:
        raise ParameterCommandError("missing NPAR")
    count = payload[0]
    if data.service_sub_type == 2:
        if len(payload) != 1 + count * 4:
            raise ParameterCommandError("invalid parameter request length")
        ids = [unpack(">I", payload[1 + i * 4 : 5 + i * 4])[0] for i in range(count)]
        values = bytearray((count,))
        for parameter_id in ids:
            if parameter_id in _THERMISTOR_CHANNELS:
                raw = pack(
                    ">f", state.temperatures_celsius[_THERMISTOR_CHANNELS[parameter_id]]
                )
            elif parameter_id in _HEATER_CHANNELS:
                raw = pack(
                    ">i", int(state.heater_outputs[_HEATER_CHANNELS[parameter_id]] > 0)
                )
            else:
                raise ParameterCommandError(f"unknown parameter ID: {parameter_id:#x}")
            values.extend(pack(">I", parameter_id))
            values.extend(raw)
        return SourcePacket.get_source_packet(
            service_data(140, 3, bytes(values)),
            local_prid=ISS_APPLICATION_PROCESS_ID,
            destination_prid=packet.get_source_prid(),
            sequence_count=sequence,
        )

    if len(payload) != 1 + count * 8:
        raise ParameterCommandError("invalid set-parameter length")
    changes: list[tuple[int, int]] = []
    for index in range(count):
        offset = 1 + index * 8
        parameter_id, value = unpack(">Ii", payload[offset : offset + 8])
        if parameter_id not in _HEATER_CHANNELS or value not in (0, 1):
            raise ParameterCommandError(
                f"unsupported parameter assignment: {parameter_id:#x}"
            )
        changes.append((_HEATER_CHANNELS[parameter_id], value))
    for channel, value in changes:
        tcs.heaters[channel].activate(bool(value))
    return None
