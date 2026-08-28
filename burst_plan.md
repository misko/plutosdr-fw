# Pluto+ bounded DDR burst-capture plan

Status: **parked design; no implementation authorized**

This note preserves the investigation into buffering single-receiver captures
in ordinary Pluto+ DDR. It is intentionally outside the single-RX metadata RC1
release. Resume this work only as a separately reviewed feature after the RC1
release and issue #50 stabilization work.

## Objective

Capture one complete complex receiver at 25 MS/s for a bounded one- or
two-second interval without requiring the host transport to sustain the full
100 MB/s wire payload in real time. Preserve authoritative device-time
continuity evidence, restore the exact prior radio state, and transfer the
completed burst to the host only after acquisition stops.

This is a burst recorder, not a claim of continuous 25-MS/s streaming.

## Measured baseline

Measurements were taken on 2026-08-28 using radio
`104473b80a16000de6ff2000f8a6beca79`, RAM-booted with
`v0.42-plutoplus-spf-single-rx-metadata-rc1`, over its physical
`192.168.1.0/24` Ethernet path.

| Metric | Idle | During a 25-MS/s RX0 job |
|---|---:|---:|
| Linux-usable RAM | 506,872 KiB (495.0 MiB) | unchanged |
| `MemAvailable` | 439,484 KiB (429.2 MiB) | about 421,904 KiB (412.0 MiB) |
| CMA total | 65,536 KiB (64 MiB) | 65,536 KiB |
| CMA free | 65,252 KiB | about 48,876 KiB |
| IIOD resident set | about 2.4 MiB | about 2.4 MiB |
| swap | none | none |

The monitored job used four 4-MiB DMA buffers and transferred 400 MiB to the
host. Ordinary RAM did not grow with transferred bytes. CMA dropped by almost
exactly 16 MiB while the IIO queue was active and recovered after teardown.
This proves that the current path retains only the fixed DMA queue and does not
accumulate a capture in normal DDR.

During that job IIOD consumed roughly 36--45% of the complete two-core CPU,
equivalent to approximately 72--90% of one core, while total idle CPU remained
about 50--59%. Observed IP delivery was 54--56 MB/s.

The radio exposes separate `/tmp` and `/dev/shm` tmpfs mounts with apparent
limits of about 247.5 MiB each. They consume the same physical DDR and their
capacities must not be added together. The system has no swap.

## Capacity calculation

One complete complex receiver is CI16: one 16-bit I word plus one 16-bit Q
word, or four bytes per sample time.

| Duration | Sample times | Raw bytes | Raw MiB | Approximate RAM left from the observed active baseline |
|---|---:|---:|---:|---:|
| 1 second | 25,000,000 | 100,000,000 | 95.4 MiB | 316.6 MiB |
| 2 seconds | 50,000,000 | 200,000,000 | 190.7 MiB | 221.3 MiB |
| 3 seconds | 75,000,000 | 300,000,000 | 286.1 MiB | 125.9 MiB |

One and two seconds fit comfortably in current ordinary RAM. Three seconds is
not an initial target: it exceeds the tmpfs cap, leaves substantially less
no-swap headroom, and has not earned a reliability justification.

Dual RX doubles every payload figure. A two-second dual-RX burst would require
about 381.5 MiB before queue and process overhead and is not a safe target on
this platform.

## Current path and missing capability

IIOD currently performs one `iio_buffer_refill()`, then synchronously sends the
returned buffer to the client. The local backend allocates and maps the fixed
kernel DMA blocks, but there is no second-stage ordinary-DDR ring. When the
host link is slower than the configured sample stream, ordinary libiio can
continue returning buffers while device-time gaps accumulate; delivered host
bytes alone are not continuity proof.

The missing capability is therefore not a larger IIO frame. It is a bounded,
preallocated, normal-DDR capture stage with explicit continuity and ownership
semantics.

## Proposed architecture

Prefer an opt-in IIOD/libiio burst operation with a matching Pluto Plus Utils
command. Keeping the operation inside the existing radio data owner avoids a
second local process racing IIOD for the same IIO buffer.

The operation should:

1. Attest the exact radio, firmware ABI, receiver geometry, and TX-safe state.
2. Acquire an exclusive bounded-capture lease and reject concurrent readers.
3. Snapshot the exact RX settings and IIO buffer state.
4. Compute the requested byte count with checked arithmetic.
5. Enforce single RX and an initial duration ceiling of two seconds.
6. Reserve a fixed system-memory safety margin of at least 128 MiB.
7. Allocate, prefault, and retain a 95.4- or 190.7-MiB anonymous/memfd ring.
8. Keep the validated four-by-4-MiB CMA staging queue.
9. Capture exact local refills into the DDR ring without concurrent network
   transmission.
10. Retain ABI-3 metadata per refill, including first-sample sequence, stream
    generation, flags, receiver mask, payload size, and CRC.
11. Reject any counter gap, regression, overflow ambiguity, short refill,
    layout mismatch, or terminal-state failure. Do not silently rebase time.
12. Stop after exactly 25,000,000 or 50,000,000 sample times.
13. Restore and verify the exact original RX settings before making the burst
    downloadable.
14. Return a durable capture receipt, then transfer the frozen burst to the
    host and release the radio-side memory deterministically.

Hashing and optional format conversion should occur after capture, not in the
real-time ingestion loop. The first implementation should retain raw CI16 and
must not add compression, resampling, or quantization.

## Why not enlarge CMA or the kernel queue

The Pluto kernel intentionally reserves a bounded 64-MiB CMA pool. A one-second
single-RX burst already needs 95.4 MiB, so CMA cannot satisfy the objective.
The platform's fixed pstore placement and Zynq DMA-visible address constraints
also prevent treating all 512 MiB of DDR as one large coherent DMA arena.

Live qualification found:

- 16-MiB aggregate queues are healthy across the tested ladders;
- selected 24-MiB configurations work at 12.5 and 25 MS/s under an explicit
  unsafe qualification override;
- a four-by-8-MiB, 32-MiB queue timed out at 1 MS/s and reproduced the
  persistent RX-DMAC completion wedge.

Increasing CMA or queue depth neither solves host-link throughput nor provides
the required one- or two-second capacity. It also expands the teardown failure
surface. Keep CMA as staging memory and use ordinary DDR for the burst.

## Transport consequence

At the measured 54--56 MB/s IP rate, a completed burst needs approximately:

- 1.8--1.9 seconds to drain a one-second capture;
- 3.6--3.8 seconds to drain a two-second capture.

Capture and drain cannot run continuously at 25 MS/s because the backlog grows
by roughly 44--46 MB/s. Double buffering only postpones exhaustion. The
contract must explicitly be capture, stop, verify, then transfer.

## Qualification gates before implementation is promotable

### B1: local sink throughput

Using an exact-restore harness, prove RX0 local capture to `/dev/null` at
25 MS/s for at least two seconds. Require at least 120 MB/s measured ingestion
headroom and zero counter gaps or device overflows.

### B2: prefaulted DDR throughput

Repeat into a prefaulted 200-MB normal-RAM ring. Measure CPU, memory bandwidth,
CMA, scheduler latency, refill cadence, and continuity. The complete two-second
capture must finish without allocation during the hot path.

### B3: failure atomicity

Inject client disconnect, timeout, cancellation, allocation refusal, metadata
error, and insufficient-memory conditions. Every path must release the ring,
close the buffer, restore the exact RX configuration, and leave the data plane
immediately reusable without reboot.

### B4: truthful continuity

Plant a known dequeue delay and require the authoritative counter to report
the exact missing sample-time count. A successful byte count or an overflow
flag alone must never authorize a capture.

### B5: memory boundary

Exercise one- and two-second bursts with the full normal service set running.
Reject requests that cannot retain the safety reserve. Confirm no OOM kill,
CMA starvation, tmpfs leakage, stale capture, or cross-client data exposure.

### B6: transport and receipt

Download the frozen burst over both IP and USB where supported. Verify exact
byte count, cryptographic hash, metadata-to-IQ association, cleanup, and a
receipt that distinguishes capture duration from later transfer duration.

### B7: soak

Repeat bounded capture/drain cycles long enough to expose fragmentation,
resource leakage, sequence reset errors, and teardown races. Include recovery
from an interrupted download without recapturing or corrupting the retained
burst.

## Decisions deliberately deferred

- exact wire command and capability-advertisement version;
- whether the retained burst is held only by a memfd or exposed through a
  private tmpfs object;
- whether downloading may resume after a host reconnect;
- exact retention timeout and secure erasure behavior;
- whether RX1 is enabled in the first burst release or follows RX0 validation;
- whether a later FPGA-assisted DDR writer is warranted if the ARM copy path
  cannot sustain the B1/B2 margin.

## Resume criteria

Resume only when all of the following are true:

- single-RX metadata RC1 has been released and its issue #50 ABI is stable;
- the work is scoped as a separate feature with its own source lock and release
  identity;
- Pluto Plus Utils owns the host command, validation, and receipts;
- no shell sidecar or unbounded rootfs file is proposed as the production
  mechanism; and
- B1 and B2 are authorized as diagnostic-only tests before behavioral code is
  written.

