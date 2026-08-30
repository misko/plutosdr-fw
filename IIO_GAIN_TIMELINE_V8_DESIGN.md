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

The new provider advertises `iio,buffer-metadata=4` and emits metadata record
version 7 only when the client sends the explicit provider-v4 envelope.  The
legacy 104-byte tandem request and its burst/ring suffixes retain their existing
version-6 behavior and byte layout.

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
- Direct USB/IP gadget protocol v3 is unchanged.  It does not own the tandem
  event lease, so authoritative AUTO timelines there are a separate feature.
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
