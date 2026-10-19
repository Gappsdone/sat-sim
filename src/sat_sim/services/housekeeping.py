"""ISS housekeeping report generation using PUS Service 3."""

from enum import IntEnum

from pus_library import HousekeepingParameter, HousekeepingReport, SourcePacket
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


class ISSHousekeepingParameter(IntEnum):
    """Stable mission-database identifiers for the default ISS report."""

    ILLUMINATION_STATE = 1
    BATTERY_CHARGE_WH = 2
    GENERATED_POWER_W = 3
    CONSUMED_POWER_W = 4


def create_iss_housekeeping_report(
    state: ISSScenarioState, sequence: int
) -> HousekeepingReport:
    """Create the default platform housekeeping report from one scenario step."""
    illumination = -1 if state.is_sunlit is None else int(state.is_sunlit)
    parameters = [
        HousekeepingParameter(
            ISSHousekeepingParameter.ILLUMINATION_STATE, illumination
        ),
        HousekeepingParameter(
            ISSHousekeepingParameter.BATTERY_CHARGE_WH, state.battery_charge_wh
        ),
        HousekeepingParameter(
            ISSHousekeepingParameter.GENERATED_POWER_W, state.generated_power_w
        ),
        HousekeepingParameter(
            ISSHousekeepingParameter.CONSUMED_POWER_W, state.consumed_power_w
        ),
    ]
    if len(state.temperatures_celsius) != len(TCS_THERMISTOR_IDS):
        raise ValueError("the ISS scenario must expose all nine TCS thermal channels")
    if len(state.heater_outputs) != len(TCS_HEATER_INDICATOR_IDS):
        raise ValueError("the ISS scenario must expose all nine TCS heater channels")
    parameters.extend(
        HousekeepingParameter(parameter_id, temperature)
        for parameter_ids, temperature in zip(
            TCS_THERMISTOR_IDS, state.temperatures_celsius, strict=True
        )
        for parameter_id in parameter_ids
    )
    parameters.extend(
        HousekeepingParameter(parameter_id, int(output > 0.0))
        for parameter_id, output in zip(
            TCS_HEATER_INDICATOR_IDS, state.heater_outputs, strict=True
        )
    )
    return HousekeepingReport(
        ISS_HOUSEKEEPING_STRUCTURE_ID,
        sequence,
        tuple(parameters),
    )


def create_iss_housekeeping_packet(
    state: ISSScenarioState, sequence: int
) -> SourcePacket:
    """Packetize one ISS housekeeping report as CRC-protected TM(3,25)."""
    report = create_iss_housekeeping_report(state, sequence)
    return SourcePacket.get_source_packet(
        report.to_service_data(),
        local_prid=ISS_APPLICATION_PROCESS_ID,
        destination_prid=GROUND_APPLICATION_PROCESS_ID,
    )
