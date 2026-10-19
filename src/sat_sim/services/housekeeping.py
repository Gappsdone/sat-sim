"""ISS TCS housekeeping report generation using PUS Service 3."""

from pus_library import (
    HousekeepingParameter,
    HousekeepingParameterDefinition,
    HousekeepingParameterType,
    HousekeepingReport,
    SourcePacket,
)
from sat_sim.scenarios.iss_scenario import ISSScenarioState

ISS_HOUSEKEEPING_STRUCTURE_ID = 1
# Mission assignments from plugin_tcs (TCS.java on the dev branch).
ISS_APPLICATION_PROCESS_ID = 5
GROUND_APPLICATION_PROCESS_ID = 0

TCS_THERMISTOR_IDS = (
    (0x01003F01, 0x01004101, 0x01004001),
    (0x01004801, 0x01004701, 0x01005901),
    (0x01005801, 0x01005701, 0x01005601),
    (0x01005501, 0x01005401, 0x01005301),
    (0x01005201, 0x01005101, 0x01005001),
    (0x01004F01, 0x01004E01, 0x01004D01),
    (0x01004C01, 0x01004B01, 0x01004A01),
    (0x01004901, 0x01004601, 0x01004501),
    (0x01004401, 0x01004301, 0x01004201),
)
TCS_HEATER_INDICATOR_IDS = (
    0x0600000A,
    0x0600010A,
    0x0600020A,
    0x0600030A,
    0x0600040A,
    0x0600050A,
    0x0600060A,
    0x0600070A,
    0x0600080A,
)


TCS_HOUSEKEEPING_DEFINITIONS = tuple(
    HousekeepingParameterDefinition(parameter_id, 4, HousekeepingParameterType.FLOAT)
    for group in TCS_THERMISTOR_IDS
    for parameter_id in group
) + tuple(
    HousekeepingParameterDefinition(
        parameter_id, 4, HousekeepingParameterType.SIGNED_INTEGER
    )
    for parameter_id in TCS_HEATER_INDICATOR_IDS
)


def create_iss_housekeeping_report(state: ISSScenarioState) -> HousekeepingReport:
    """Create the plugin_tcs structure report from one scenario step."""
    if len(state.temperatures_celsius) != len(TCS_THERMISTOR_IDS):
        raise ValueError("the ISS scenario must expose all nine TCS thermal channels")
    if len(state.heater_outputs) != len(TCS_HEATER_INDICATOR_IDS):
        raise ValueError("the ISS scenario must expose all nine TCS heater channels")
    values = [
        temperature
        for _parameter_ids, temperature in zip(
            TCS_THERMISTOR_IDS, state.temperatures_celsius, strict=True
        )
        for _parameter_id in _parameter_ids
    ]
    values.extend(int(output > 0.0) for output in state.heater_outputs)
    return HousekeepingReport(
        ISS_HOUSEKEEPING_STRUCTURE_ID,
        tuple(
            HousekeepingParameter(definition, value)
            for definition, value in zip(
                TCS_HOUSEKEEPING_DEFINITIONS, values, strict=True
            )
        ),
    )


def create_iss_housekeeping_packet(
    state: ISSScenarioState, sequence: int
) -> SourcePacket:
    """Packetize one ISS housekeeping report as CRC-protected TM(3,25)."""
    report = create_iss_housekeeping_report(state)
    return SourcePacket.get_source_packet(
        report.to_service_data(),
        local_prid=ISS_APPLICATION_PROCESS_ID,
        destination_prid=GROUND_APPLICATION_PROCESS_ID,
        sequence_count=sequence,
    )
