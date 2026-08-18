# Tandem AGC v2 design contract

Status: draft implementation contract

This is a forward-only design based on the v6 firmware source graph. It does
not preserve the control, metadata, or register ABI from the abandoned tandem
AGC v1 pull request. The useful v1 RTL and verification ideas may be ported only
after they satisfy this contract.

## 1. Goals

Tandem AGC changes the two AD9361 receive gains together, from FPGA logic, and
records every accepted change on the same sample counter as RX IQ. The system
must remain safe if a host exits, a network connection disappears, iiOD dies,
the FPGA FIFO fills, the AD9361 leaves RX-active state, or any enable step
fails.

The design has one supported path:

- one versioned session request;
- one exclusive owner;
- one atomic acquire operation;
- one sample-aligned metadata schema;
- one mandatory rollback path.

There is no legacy tandem mode, raw remote register interface, or silent
feature downgrade.

## 2. Component boundaries

### FPGA

The FPGA owns only real-time decisions and deterministic event production. It
measures RX1/RX2 power, applies the paired decision table, drives both AD9361
CTRL_IN pin pairs, maintains the modeled gain indices, and emits accepted
transitions into an asynchronous FIFO.

The FPGA must fail closed. Reset selects PS/legacy pin ownership. A controller
fault moves the controller to hold, suppresses pin pulses, and raises a sticky
fault. Ownership changes must never create a CTRL_IN edge.

### Linux

Linux is the authority for the ownership transaction. A tandem platform driver
owns the FPGA MMIO region and exposes:

- a read-only, zero-channel `tandem-agc` IIO device for capability and status
  discovery;
- an exclusive local event/session character device used only by the iiOD
  metadata provider;
- a versioned acquire ioctl carrying the complete configuration;
- fixed-size event reads and explicit fault/overflow reporting.

The driver coordinates with the AD9361 driver under a defined lock order. It
validates the radio, snapshots every modified register and gain setting,
programs the controller, verifies readback, and arms the ownership mux as the
last step. Release disarms first and restores the complete snapshot.

While a lease is active, conflicting AD9361 writes return `-EBUSY`. This
includes RX hardware gain, gain-control mode, gain-table selection or reload,
RX LO/band changes, sample-rate changes that invalidate controller timing,
ENSM changes, initialize/reset, driver unbind, and direct debug-register
writes. Unexpected hardware state is a fault and triggers rollback.

Closing the session file descriptor releases the lease. This is mandatory
process-death cleanup, not an optional userspace convention.

### libiio and iiOD

libiio transports opaque, provider-owned session requests and returns opaque
metadata atomically with the matching IQ refill. It does not understand tandem
thresholds or event records.

The metadata buffer is the remote ownership lease:

1. the host creates a metadata-aware RX buffer with a required session request;
2. iiOD passes the request to the metadata provider;
3. the provider opens the local exclusive session device;
4. after the kernel RX buffer is ready, the provider issues one acquire ioctl;
5. every refill returns IQ and metadata for exactly the same sample range;
6. buffer close, transport loss, or iiOD teardown closes the session device;
7. the kernel disarms and restores the radio.

The libiio request API is generic. The request is a byte string with a size
limit; its schema belongs to the installed metadata provider. The wire command
passes the byte count followed by the exact bytes. Unknown, malformed, or
unsupported requests fail buffer creation. There is no negotiated downgrade.

The metadata provider lifecycle receives the request at `open`, acquires only
after `buffer_opened`, fences collection in `before_refill` and `after_refill`,
drains and partitions events in `get`, and releases in `close`.

### SPF host

SPF owns the tandem session-request and radio-metadata schemas. It builds the
request, creates the metadata buffer, decodes every returned frame, rejects any
fault or sequence discontinuity, and stores the exact event series. It does not
perform sensitive multi-step register programming from the host.

## 3. Public topology

| Interface | Purpose | Mutability |
| --- | --- | --- |
| `ad9361-phy` | Existing radio controls | Existing writes, interlocked while leased |
| `cf-ad9361-lpc` | RX IQ buffer | Existing scan data plus metadata-buffer API |
| `tandem-agc` | Capabilities and live status | Read-only IIO attributes |
| `/dev/tandem-agc-events` | Atomic local lease and event drain | Exclusive to the iiOD provider |

The tandem IIO device has no scan channels and never exposes arbitrary MMIO.
At minimum it reports ABI version, FPGA identity/version, supported modes,
state, ownership epoch, current RX indices, sticky faults, FIFO depth/level,
and transition/overflow counters.

## 4. Session request

The first provider request is `spf_tandem_session_request_v1`. All integers are
little-endian and the structure starts with magic, version, and total byte
count. Reserved fields must be zero.

The request contains:

- required metadata features;
- required observation and event capacities;
- controller mode (`hold` or `auto`);
- minimum and maximum gain in physical dB;
- large-overload and low-power thresholds;
- low-power dwell and transition cooldown in sample periods;
- detector blanking and CTRL_IN pulse widths in controller-clock cycles;
- required behavior on event overflow and synchronization fault.

Configuration is expressed in physical units at the host boundary. The kernel
maps gain dB to the currently loaded full-table indices and reports both the
resolved dB and index values in session status. A table index is never written
to the IIO `hardwaregain` attribute as though it were dB.

Every requested feature is required. Unsupported mode, capacity, timing,
threshold, table, or radio state fails acquire without changing ownership.

## 5. Ownership state machine

The authoritative kernel states are:

```text
IDLE -> VALIDATING -> ARMED_HOLD -> ARMED_AUTO
  ^          |             |            |
  |          +-----------> FAULTED <-----+
  |                           |
  +-------- RESTORING <-------+
```

Rules:

- only `IDLE` accepts an acquire;
- only the exclusive session descriptor can acquire or release;
- validation and programming occur before FPGA pin ownership;
- the ownership mux is armed last and disarmed first;
- every acquire increments a nonzero ownership epoch;
- events from another epoch are never returned in a frame;
- all failure exits pass through `RESTORING`;
- failure to restore is reported as a permanent kernel fault and leaves FPGA
  pulses suppressed with PS/legacy ownership selected;
- closing the descriptor from any armed or faulted state initiates restore.

## 6. AD9361 transaction

Acquire performs one kernel-side transaction:

1. lock tandem, then AD9361 using the documented global lock order;
2. verify the FPGA ID and ABI;
3. verify full gain-table mode and supported band/table mapping;
4. verify ENSM is RX-active;
5. verify both receivers and required CTRL_OUT detector routing are available;
6. snapshot gain modes, gains, CTRL_OUT routing, pin-control fields, step-size
   fields, timing-dependent fields, and every other register to be changed;
7. resolve requested dB limits to exact table indices;
8. place both receivers in manual gain mode and seed an explicitly selected,
   verified common gain;
9. program AD9361 pin-control behavior with read-modify-write operations;
10. program FPGA thresholds, limits, timing, epoch, and modeled indices;
11. clear FIFO and sticky faults;
12. verify the event consumer lease and all readbacks;
13. transfer value and tri-state ownership with outputs held inactive;
14. enter hold, then auto if requested.

Release reverses ownership first, suppresses all pulses, drains or retires the
epoch, and restores the complete snapshot. No caller supplies a guessed
"legacy mode" during release.

## 7. FPGA decision contract

For each completed power-measurement period:

| Condition | Decision |
| --- | --- |
| Either channel reports large overload | Decrease both gains by one index |
| Either channel reports small-ADC inhibit | Hold |
| Both channels remain below low threshold for the full dwell | Increase both gains by one index |
| Otherwise | Hold |

An accepted change requires auto mode, completed cooldown, no active fault,
consumer readiness, synchronized modeled/hardware indices, and room in the
event FIFO. Limits clamp both channels as a pair. One accepted transition emits
exactly one event.

## 8. Metadata contract

The next SPF radio metadata schema is the only supported tandem schema. It
contains a fixed prefix, fixed negotiated-capacity arrays, and a trailing CRC.
The prefix includes the ownership epoch, tandem state/fault flags, observation
and event counts, capacities, record sizes, and cumulative overflow counters.

Each 16-byte tandem event contains:

```text
u64 sample_sequence
u32 event_sequence
u16 flags
u8  rx1_gain_index
u8  rx2_gain_index
```

Flags identify direction, reason, channel-change validity, and lock state. The
event sequence makes loss detectable. The frame carries the epoch. Gain-table
identity and endpoint observations provide the index-to-dB interpretation.

The provider partitions events by the half-open IQ interval
`[first_sample_sequence, first_sample_sequence + samples_per_channel)`. Events
from the next frame are retained. Pre-frame events update the opening state but
are not emitted in the current array. Sequence holes, non-monotonic sample
counters, epoch changes inside a frame, FIFO overflow, or insufficient event
capacity make tandem metadata invalid explicitly; they never produce a
plausible partial series.

## 9. Failure policy

The following suppress pulses immediately and end auto mode:

- ENSM not RX-active;
- modeled RX indices diverge from verified hardware state;
- consumer lease loss;
- FIFO overflow or event-sequence loss;
- illegal ownership transition;
- MMIO or SPI failure;
- AD9361 reset/reinitialize attempt;
- controller watchdog expiry.

IQ transport may continue, but the frame is marked tandem-invalid and SPF must
not use its gain series. Recovery requires teardown and a new acquire; auto
re-arm is forbidden.

## 10. Verification checkpoints

### C0: contract

- request, status, ioctl, FPGA register, and metadata layouts have golden
  byte-vector tests;
- generated/shared definitions eliminate hand-copied constants;
- malformed request and unknown required-feature tests are red before code.

### C1: libiio transport

- network and USB backends pass the request byte-for-byte to iiOD;
- the local iiOD metadata provider receives the exact request at its open boundary;
- provider-open failure leaves no RX buffer or provider context;
- connection loss invokes provider close exactly once;
- metadata and IQ remain atomically paired across refill errors.

### C2: Linux ownership

- every acquire step has failure injection and proves complete rollback;
- conflicting AD9361 writes return `-EBUSY` while leased;
- descriptor close, process death, ENSM loss, FIFO overflow, and device removal
  all suppress pulses and restore state;
- gain dB/index conversion is tested against each supported gain table.

### C3: FPGA

- directed and randomized decision-table tests;
- CDC, reset, ownership-edge, pair-simultaneity, clamp, cooldown, dwell, FIFO,
  epoch, and fault assertions;
- full integrated synthesis with nonnegative timing slack and an explicit
  utilization ceiling;
- the v6 image remains behaviorally legacy when no tandem session exists.

### C4: end-to-end software

- synthetic FPGA records round-trip through the kernel drain, iiOD metadata
  provider, libiio C/Python bindings, SPF decoder, and Zarr store;
- event reconstruction agrees with endpoint observations;
- USB-IIO, network-IIO, direct USB, and direct IP use the same metadata schema.

### C5: hardware

- RAM boot before permanent flashing;
- one-radio smoke and injected-fault tests;
- four-radio TX2-to-RX1/RX2 paired stepping and sample-alignment tests;
- threshold/dwell/cooldown sweeps at multiple sample rates and RF bands;
- host kill, cable removal, iiOD restart, ENSM disturbance, FIFO pressure, and
  repeated acquire/release testing;
- multi-hour four-radio soak with zero unexplained events, sequence holes,
  overflows, stuck ownership, or boot-time TX regression;
- permanent flashing only after the checkpoint report is reviewed.
