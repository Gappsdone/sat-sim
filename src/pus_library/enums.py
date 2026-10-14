from __future__ import annotations

from enum import Enum, IntEnum


class ByteOrder(Enum):
    BIG_ENDIAN = "big"
    LITTLE_ENDIAN = "little"


DEFAULT_BYTE_ORDER = ByteOrder.BIG_ENDIAN


class PacketType(IntEnum):
    TELEMETRY = 0
    TELECOMMAND = 1

    @property
    def short_name(self) -> str:
        return "TM" if self is PacketType.TELEMETRY else "TC"

    @classmethod
    def type(cls, value: int) -> PacketType:
        return cls(value)


class PacketCategory(IntEnum):
    TIME = 0
    ACKNOWLEDGE = 1
    HK_RT = 2
    TABLE = 3
    HK_PB = 4
    UNKNOWN = 6
    EVENT = 7
    DIAGNOSTIC = 8
    DUMP = 9
    TELECOMMAND = 12
    OCC_EGSE = 14
    IDLE = 15

    @classmethod
    def pcat(cls, value: int) -> PacketCategory:
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN


class FaultID(IntEnum):
    SYS_FID_INVALID_VALUE = 0x0100
    PRID_NOT_RESPONDING = 0x0101
    PRID_COMMUNICATION_TIMEOUT = 0x0102
    PRID_COMMUNICATION_ERROR = 0x0103
    PRID_COMMUNICATION_LINK_LOST = 0x0104
    PRID_REMOTE_ERROR = 0x0105
    PRID_INVALID_SERVICE_TYPE = 0x0106
    ILLEGAL_APID = 0x0200
    INCOMPLETE_OR_INVALID_LENGTH_PACKET = 0x0201
    INCORRECT_CHECKSUM = 0x0202
    ILLEGAL_PACKET_TYPE = 0x0203
    ILLEGAL_PACKET_SUBTYPE = 0x0204
    ILLEGAL_OR_INCONSISTENT_APPLICATION_DATA = 0x0205
    ILLEGAL_TCS_SF = 0x0206
    ILLEGAL_TCS_MAP_ID = 0x0207
    INVALID_NPAR = 0x0208
    NPAR_LENGTH_DISCREP = 0x0209
    INVALID_SID = 0x020A
    INVALID_COLL_INT = 0x020B
    MAX_HK_NB_EXCEEDED = 0x020C
    MAX_TOTAL_SID_NB = 0x020D
    INVALID_PAR_ID = 0x020E
    UNKNOWN_SID = 0x020F
    SID_ENABLED = 0x0210
    SID_DEFINED = 0x0211
    SID_NOT_DEFINED = 0x0212
    TM_SIZE_EXCEEDED = 0x0213
    SID_UNKNOWN_EID = 0x0214
    INVALID_NFA = 0x0215
    NREP_INCO_INTERVAL = 0x0216
    UNKNOWN_FORW_PID = 0x0220
    FORW_INVALID_RID = 0x0221
    ILLEGAL_VERSION = 0x0222
    ILLEGAL_P_TYPE = 0x0223
    ILLEGAL_DFHF = 0x0224
    UNKNOWN_PRID = 0x0225
    ILLEGAL_PCAT = 0x0226
    ILLEGAL_SF = 0x0227
    ILLEGAL_NPAR = 0x0228
    INVALID_PLENGTH = 0x0229
    LENGTH_DISCREP = 0x022A
    ILLEGAL_SHF = 0x022B
    ILLEGAL_TC_PUS = 0x022C
    UNKNOWN_S_TYPE = 0x0300
    UNKNOWN_S_SUBTYPE = 0x0301
    CS_DISCREP = 0x0302
    TC_INBUF_OVERFLOW = 0x0303
    MTU_TOO_SMALL = 0x0304
    REPORT_ABORTED = 0x0305
    DUMP_ERROR = 0x0400
    TC_POOL_OVERFLOW = 0x0401
    ACT_SERVICE_ENABLED = 0x0402
    DETECTION_OVERFLOW = 0x0403
    UNKNOWN_ACTION = 0x0404
    ACTION_ACTIVE = 0x0405
    NACT_LEN_DISCREP = 0x0406
    FORBIDDEN_EID = 0x0407
    NOT_SET = 0xFFFF

    @classmethod
    def get_from(cls, value: int) -> FaultID:
        try:
            return cls(value)
        except ValueError:
            return cls.NOT_SET


class EventID(IntEnum):
    EID_IOH_STATE_TRANSITION_FAILED = 0xF100
    EID_PCDU_EQUIPMENT_SWITCH_STATUS_CHANGE = 0x1234
    EID_DUMMY = 0xFFFF

    @classmethod
    def get_from(cls, value: int) -> EventID:
        try:
            return cls(value)
        except ValueError:
            return cls.EID_DUMMY

    getFrom = get_from
