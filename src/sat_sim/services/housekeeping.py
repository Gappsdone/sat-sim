"""ISS TCS housekeeping report generation using PUS Service 3."""

from pus_library import (
    HousekeepingParameterDefinition,
    HousekeepingParameterType,
    HousekeepingReport,
    HousekeepingService,
    HousekeepingStructure,
    HousekeepingStructureDefinition,
    SourcePacket,
)
from sat_sim.scenarios.iss_scenario import ISSScenarioState

ISS_HOUSEKEEPING_STRUCTURE_ID = 1
ISS_HOUSEKEEPING_COLLECTION_INTERVAL = 1
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


def create_iss_housekeeping_report(
    state: ISSScenarioState,
    structure: HousekeepingStructure | None = None,
) -> HousekeepingReport:
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
    return (structure or _new_iss_structure()).report(values)


def create_iss_housekeeping_packet(
    state: ISSScenarioState,
    sequence: int,
    destination_prid: int = GROUND_APPLICATION_PROCESS_ID,
) -> SourcePacket:
    """Packetize one ISS housekeeping report as CRC-protected TM(3,25)."""
    report = create_iss_housekeeping_report(state)
    return SourcePacket.get_source_packet(
        report.to_service_data(),
        local_prid=ISS_APPLICATION_PROCESS_ID,
        destination_prid=destination_prid,
        sequence_count=sequence,
    )


def _new_iss_structure() -> HousekeepingStructure:
    return HousekeepingStructure(
        HousekeepingStructureDefinition(
            ISS_HOUSEKEEPING_STRUCTURE_ID,
            ISS_HOUSEKEEPING_COLLECTION_INTERVAL,
            tuple(item.parameter_id for item in TCS_HOUSEKEEPING_DEFINITIONS),
        ),
        TCS_HOUSEKEEPING_DEFINITIONS,
        (GROUND_APPLICATION_PROCESS_ID,),
    )


class ISSHousekeepingService:
    """Manage the fixed plugin_tcs housekeeping structure and subscriptions."""

    def __init__(self) -> None:
        self._service = HousekeepingService(ISS_APPLICATION_PROCESS_ID)
        self._service.add_structure(_new_iss_structure())

    @property
    def definition(self) -> HousekeepingStructureDefinition:
        """Expose the fixed ISS definition for compatibility with callers."""
        structure = self._service.get_structure(ISS_HOUSEKEEPING_STRUCTURE_ID)
        assert structure is not None
        return structure.definition

    def periodic_packets(
        self, state: ISSScenarioState, first_sequence: int
    ) -> tuple[SourcePacket, ...]:
        """Create one periodic report for every enabled destination."""
        return self._service.periodic_packets(
            lambda structure: create_iss_housekeeping_report(state, structure),
            first_sequence,
        )

    def handle_command(
        self,
        packet: SourcePacket,
        state: ISSScenarioState | None,
        sequence: int,
    ) -> SourcePacket | None:
        """Handle TC(3,5/6/9/136), returning telemetry where applicable."""
        factory = (
            None
            if state is None
            else lambda structure: create_iss_housekeeping_report(state, structure)
        )
        return self._service.handle_command(packet, factory, sequence)
