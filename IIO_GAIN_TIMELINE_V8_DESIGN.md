# IIO gain timeline v8

## Release invariant

IQ validity is determined by the DMA sample counter and the tandem FPGA event
stream.  Scheduler-timed AD936x gain and RSSI reads may annotate a frame, but
missing telemetry must never invalidate otherwise complete IQ.

This release fixes the buffered-capture failure in which a historical DMA
frame was dequeued after the gain sampler had advanced beyond it.  Keeping the
sampler alive did not make its Linux/SPI observations sample-clock complete,
so a valid refill could still terminate with `ENODATA`.

## Versioned contract

The new provider advertises ABI 4 in the additive
`iio,buffer-metadata-abi-versions` set and emits metadata record version 7 only
when the client sends the explicit provider-v4 envelope.  The legacy scalar
advertisement remains `iio,buffer-metadata=3`; the 104-byte tandem request and
its burst/ring suffixes retain their existing version-6 behavior and byte
layout.  In particular, the inner tandem request retains required-features
mask `0x00000007`; the outer ABI-4 envelope requires mask `0x0000000f`, and the
provider separately proves FPGA ABI 2 plus the `SAMPLE_FENCE` capability before
acquisition.

The 32-byte little-endian envelope is:

| Offset | Type | Field | Required value |
| ---: | --- | --- | --- |
| 0 | `u32` | magic | `0x31524d53` (`SMR1`) |
| 4 | `u16` | version | 1 |
| 6 | `u16` | header bytes | 32 |
| 8 | `u32` | required features | `0x0000000f` |
| 12 | `u16` | metadata record version | 7 |
| 14 | `u16` | transport kind | 0 ordinary, 1 burst, 2 ring |
| 16 | `u16` | tandem request bytes | 104 |
| 18 | `u16` | transport request bytes | 0, 32, or 48 |
| 20 | `u32` | reserved | 0 |
| 24 | `u32` | reserved | 0 |
| 28 | `u32` | reserved | 0 |

The required provider features are FPGA gain timeline, exact event sequence,
optional RSSI telemetry, and typed capture errors.  Unknown or missing required
features, malformed nested lengths, and non-zero reserved fields fail before
DMA is armed.

Record v7 adds metadata feature bit 12 (`FPGA_GAIN_TIMELINE`) and metadata flag
bit 24 (`FPGA_GAIN_TIMELINE_VALID`).  It keeps the 124-byte common prefix and
uses a 56-byte v7 tandem extension at offset 124:

1. the existing ownership, state, fault, end-transition, gain-table,
   threshold, configured gain, end-index, and temperature fields;
2. `transition_count_start`;
3. authoritative paired start indices;
4. timeline flags, currently bit 0 `COMPLETE` only; and
5. `event_sequence_start`.

The v7 event record is exactly 16 bytes: sample sequence (`u64`), event
sequence (`u32`), flags (`u16`), and the resulting RX1/RX2 indices (`u8`,
`u8`).  Events are ordered, gap-free modulo 2^32, and lie in
`[frame_start, frame_end)`.  An event at frame start applies to the first
sample; an event at frame end belongs to the next frame.  CLEAR seeds the
hardware event counter so the first emitted event sequence is exactly zero.

Zero SPI observations and unavailable RSSI are valid v7 telemetry states.  In
that case their existing validity flags are clear and their existing read-fail
flags are set.  The authoritative start/end indices, converted gain dB values,
first-change offsets, and exact events remain mandatory.

## Acquisition and ledger ordering

FPGA ABI 2 adds feature bit 3 (`SAMPLE_FENCE`) and register `0x54`, the low
32 bits of the exclusive RX sample boundary.  That fence and the modulo-256
transition counter cross in the same coherent receive-domain status snapshot.
The kernel keeps the existing status structure and ioctl sizes by assigning
the first formerly reserved status word to `sample_counter_fence_low`; it
reads the fence register before the transition register.  The returned
transition count is therefore from the fence's snapshot or a newer one and
covers every gain decision strictly before the fence.

The coherent status record crosses through a four-slot BRAM mailbox.  Each
slot is written as one receive-domain snapshot; Gray-coded pointers publish
only committed slots, and the AXI side drains only while another committed
slot is available, retaining the last complete record.  A full mailbox may
coalesce intermediate observations, but can neither tear a fence/count pair
nor overwrite the record visible to AXI.  This moves the wide crossing out of
slice registers while preserving the same-or-newer read guarantee.

The authoritative provider lifecycle is:

1. parse and validate the complete request;
2. reserve and prefault optional DDR storage;
3. acquire the tandem lease in HOLD and require zero transitions, zero
   overflows, event sequence zero, and its authoritative initial gain state;
4. create and arm the IIO DMA buffer;
5. for a requested AUTO session, issue the explicit `START_AUTO` ioctl only
   after step 4; legacy providers retain their original one-phase lifecycle;
6. after each refill, wait until the modulo-32-bit sample fence reaches the
   frame's exclusive end, then freeze its same-or-newer transition watermark;
7. drain and validate the event FIFO through that watermark;
8. transactionally resolve the frame timeline;
9. attach any available SPI/RSSI telemetry and serialize metadata; and
10. commit the tandem ledger and DMA sequence only after serialization succeeds.

The host independently maintains the same transaction boundary.  Its first
accepted ABI-4 frame must start at transition count zero and event sequence
zero.  Every later frame must begin at the preceding transition endpoint and
at the preceding event-sequence start plus event count modulo 2^32, under the
same ownership and gain-table contract.  If the current frame has no event at its first sample,
its start gain/index endpoint must equal the preceding
frame's end endpoint.  If one or more ordered events occur at the current
frame's first sample, the preceding end endpoint is their input baseline: each
direction/result must be valid in order and the current start endpoint must
equal the final boundary-event result, with dB direction consistent with the
index change.  The host advances this ledger only after the complete frame,
CRC, DMA continuity, and timeline checks pass; individually valid records may
not hide a missing boundary transition.

The transition counter is extended from its hardware modulo-256 value only
when the delta is unambiguous and within the admitted FIFO/ledger window.
The 32-bit sample fence is compared modulo 2^32 only while the admitted live
window is below 2^31 samples, making before/after unambiguous across wrap.
Status faults, FIFO overflow, event-sequence gaps, sample regression, malformed
geometry, and DMA counter gaps remain fail-closed.

## Failure domains

Ring status v2 distinguishes target completion, DMA failure, DMA counter gap,
gain-event gap, gain-event overflow, metadata encoding/protocol failure,
consumer stall, and client cancellation/disconnection.  The provider assigns
the domain at the failure source; errno alone is not used to guess it.

## Compatibility and scope

- Metadata ABIs 1 through 3 and record versions 1 through 6 keep their strict
  parsers and golden byte vectors.
- The legacy scalar discovery attributes remain
  `iio,buffer-metadata=3` and `iio,buffer-metadata-status=1`, so an older host
  can continue to request record v6 and status v1 from a v8 server.  New hosts
  discover the additive protocols through
  `iio,buffer-metadata-abi-versions=1,2,3,4` and
  `iio,buffer-metadata-status-versions=1,2`; only an ABI 4 request selects
  record v7 and status v2.
- Direct USB/IP gadget protocol v3 is unchanged.  It does not own the tandem
  event lease, so authoritative AUTO timelines there are a separate feature.
- A candidate names one exact raw IIO hardware model.  The supported Pluto+
  Rev.C set contains `Z7010-AD9363A` and `Z7010-AD9361`; it does not treat them
  as interchangeable within a deployment receipt.  The boot gadget derives
  this runtime string from the selected live device-tree `compatible`, while
  `mode=2r2t` is an independent setting, so the model string alone is not a
  2R2T proof.  Preboot, postboot, and restored observations must remain
  byte-for-byte equal to the model selected by the artifact, while the
  dual-RX qualification proves the required 2R2T runtime layout.
- This release fixes IIO over USB and IIO over physical Ethernet: ordinary
  capture supports single and dual RX, while DDR-ring capture retains its
  advertised single-RX-only layout.
- No persistent radio write is permitted before the exact candidate bytes pass
  RAM-only qualification on the two reserved radios.

## Release gates

Portable gates cover request mutation, legacy goldens, pure timeline boundary
and wrap cases, CDC-delayed events, lifecycle ordering, typed failures, missing
telemetry, sanitizer runs, and package installation.  Hardware gates run HOLD
and AUTO over ordinary and 200 MB ring capture on both reserved radios,
including repeated 200/600-frame regressions and a 5,000-frame soak.  USB tests
may run per-radio in parallel; physical-LAN load is serialized.  The exact
final release bytes are RAM-booted and requalified after the final source merge
before the GitHub release is created.
