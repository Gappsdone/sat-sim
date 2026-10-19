from datetime import UTC, datetime

import pytest

from pus_library import (
    ByteOrder,
    HousekeepingParameter,
    HousekeepingParameterDefinition,
    HousekeepingParameterType,
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
    TCS_HOUSEKEEPING_DEFINITIONS,
    TCS_THERMISTOR_IDS,
    create_iss_housekeeping_packet,
    create_iss_housekeeping_report,
)


@pytest.mark.parametrize("byte_order", list(ByteOrder))
def test_housekeeping_report_round_trip(byte_order: ByteOrder) -> None:
    definitions = (
        HousekeepingParameterDefinition(1, 1, HousekeepingParameterType.SIGNED_INTEGER),
        HousekeepingParameterDefinition(2, 4, HousekeepingParameterType.SIGNED_INTEGER),
        HousekeepingParameterDefinition(3, 4, HousekeepingParameterType.FLOAT),
    )
    report = HousekeepingReport(
        7,
        (
            HousekeepingParameter(definitions[0], 42),
            HousekeepingParameter(definitions[1], -12),
            HousekeepingParameter(definitions[2], 21.5),
        ),
    )

    wrapped = service_data(3, 25, report.get_bytes(byte_order))

    assert (
        HousekeepingReport.from_service_data(wrapped, definitions, byte_order) == report
    )


def test_housekeeping_report_rejects_invalid_data() -> None:
    definition = HousekeepingParameterDefinition(
        1, 4, HousekeepingParameterType.SIGNED_INTEGER
    )
    with pytest.raises(ValueError, match="unique"):
        HousekeepingReport(
            1,
            (
                HousekeepingParameter(definition, 1),
                HousekeepingParameter(definition, 2),
            ),
        )
    with pytest.raises(ValueError, match=r"TM\(3,25\)"):
        HousekeepingReport.from_service_data(service_data(3, 10), ())
    with pytest.raises(ValueError, match="length"):
        HousekeepingReport.from_service_data(
            service_data(3, 25, b"\x01"), (definition,)
        )


def test_housekeeping_ids_use_pusutilities_framework_widths() -> None:
    definition = HousekeepingParameterDefinition(
        0xFFFFFFFF, 4, HousekeepingParameterType.SIGNED_INTEGER
    )
    report = HousekeepingReport(0xFF, (HousekeepingParameter(definition, 1),))

    assert (
        HousekeepingReport.from_service_data(report.to_service_data(), (definition,))
        == report
    )
    with pytest.raises(ValueError, match="unsigned 8-bit"):
        HousekeepingReport(0x100, ())
    with pytest.raises(ValueError, match="unsigned 32-bit"):
        HousekeepingParameterDefinition(
            0x100000000, 4, HousekeepingParameterType.SIGNED_INTEGER
        )


def test_iss_housekeeping_is_pusutilities_data_sst25() -> None:
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

    report = create_iss_housekeeping_report(state)
    packet = create_iss_housekeeping_packet(state, sequence=9)
    raw = packet.get_bytes()
    restored_packet = SourcePacket(raw, ByteOrder.BIG_ENDIAN)
    restored_report = HousekeepingReport.from_service_data(
        restored_packet.packet_data_field.data, TCS_HOUSEKEEPING_DEFINITIONS
    )
    values = {
        parameter.parameter_id: parameter.value
        for parameter in restored_report.parameters
    }

    assert report.structure_id == ISS_HOUSEKEEPING_STRUCTURE_ID
    assert len(report.parameters) == 36
    assert len(report.get_bytes()) == 145
    assert report.get_bytes().hex() == (
        "0141a0000041a0000041a0000041a8000041a8000041a8000041b00000"
        "41b0000041b0000041b8000041b8000041b8000041c0000041c0000041c00000"
        "41c8000041c8000041c8000041d0000041d0000041d0000041d8000041d80000"
        "41d8000041e0000041e0000041e0000000000000000000010000000000000000"
        "0000000000000000000000000000000000000000"
    )
    assert restored_packet.is_tm_packet()
    assert restored_packet.packet_data_field.data.service_type == 3
    assert restored_packet.packet_data_field.data.service_sub_type == 25
    assert restored_packet.packet_header.sequence_control.sequence_count == 9
    assert PacketErrorControl.verify_crc(raw)
    assert all(values[parameter_id] == 20.0 for parameter_id in TCS_THERMISTOR_IDS[0])
    assert values[TCS_HEATER_INDICATOR_IDS[0]] == 0
    assert values[TCS_HEATER_INDICATOR_IDS[1]] == 1


def test_tcs_structure_matches_plugin_parameter_metadata() -> None:
    assert tuple(item.parameter_id for item in TCS_HOUSEKEEPING_DEFINITIONS) == (
        *(parameter_id for group in TCS_THERMISTOR_IDS for parameter_id in group),
        *TCS_HEATER_INDICATOR_IDS,
    )
    assert all(item.number_of_bytes == 4 for item in TCS_HOUSEKEEPING_DEFINITIONS)
    assert all(
        item.parameter_type is HousekeepingParameterType.FLOAT
        for item in TCS_HOUSEKEEPING_DEFINITIONS[:27]
    )
    assert all(
        item.parameter_type is HousekeepingParameterType.SIGNED_INTEGER
        for item in TCS_HOUSEKEEPING_DEFINITIONS[27:]
    )
