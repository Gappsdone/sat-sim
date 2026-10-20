import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from pus_library import ByteOrder, HousekeepingReport, SourcePacket
from sat_sim.scenarios.iss_scenario import ISSScenario
from sat_sim.services.housekeeping import TCS_HOUSEKEEPING_DEFINITIONS
from sat_sim.services.tcs import solar_direction_eci
from sat_sim_telemetry import (
    ISSTelemetryPublisher,
    TelemetryStore,
    create_app,
    describe_iss_scenario,
    snapshot_iss,
)


class FakeOrbital:
    def get_position(
        self, utc_time: datetime, normalize: bool = False
    ) -> tuple[list[float], list[float]]:
        del normalize
        sun = solar_direction_eci(utc_time)
        return [6_700.0 * value for value in sun], [0.0, 7.5, 0.0]


class FakePUSPublisher:
    def __init__(self) -> None:
        self.packets: list[SourcePacket] = []

    def publish(self, packet: SourcePacket) -> None:
        self.packets.append(packet)


def make_scenario(monkeypatch: pytest.MonkeyPatch) -> tuple[ISSScenario, datetime]:
    monkeypatch.setattr(
        "sat_sim.scenarios.iss_scenario.create_iss_orbital",
        lambda **_kwargs: FakeOrbital(),
    )
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    scenario = ISSScenario()
    scenario.setup(timestamp)
    return scenario, timestamp


def test_snapshot_contains_cesium_ready_orbit_attitude_and_subsystems(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario, timestamp = make_scenario(monkeypatch)
    state = scenario.step(timestamp + timedelta(seconds=1))
    capsys.readouterr()

    frame = snapshot_iss(scenario, state, 7)
    iss = frame.entities["iss"]

    assert frame.schema_version == 1
    assert frame.sequence == 7
    assert frame.time == state.timestamp
    assert iss.position.frame == "TEME"
    assert iss.position.unit == "m"
    assert iss.velocity.unit == "m/s"
    assert iss.attitude.frame == "BODY_TO_TEME"
    assert sum(value**2 for value in iss.attitude.value) == pytest.approx(1.0)
    assert iss.adcs.pointing_error_deg == pytest.approx(state.pointing_error_deg)
    assert iss.adcs.wheel_speeds_rad_s == pytest.approx(state.wheel_speeds_rad_s)
    assert len(iss.adcs.target_quaternion_xyzw) == 4
    assert len(iss.adcs.disturbance_torque_nm) == 3
    assert len(iss.adcs.estimated_quaternion_xyzw) == 4
    assert iss.adcs.sensor_valid["gyro"]
    assert iss.adcs.mode == "NADIR_POINTING"
    assert len(iss.adcs.magnetorquer_torque_nm) == 3
    assert iss.illumination.sunlit is True
    assert iss.power.battery_capacity_wh == 1_000.0
    assert iss.power.state_of_charge == pytest.approx(state.battery_charge_wh / 1_000.0)
    assert len(iss.thermal_channels) == 9
    assert iss.thermal_channels[0].heater_power_w > 0.0


def test_description_separates_static_geometry_from_streamed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, _timestamp = make_scenario(monkeypatch)
    description = describe_iss_scenario(scenario)

    assert description.scenario == "ISS"
    assert description.entities == ("iss",)
    assert description.entity_components["iss"] == (
        "ADCSFaultState",
        "ADCSModeState",
        "ADCSSensorConfiguration",
        "ADCSSensorMeasurements",
        "ADCSStatus",
        "AttitudeController",
        "AttitudeEstimate",
        "AttitudeEstimatorConfiguration",
        "AttitudeReference",
        "AttitudeState",
        "ECIPosition",
        "ECIVelocity",
        "IlluminationState",
        "MagnetorquerAssembly",
        "MomentumManagementConfiguration",
        "PCDU",
        "ReactionWheelAssembly",
        "RigidBody",
        "SolarPanel",
        "SpacecraftAttitude",
    )
    assert description.entity_component_values["iss"]["PCDU"] == {
        "capacity_wh": 1_000.0,
        "charge_wh": 500.0,
        "generated_power_w": 0.0,
        "consumed_power_w": 0.0,
        "is_sunlit": None,
    }
    assert (
        description.entity_component_values["iss"]["ADCSModeState"]["current"]
        == "NADIR_POINTING"
    )
    assert description.coordinate_frame == "TEME"
    assert description.solar_panel_peak_power_w == 100.0
    assert len(description.thermal_channels) == 9


def test_description_requires_initialized_iss_scenario() -> None:
    with pytest.raises(RuntimeError, match="set up"):
        describe_iss_scenario(ISSScenario())


def test_publisher_steps_scenario_and_increments_sequence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario, timestamp = make_scenario(monkeypatch)
    store = TelemetryStore()
    pus = FakePUSPublisher()
    publisher = ISSTelemetryPublisher(scenario, store, pus)

    _state, first = publisher.step(timestamp + timedelta(seconds=1))
    _state, second = publisher.step(timestamp + timedelta(seconds=2))
    capsys.readouterr()

    assert first.sequence == 0
    assert second.sequence == 1
    assert store.current is second
    assert len(pus.packets) == 2
    packet = SourcePacket(pus.packets[-1].get_bytes(), ByteOrder.BIG_ENDIAN)
    report = HousekeepingReport.from_service_data(
        packet.packet_data_field.data, TCS_HOUSEKEEPING_DEFINITIONS
    )
    assert report.structure_id == 1
    assert packet.packet_header.sequence_control.sequence_count == 1
    publisher.consume(packet)
    assert publisher.last_consumed_packet is packet


def test_publisher_answers_service_17_before_first_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pus_library import service_data
    from sat_sim.services.housekeeping import ISS_APPLICATION_PROCESS_ID

    scenario, _timestamp = make_scenario(monkeypatch)
    pus = FakePUSPublisher()
    publisher = ISSTelemetryPublisher(scenario, TelemetryStore(), pus)
    request = SourcePacket.get_source_packet(
        service_data(17, 1),
        local_prid=23,
        destination_prid=ISS_APPLICATION_PROCESS_ID,
    )

    publisher.consume(request)

    assert publisher.last_consumed_packet is request
    assert [
        packet.packet_data_field.data.service_sub_type for packet in pus.packets
    ] == [
        1,
        2,
        7,
    ]
    response = pus.packets[1]
    assert response.packet_data_field.data.service_sub_type == 2
    assert response.get_destination_prid() == 23
    assert response.packet_header.sequence_control.sequence_count == 1


def test_publisher_honors_success_report_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pus_library import TCDataFieldHeader, service_data
    from sat_sim.services.housekeeping import ISS_APPLICATION_PROCESS_ID

    scenario, _timestamp = make_scenario(monkeypatch)
    pus = FakePUSPublisher()
    publisher = ISSTelemetryPublisher(scenario, TelemetryStore(), pus)
    request = SourcePacket.get_source_packet(
        service_data(17, 1), destination_prid=ISS_APPLICATION_PROCESS_ID
    )
    header = request.packet_data_field.data_field_header
    assert isinstance(header, TCDataFieldHeader)
    header.request_acceptance_report = False
    header.request_execution_completion_report = False

    publisher.consume(request)

    assert [packet.packet_data_field.data.service_type for packet in pus.packets] == [
        17
    ]


def test_publisher_reports_parameter_execution_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pus_library import FaultID, service_data
    from sat_sim.services.housekeeping import ISS_APPLICATION_PROCESS_ID

    scenario, timestamp = make_scenario(monkeypatch)
    pus = FakePUSPublisher()
    publisher = ISSTelemetryPublisher(scenario, TelemetryStore(), pus)
    publisher.step(timestamp + timedelta(seconds=1))
    capsys.readouterr()
    pus.packets.clear()
    request = SourcePacket.get_source_packet(
        service_data(140, 1, b""), destination_prid=ISS_APPLICATION_PROCESS_ID
    )

    publisher.consume(request)

    assert [
        packet.packet_data_field.data.service_sub_type for packet in pus.packets
    ] == [
        1,
        8,
    ]
    failure = pus.packets[-1].packet_data_field.data.data
    assert failure[:4] == request.get_bytes()[:4]
    assert (
        int.from_bytes(failure[4:6], "big")
        == FaultID.ILLEGAL_OR_INCONSISTENT_APPLICATION_DATA
    )


def test_api_serves_metadata_latest_snapshot_and_websocket(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario, timestamp = make_scenario(monkeypatch)
    store = TelemetryStore()
    app = create_app(store, lambda: describe_iss_scenario(scenario))

    with TestClient(app) as client:
        assert client.get("/api/v1/state").status_code == 503
        metadata = client.get("/api/v1/scenario")
        assert metadata.status_code == 200
        assert metadata.json()["coordinateFrame"] == "TEME"
        assert (
            metadata.json()["entityComponentValues"]["iss"]["PCDU"]["capacity_wh"]
            == 1_000.0
        )

        state = scenario.step(timestamp + timedelta(seconds=1))
        frame = snapshot_iss(scenario, state, 0)
        store.publish(frame)
        capsys.readouterr()

        live_metadata = client.get("/api/v1/scenario")
        assert live_metadata.status_code == 200
        assert live_metadata.json()["entityComponentValues"]["iss"]["ADCSStatus"][
            "wheel_saturated"
        ] == [False, False, False]

        response = client.get("/api/v1/state")
        assert response.status_code == 200
        assert response.json()["entities"]["iss"]["power"]["batteryCapacityWh"] == (
            1_000.0
        )
        with client.websocket_connect("/api/v1/telemetry") as websocket:
            message = websocket.receive_json()
            assert message["sequence"] == 0
            assert message["entities"]["iss"]["position"]["frame"] == "TEME"


def test_store_rejects_stale_frames_and_drops_slow_subscriber_backlog(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario, timestamp = make_scenario(monkeypatch)
    state = scenario.step(timestamp + timedelta(seconds=1))
    capsys.readouterr()
    first = snapshot_iss(scenario, state, 1)
    second = snapshot_iss(scenario, state, 2)
    store = TelemetryStore(subscriber_queue_size=1)

    async def exercise_store() -> None:
        async with store.subscribe() as queue:
            store.publish(first)
            store.publish(second)
            assert await queue.get() is second

    asyncio.run(exercise_store())
    with pytest.raises(ValueError, match="increase"):
        store.publish(first)


def test_store_requires_positive_subscriber_queue_size() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        TelemetryStore(0)


def test_service_140_get_and_set_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from struct import pack

    from pus_library import service_data
    from sat_sim.services.housekeeping import (
        ISS_APPLICATION_PROCESS_ID,
        TCS_HEATER_INDICATOR_IDS,
        TCS_THERMISTOR_IDS,
    )
    from sat_sim.services.parameters import (
        ParameterCommandError,
        handle_parameter_command,
    )

    scenario, timestamp = make_scenario(monkeypatch)
    state = scenario.step(timestamp + timedelta(seconds=1))
    ids = (TCS_THERMISTOR_IDS[0][0], TCS_HEATER_INDICATOR_IDS[0])
    request = SourcePacket.get_source_packet(
        service_data(140, 2, b"\x02" + pack(">II", *ids)),
        local_prid=0,
        destination_prid=ISS_APPLICATION_PROCESS_ID,
    )
    response = handle_parameter_command(request, state, scenario.tcs, 7)
    assert response is not None
    assert response.packet_data_field.data.service_sub_type == 3
    assert response.packet_data_field.data.data == (
        b"\x02"
        + pack(">If", ids[0], state.temperatures_celsius[0])
        + pack(">Ii", ids[1], int(state.heater_outputs[0] > 0))
    )
    assert response.get_source_prid() == ISS_APPLICATION_PROCESS_ID
    assert response.get_destination_prid() == 0
    assert response.verify_crc()

    set_packet = SourcePacket.get_source_packet(
        service_data(140, 1, b"\x01" + pack(">Ii", ids[1], 1)),
        local_prid=0,
        destination_prid=ISS_APPLICATION_PROCESS_ID,
    )
    assert handle_parameter_command(set_packet, state, scenario.tcs, 8) is None
    assert scenario.tcs.heaters[0].manual_override
    invalid = SourcePacket.get_source_packet(
        service_data(140, 1, b"\x02" + pack(">IiIi", ids[1], 0, ids[0], 1)),
        local_prid=0,
        destination_prid=ISS_APPLICATION_PROCESS_ID,
    )
    with pytest.raises(ParameterCommandError):
        handle_parameter_command(invalid, state, scenario.tcs, 9)
    assert scenario.tcs.heaters[0].manual_override
