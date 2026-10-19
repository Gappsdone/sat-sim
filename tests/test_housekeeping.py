from datetime import UTC, datetime

import pytest

from pus_library import (
    ByteOrder,
    HousekeepingParameter,
    HousekeepingReport,
    PacketErrorControl,
    SourcePacket,
    service_data,
)
from sat_sim.position import ECIPosition, ECIVelocity
from sat_sim.scenarios.iss_scenario import ISSScenarioState
from sat_sim.services.housekeeping import (
    ISS_HOUSEKEEPING_STRUCTURE_ID,
    TCS_HEATER_INDICATOR_IDS,
    TCS_THERMISTOR_IDS,
    ISSHousekeepingParameter,
    create_iss_housekeeping_packet,
    create_iss_housekeeping_report,
)


@pytest.mark.parametrize("byte_order", list(ByteOrder))
def test_housekeeping_report_round_trip(byte_order: ByteOrder) -> None:
    report = HousekeepingReport(
        structure_id=7,
        sequence=42,
        parameters=(
            HousekeepingParameter(1, True),
            HousekeepingParameter(2, -12),
            HousekeepingParameter(3, 21.5),
        ),
    )
    encoded = report.get_bytes(byte_order)
    wrapped = service_data(3, 25, encoded)

    assert HousekeepingReport.from_service_data(wrapped, byte_order) == report


def test_housekeeping_report_rejects_invalid_data() -> None:
    with pytest.raises(ValueError, match="unique"):
        HousekeepingReport(
            1,
            0,
            (HousekeepingParameter(1, 1), HousekeepingParameter(1, 2)),
        )
    with pytest.raises(ValueError, match=r"TM\(3,25\)"):
        HousekeepingReport.from_service_data(service_data(3, 10))
    with pytest.raises(ValueError, match="truncated"):
        HousekeepingReport.from_service_data(
            service_data(3, 25, b"\x01\x00\x00\x00\x00\x00\x01")
        )


def test_housekeeping_ids_use_pusutilities_framework_widths() -> None:
    report = HousekeepingReport(
        structure_id=0xFF,
        sequence=0,
        parameters=(HousekeepingParameter(0xFFFFFFFF, True),),
    )

    assert HousekeepingReport.from_service_data(report.to_service_data()) == report
    with pytest.raises(ValueError, match="unsigned 8-bit"):
        HousekeepingReport(0x100, 0, ())
    with pytest.raises(ValueError, match="unsigned 32-bit"):
        HousekeepingParameter(0x100000000, True)


def test_iss_housekeeping_is_packetized_as_service_3_telemetry() -> None:
    state = ISSScenarioState(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        position=ECIPosition(1.0, 2.0, 3.0),
        velocity=ECIVelocity(4.0, 5.0, 6.0),
        temperatures_celsius=tuple(float(value) for value in range(20, 29)),
        heater_outputs=(0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        is_sunlit=True,
        battery_charge_wh=500.0,
        generated_power_w=80.0,
        consumed_power_w=25.0,
    )

    report = create_iss_housekeeping_report(state, sequence=9)
    packet = create_iss_housekeeping_packet(state, sequence=9)
    raw = packet.get_bytes()
    restored_packet = SourcePacket(raw, ByteOrder.BIG_ENDIAN)
    restored_report = HousekeepingReport.from_service_data(
        restored_packet.packet_data_field.data
    )
    values = {
        parameter.parameter_id: parameter.value
        for parameter in restored_report.parameters
    }

    assert report.structure_id == ISS_HOUSEKEEPING_STRUCTURE_ID
    assert report.sequence == 9
    assert len(report.parameters) == 40
    assert restored_packet.is_tm_packet()
    assert restored_packet.packet_data_field.data.service_type == 3
    assert restored_packet.packet_data_field.data.service_sub_type == 25
    assert PacketErrorControl.verify_crc(raw)
    assert values[ISSHousekeepingParameter.ILLUMINATION_STATE] == 1
    assert values[ISSHousekeepingParameter.BATTERY_CHARGE_WH] == 500.0
    assert all(values[parameter_id] == 20.0 for parameter_id in TCS_THERMISTOR_IDS[0])
    assert values[TCS_HEATER_INDICATOR_IDS[0]] == 0
    assert values[TCS_HEATER_INDICATOR_IDS[1]] == 1
