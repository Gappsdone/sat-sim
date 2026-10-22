# Pus

## PUS library (Python port)

`pus_library` ports the Java library's PUS packet primitives into a Python
module: packet identifiers and primary headers, TC/TM data-field headers, CUC
time, time-sync quality, packet payload containers, source-packet creation and
parsing, and CRC-16/CCITT-FALSE validation. Supported service type/subtype
metadata is available through `service_data`; service payloads are retained as
opaque bytes so service-specific application formats can be added without
changing packet framing.

```python
from pus_library import SourcePacket, service_data

ping = service_data(17, 1)  # TC(17,1)
packet = SourcePacket.get_source_packet(ping, local_prid=1, destination_prid=100)
wire_bytes = packet.get_bytes()
assert packet.verify_crc()
received = SourcePacket(wire_bytes, SourcePacket.DEFAULT_BYTE_ORDER)
```

The port's wire-format and regression tests are in `tests/test_pus_library.py`.
The original Java JUnit suite is separate in the source library checkout; its
Maven configuration skips tests by default, so run it explicitly with
`mvn test -DskipTests=false`.

### PUS service 1 telecommand verification

The live dispatcher emits TM(1,1) acceptance-success and TM(1,7)
execution-completion-success reports when their corresponding TC acknowledgement
flags are set. Unsupported commands or invalid headers receive TM(1,2), while
invalid application data receives TM(1,8). Each report references the original
TC packet ID and sequence control; failures append a 16-bit fault ID. This
application-data layout matches PUSUtilities Java `VerificationReport` and
`DataSST1`, `DataSST2`, `DataSST7`, and `DataSST8`.

### PUS service 17 connection test

The live simulator handles a TC(17,1) connection-test request addressed to the
ISS application process and returns an empty TM(17,2) response to the request's
source PRID. This is available immediately after publisher construction, before
the first simulation step. The empty application-data layout and PRID reversal
match PUSUtilities Java `st17.DataSST1`.

### PUS service 140 thermal parameters

The live simulator handles TC(140,2) parameter requests and sends TM(140,3)
reports, and handles TC(140,1) on/off assignments for the nine heater indicator
IDs. Thermistor IDs are read-only. Unknown IDs, invalid values, and malformed
lengths are rejected without applying a partial command. Requests addressed to
another PRID are ignored. The packet-caster subtypes 31–34 are not simulated.

The application-data layout follows PUSUtilities Java `DataSST2` and
`ParameterManagementData`: one-byte NPAR followed by big-endian four-byte IDs;
set/report entries also carry four-byte values. TCS parameter IDs and sizes are
from `plugin_tcs`'s `TCS.java` assignments, shared with the Service 3 housekeeping
mapping in `src/sat_sim/services/housekeeping.py`.
