"""Bridge synchronous ISS scenario steps into telemetry frames."""

from datetime import datetime
from typing import Protocol

from pus_library import FaultID, SourcePacket, TCDataFieldHeader
from sat_sim.scenarios.iss_scenario import ISSScenario, ISSScenarioState
from sat_sim.services.connection import handle_connection_test
from sat_sim.services.housekeeping import (
    ISS_APPLICATION_PROCESS_ID,
    create_iss_housekeeping_packet,
)
from sat_sim.services.parameters import ParameterCommandError, handle_parameter_command
from sat_sim.services.verification import acceptance_fault, verification_report
from sat_sim_telemetry.models import TelemetryFrame
from sat_sim_telemetry.snapshot import snapshot_iss
from sat_sim_telemetry.store import TelemetryStore


class PUSPublisher(Protocol):
    """Transport accepted by the telemetry publisher."""

    def publish(self, packet: SourcePacket) -> None: ...


class ISSTelemetryPublisher:
    """Step an ISS scenario and publish one immutable frame per step."""

    def __init__(
        self,
        scenario: ISSScenario,
        store: TelemetryStore,
        pus: PUSPublisher,
    ) -> None:
        self.scenario = scenario
        self.store = store
        self.pus = pus
        self._sequence = 0 if store.current is None else store.current.sequence + 1
        self.last_consumed_packet: SourcePacket | None = None
        self._latest_state: ISSScenarioState | None = None

    def setup(self, timestamp: datetime) -> None:
        self.scenario.setup(timestamp)

    def step(self, timestamp: datetime) -> tuple[ISSScenarioState, TelemetryFrame]:
        state = self.scenario.step(timestamp)
        self._latest_state = state
        frame = snapshot_iss(self.scenario, state, self._sequence)
        self.pus.publish(create_iss_housekeeping_packet(state, self._sequence))
        self.store.publish(frame)
        self._sequence += 1
        return state, frame

    def consume(self, packet: SourcePacket) -> None:
        """Accept an inbound PUS packet for service-specific dispatch."""
        self.last_consumed_packet = packet
        if not packet.is_tc_packet():
            return
        if packet.get_destination_prid() != ISS_APPLICATION_PROCESS_ID:
            return
        header = packet.packet_data_field.data_field_header
        fault = acceptance_fault(packet)
        if fault is not None:
            self._publish_verification(packet, 2, fault)
            return
        if isinstance(header, TCDataFieldHeader) and header.request_acceptance_report:
            self._publish_verification(packet, 1)

        response = handle_connection_test(packet, self._sequence)
        if response is not None:
            self.pus.publish(response)
            self._sequence += 1
        else:
            if self._latest_state is None:
                self._publish_verification(packet, 8, FaultID.REPORT_ABORTED)
                return
            try:
                response = handle_parameter_command(
                    packet, self._latest_state, self.scenario.tcs, self._sequence
                )
            except ParameterCommandError:
                self._publish_verification(
                    packet, 8, FaultID.ILLEGAL_OR_INCONSISTENT_APPLICATION_DATA
                )
                return
            if response is not None:
                self.pus.publish(response)
                self._sequence += 1

        if (
            isinstance(header, TCDataFieldHeader)
            and header.request_execution_completion_report
        ):
            self._publish_verification(packet, 7)

    def _publish_verification(
        self, packet: SourcePacket, subtype: int, fault: FaultID | None = None
    ) -> None:
        self.pus.publish(verification_report(packet, subtype, self._sequence, fault))
        self._sequence += 1
