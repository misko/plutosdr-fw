# Pluto+ bounded DDR burst-capture plan

Status: **published, hardware-qualified, and persistently promoted on all five
USB-recoverable radios; the feature remains disabled by default**

This note preserves the design and the resulting qualification evidence for
buffering single-receiver captures in ordinary Pluto+ DDR. The final release
combines the previously published single-RX metadata ABI with the reviewed DDR
extension. Pluto Plus Utils keeps separate immutable RAM-only and persistent
profiles; only the exact hardware-qualified release profile permits QSPI
promotion.

## Optional streaming ring extension (issue #61)

The next additive candidate keeps the qualified sealed burst above intact and
adds a second, independently negotiated mode. Its logical queue is:

```text
FPGA sample counter / AXI DMAC
        -> bounded kernel CMA buffers
        -> prefaulted normal-DDR whole-frame ring
        -> ordinary iiOD USB or IP response
        -> existing libiio metadata refill
```

This is a natural extension of the DMA queue, not a second capture file and not
a claim that 200 MB can be allocated as coherent DMA. The kernel continues to
own the qualified CMA blocks; a dedicated iiOD producer refills those blocks
and commits paired metadata plus IQ into normal DDR while the existing reader
drains committed slots. Producer, committed, consumer and free ownership are
explicit. A slot cannot be overwritten until its complete wire response has
been delivered.

The mode is omitted by default. A versioned `SFRR` suffix requests a capacity
of at most 200,000,000 IQ bytes and exactly one of:

- a positive finite frame target; or
- explicit continuous capture until buffer close.

Capacity rounds down to complete existing IIO frames. Single-RX layout, the
12-ms safe frame-period floor, 128-MiB ordinary-memory reserve, 16-MiB CMA
reserve, and shared one-arena reservation are enforced before capture starts.
Legacy sealed burst, host metadata batching and the streaming ring are mutually
exclusive. Ordinary buffers and dual RX remain unchanged.

Full-ring behavior is backpressure: iiOD stops requesting the next DMA block
until the consumer releases a slot. The already-queued kernel blocks absorb a
short transport stall. If that window is exceeded, the authoritative FPGA
counter detects the first discontinuity; no synthetic continuity or silent
overwrite is permitted. Committed frames drain in order, then the original
producer error is returned. Disconnect cancels DMA, joins the producer, frees
the arena and reservation, and preserves immediate ordinary/ring reuse.

The ordinary IIO buffer also exposes a non-consuming 128-byte `SFRS` snapshot:
state, terminal reason/error, requested and admitted capacity, finite target,
produced/consumed frames, high-water mark, wraps, producer/consumer positions,
and valid last-contiguous/first-unavailable sample boundaries. Python selects
the mode with `ddr_ring_bytes`, `ddr_ring_frames`, and the explicit
`ddr_ring_continuous` flag, then reads status with `ddr_ring_status()`.

Implementation source is locked at libiio
`739a250b92610184b12d773f6a367e549f0dfe29` and Buildroot
`879afd8facb69519ed2328b39d80d6905e416247`. Native stock/SPF/sanitized builds,
portable unit tests, Python contract tests, and a live attached-Pluto proxy
test pass. Firmware CI, RAM deployment, transport ladders, forced disconnect,
memory recovery and ordinary-path regression remain promotion gates.

## Final release and promotion result

Release `v0.42-plutoplus-spf-ddr-burst-v1` is the source-locked firmware commit
`a6b78df100f67c1bcd2528e2fbc0c86b2a8ee2ba`. Protected GitHub Actions run
`33174605592` produced the published DFU with SHA-256
`47bb23ff1d498a5899c4503de33bc818aa908c567eab4e0fc535602ffa296877`,
FIT-body SHA-256
`f40542a7b1a53f4f1b06a5733f068e7b69f1eddff7ab0eb46c0f37f9f37d295a`,
and evidence-bundle SHA-256
`d4bce8fb200cac685d5acbeb0631b6fb0ed214f3d2c7fb5d06e3b36fd62aafd6`.
Both nested checksum manifests and the integrated routed-design verdict pass.
All five release assets were downloaded after publication and compared
byte-for-byte with the qualified CI material.

Pluto Plus Utils merge `daa24ef7a1d170ed1779ae175232660c0d885c09`
binds those exact bytes. Profile `ddr-burst-v1-release-ram` remains explicitly
RAM-only. Profile `ddr-burst-v1-release-persistent-promotion` is the distinct
hardware-qualified mutation policy and guarded upgrade target. The utility
attests the selected serial, direct USB topology, DFU and FIT hashes, metadata
ABI 3, DDR limits, returned identity, and safe TX state around each operation.

The exact release was RAM-booted and persistently written on five local
USB-recoverable radios. The fleet passed 28 RAM-mode and ten post-flash
abrupt-client recovery cycles. Each cycle killed a live 200-MB, 25-MS/s client
and then proved both fresh DDR and ordinary-buffer reuse. All 38 cycles passed
on alternating RX0/RX1 with zero counter gaps, missing samples, or overflow;
unchanged boot and iiOD identity; restored settings; zero live buffers; DDS
off; and both TX channels at -80 dB.

The designated AD9363A radio also completed four full two-second, 25-MS/s,
200-MB captures: RX0 and RX1 over both physical Ethernet and USB. Every capture
reported all 50,000,000 sample times with zero counter gaps, missing samples,
or overflow. Ordinary dual-RX controls passed over both transports with burst
mode disabled. Three additional LAN-only radios passed identity-bound dual-RX
IP ladders at 1, 2.5, and 5 MS/s, but were intentionally not flashed because
no local USB/DFU recovery path was attached.

The 200-MB ceiling, 128-MiB ordinary-memory reserve, 64-MiB CMA pool, one-RX
geometry, provider-owned request extension, sealed-cache refill behavior, and
default-off compatibility contract described below are the released design.
DDR burst is a bounded recorder; it does not increase sustained USB or Ethernet
throughput.

## Historical first candidate and qualification result

The first candidate implements the anonymous-DDR cache in IIOD while retaining
the existing ABI-3 metadata provider, Linux DMA driver, FPGA design, 64-MiB CMA
reservation, and ordinary four-buffer staging queue. Omitted or zero burst
bytes take the original code path. A positive byte budget opts in for exactly
one receiver and is rounded down to a whole number of existing IIO frames.

The immutable source graph is:

- firmware `fdbe3ffaed604cc83f89252a10d2ec8b51b5be58`;
- libiio `6591aa335ee124c32d9ef500f728068d299af71a`;
- Buildroot `9439e15a61ebb5a3a1b2d5a0144876ad80a181e1`;
- unchanged ABI-3 metadata provider `6e2362c0e149bd2a76f7777115a36fb65da80b58`;
- Pluto Plus Utils client/profile `983e1f8`.

The trusted rebased Kalman build is GitHub Actions run `33145187461`. Its complete
bundle and both nested checksum manifests verify. The RAM-qualified DFU is
`plutoplus-spf-ddr-burst-v1-rc1-fdbe3ffaed60-pluto.dfu`, 12,796,147 bytes,
SHA-256 `9024ed3c0ce38efeaf2e30dd71f903e2d65a234b90e7af175d3c196042dc6591`.
The FIT body is 12,796,131 bytes, SHA-256
`b9ceebdbadf144e91be78c2b87aad30691f3ade068f91ad8ab61c72b1b4035d4`.

On 2026-08-28, Pluto Plus Utils loaded those exact bytes into RAM on radio
`104473b80a16000de6ff2000f8a6beca79`; QSPI was not written. The returned
serial, AD9363A PHY, firmware string, metadata ABI 3, tandem device, DDR
capability, 200,000,000-byte ceiling, TX-safe state, and unchanged USB path were
all attested before testing.

| Rebased final-CI hardware gate | Result |
|---|---|
| USB, RX0, 25 MS/s, 200,000,000 bytes / 50,000,000 samples / 2.000 s | 100% counter coverage, 0 gaps, 0 overflow |
| physical Ethernet `enp132s0` to `192.168.1.186`, same maximum burst | 100% counter coverage, 0 gaps, 0 overflow |
| IP, RX1, 25 MS/s, 24,000,000 bytes after forced disconnect | 100% counter coverage, 0 gaps, 0 overflow |
| ordinary dual RX, 5 MS/s after burst testing | 100% counter coverage, 0 gaps, 0 overflow |
| client killed during a 200-MB capture | arena and CMA released; next burst passed; IIOD generation stayed 1 |

The immediately preceding CI build used the same libiio, Buildroot, metadata,
kernel, HDL, and U-Boot component graph. Its broader matrix also passed five
successive sizes from 4.8 to 24 MB over both USB and IP, rejected a
200,000,256-byte request before capture, and completed a 200-MB capture on both
transports without a leak or IIOD restart. The final rebased artifact repeated
the maximum, forced-disconnect/reuse, RX1, and ordinary-path gates above.

The useful A/B at 25 MS/s is explicit: ordinary USB delivered 60% with two
counter gaps and ordinary IP delivered 85.7% with one gap, while burst mode
delivered 100% over both transports. This proves the result comes from the
radio-side DDR stage rather than optimistic host byte accounting.

Pluto Plus Utils measured 519,036,928 bytes of Linux RAM on both CI images.
On the source-identical first CI image, `MemAvailable` was about 450 MB before
the maximum capture, 225,644,544 bytes while the 200-MB arena and DMA queue
were active, and about 450 MB after teardown. CMA moved
from 66,826,240 bytes free to 41,820,160 bytes during capture and recovered to
66,826,240 bytes. After the forced disconnect on the final rebased image,
`MemAvailable` was 449,527,808 bytes, CMA free was 66,822,144 bytes, active RX
buffers were zero, and IIOD remained PID 218, generation 1. The 128-MiB
ordinary-memory reserve and 16-MiB CMA reserve were therefore retained at the
tested ceiling.

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

The exact source path establishes four important facts:

- `libiio/local.c` allocates four coherent CMA blocks by default. Every local
  refill re-enqueues the previously dequeued block and dequeues the next
  completed block.
- `libiio/iiod/ops.c` performs metadata fencing, one local refill, metadata
  construction, and a synchronous transport write in that order.
- the current libiio metadata batch option accumulates responses in **host**
  memory only after the bytes cross USB or IP. It cannot solve a device-side
  transport deficit.
- ABI 3 already provides the required single-RX geometry, a stream generation,
  first-sample counters, exact gap counts, payload length, and header CRC. A
  successful burst does not need a new IQ layout.

## Recommended first architecture

Implement the first version entirely in IIOD and its existing SPF metadata
provider. Keep the qualified Linux DMA driver, FPGA design, CMA reservation,
and four-block kernel queue unchanged. IIOD remains the only owner of the local
IIO buffer and adds one preallocated anonymous-DDR cache behind it.

The feature is a one-shot metadata-buffer policy, not a new streaming backend:

1. Pluto Plus Utils adds one user-visible `--ddr-burst`/`ddr_burst=true` flag.
2. The utility accepts an IQ-byte budget, derives the admitted whole-frame
   count from the existing frame size, and appends a required burst extension
   to the existing opaque metadata-session request.
3. A legacy 104-byte request has no extension and follows the current path
   without allocation or changed behavior.
4. IIOD validates and prefaults the complete cache before enabling the physical
   IIO buffer.
5. After the physical buffer is ready, IIOD acknowledges `OPENM` promptly and
   its existing per-device RX worker immediately enters a burst-capture phase.
   It proactively drains consecutive local refills into the cache without
   sending network or USB data.
6. Every accepted refill is fenced by the existing metadata provider. IIOD
   builds and stores the matching ABI-3 metadata and copies only that frame's
   CI16 IQ bytes from the mapped CMA block into normal DDR.
7. IIOD sends no IQ until all requested frames pass. Any error discards the
   whole cache; a partial burst is never presented as success.
8. After the final frame, IIOD disables and destroys the physical IIO buffer,
   closes the metadata provider to restore its timestamp/tandem state, and
   marks the cache sealed. Pluto Plus Utils verifies restored radio settings
   after the drain.
9. The application's existing `iio_buffer_refill_with_metadata()` calls are
   then satisfied one frame at a time from the sealed cache. Buffer start/end,
   channel iteration, IQ layout, metadata decoding, and artifact writing are
   unchanged.
10. The last delivered frame releases the arena. An additional refill returns
    `-ENODATA`; close remains idempotent.

Starting capture at buffer-open, rather than waiting for the first `READBUFM`,
avoids filling and stalling the four-block DMA queue while host-side setup is
still running. The open acknowledgement remains prompt; the first host refill
waits for the worker to reach `SEALED`. Pluto Plus Utils must take its initial
sample-clock anchors before opening a burst buffer and issue that refill
immediately after the open returns.

This design deliberately performs one ARM `memcpy` per frame. It is the
smallest change that reuses the qualified DMA path. A direct FPGA DDR writer,
scatter-gather kernel arena, larger CMA pool, and separate radio-side capture
process all add substantially more ownership and teardown risk.

The live measurements establish capacity, not copy-path feasibility. This
architecture remains contingent on the B1/B2 tests proving that the ARM can
copy every frame with adequate refill and scheduler margin.

## Opt-in wire and capability contract

Do not add a new IIOD command and do not reinterpret the existing host-side
metadata batch option. Retain `OPENM`, `READBUFM`, and the current refill
response byte layout.

Append a fixed-size provider-owned extension to the valid tandem request. The
extension should contain only:

- magic, version, and total size;
- required-feature bits, initially only `DEVICE_DDR_BURST`;
- the requested IQ-byte budget, which IIOD admits as whole fixed-size frames;
  and
- zeroed reserved words.

The provider accepts the original exact request length as ordinary mode. It
accepts the extended length only when every required bit and reserved field is
valid. It decodes the first 104 bytes with the unchanged tandem decoder and
decodes the tail separately; the tandem ABI itself is not weakened. An old
firmware therefore rejects the flag instead of silently streaming normally.

Keep the burst schema provider-owned. Extend the internal metadata-provider
open contract to return a provider-neutral capture plan containing only mode
and exact frame count. The IIOD core consumes that plan but does not parse SPF
wire fields. The no-metadata provider and legacy requests return ordinary mode.
This is an internal firmware interface, not a new public libiio API.

Keep `iio,buffer-metadata=3` because the metadata and IQ ABI do not change. Add
separate read-only context attributes such as:

- `iio,buffer-ddr-burst=1`;
- `iio,buffer-ddr-burst-max-iq-bytes=200000000`;
- `iio,buffer-ddr-burst-reserve-bytes=134217728`.

Pluto Plus Utils attests these exact values before adding the request
extension. The raw extension is internal. Python callers set
`iio.MetadataBuffer(..., ddr_burst_bytes=X)` and can read back
`ddr_burst_requested_bytes`, `ddr_burst_admitted_bytes`, and
`ddr_burst_frames`. The metadata ladder exposes `--ddr-burst`; it requests
exactly `--frames` whole frames for each rung and records all three values.
Omitting the flag is the control path.

## Initial geometry and bounds

The first release must require metadata ABI 3 and exactly one canonical
receiver, RX0 or RX1. It must reject ordinary buffers, dual RX, cyclic mode,
unbounded captures, and unknown scan masks for this path. Pluto Plus Utils must
force the existing host metadata batch size to one; device DDR burst is the
only batching layer for this mode.

At 25 MS/s, one convenient geometry uses 1,000,000 sample times per frame:

| Quantity | One second | Two seconds |
|---|---:|---:|
| frames | 25 | 50 |
| CI16 IQ bytes | 100,000,000 | 200,000,000 |
| ABI-3 metadata at 3,256 bytes/frame | 81,400 | 162,800 |
| capture duration per frame | 40 ms | 40 ms |

Each physical single-RX DMA block is 4,000,008 bytes: 4,000,000 IQ bytes plus
the eight-byte counter prefix represented as two extra single-RX scan samples.
Four blocks require 16,000,032 bytes, below the validated 16-MiB aggregate
queue ceiling. The complete two-second IQ, metadata, and descriptor cache is
about 190.9 MiB.

For an arbitrary positive byte request, libiio reports both the requested and
admitted byte counts. Admission is `floor(requested / frame_bytes)` whole
frames; fewer than one frame fails. There is no hidden trim: callers can reject
a non-exact admission using the explicit readback. The utility ladder requests
an exact whole-frame product and requires requested and admitted bytes to
match.

The firmware enforces a 200,000,000-IQ-byte limit. At 25 MS/s that is exactly a
two-second single-RX ceiling. The byte ceiling, checked arithmetic, ordinary
memory reserve, CMA reserve, single global reservation, and finite host timeout
bound lower-rate captures without inventing a second duration ABI.

## Memory admission

Use one anonymous private mapping owned by IIOD, not `/tmp`, `/dev/shm`, a
shell helper, or a persistent file. Acquire a process-global burst reservation
so two clients cannot simultaneously prefault competing arenas.

Perform admission and prefaulting in the existing per-device R/W worker,
outside IIOD's global device-list mutex. The metadata provider's open callback
must only validate the request and return the capture plan; it must not perform
the large allocation while unrelated device opens are serialized.

Admission is fail-closed:

1. validate the request and compute IQ, metadata, descriptor, and four-block
   CMA requirements with checked arithmetic;
2. require `mapping_bytes + 128 MiB <= MemAvailable` and require the full
   kernel queue plus a 16-MiB reserve in `CmaFree` before allocation;
3. `mmap()` without overcommit-oriented flags, mark the mapping non-dumpable,
   and write-fault every page before the IIO buffer is enabled;
4. re-read memory facts and retain at least 128 MiB of system-memory headroom;
5. require the complete safe CMA queue plus a CMA reserve; and
6. free the mapping and global reservation on every terminal path.

There is no allocation, compression, conversion, filesystem write, or whole
burst hash in the hot capture loop. Header construction and the unavoidable
CI16 copy are the only per-frame work beyond the current path. Each arena frame
contains fixed IQ and maximum-metadata slots plus actual lengths, so the worker
passes the metadata slot directly to the provider rather than using the
current `send_data()` allocation.

## Lifecycle and failure semantics

IIOD uses an explicit fail-closed state machine:

| State | Meaning | Allowed next states |
|---|---|---|
| `OFF` | ordinary request; current code path | ordinary close |
| `RESERVED` | request admitted and arena prefaulted | `CAPTURING`, `FAILED` |
| `CAPTURING` | local DMA refills are copied; no transport writes | `SEALED`, `FAILED` |
| `SEALED` | complete immutable burst; physical IIO buffer is closed; ordinary reads replay it | `DRAINED`, `FAILED` |
| `DRAINED` | all frames delivered and arena released | close |
| `FAILED` | no IQ may be returned; resources and global reservation released | close |

The cache becomes visible only after every frame is present and verified.
It rejects a counter gap, regression, stream change, provider overflow, short raw
refill, metadata failure, mask/length mismatch, idle expiry, or cancel. A
burst failure returns one typed error and destroys every retained byte.
The state machine writes the arena only while capturing and reads it only after
sealing; it never wraps or overwrites an older frame.

Startup metadata discards are limited to eight frames. The requested byte
ceiling bounds successful capture work; Pluto Plus Utils installs a calculated
finite IIO timeout (up to 300 seconds) and cancellation destroys the buffer.
IIOD heartbeats the tandem lease on every physical refill. Client disconnect or
`iio_buffer_cancel()` wakes a blocked local dequeue, closes the physical buffer,
restores provider state, and discards the arena. The forced-disconnect hardware
gate exercised that path without restarting IIOD.

Before sealing, IIOD destroys the DMA buffer and runs the existing provider
close path, which releases tandem ownership, stops samplers, and restores the
timestamp-control register. That inherited close hook is best-effort; therefore
Pluto Plus Utils also restores and verifies the complete RX snapshot on every
terminal path. Making provider finalization return a checked status remains a
reasonable hardening item before persistent promotion, but it is not needed to
make the candidate's RAM-only recovery path safe.

Once sealed, a 30-second idle-drain deadline uses the existing IIOD worker
condition variable with a timed wait; expiry frees the arena if the client sends
no reads. Successful frame delivery advances the cursor only after the complete
metadata and IQ write returns. Transport error discards the remainder. Pluto
Plus Utils restores its prior timeout after the job and its stop path cancels
and closes the IIO buffer, so socket teardown cancels radio-side work. Sealed
downloads are deliberately not resumable in v1.

## Pluto Plus Utils behavior

The flag selects an internal path while preserving the existing artifact
and `SampleBlockV2` contracts:

- require a bounded capture, ABI 3, the burst capability, and one
  selected receiver;
- compute and report the exact requested bytes, admitted bytes, and whole-frame
  count;
- collect time anchors before burst-buffer open, then avoid control-plane reads
  while device capture is active;
- construct the extended request and continue using `MetadataBuffer` with
  ordinary one-frame refills;
- independently verify every metadata record, require zero
  `missing_samples_before`, and close on the first disagreement;
- report total wall time plus authoritative device sample span in the canonical
  ladder report; and
- cancel the underlying IIO buffer from the stop/shutdown path rather than
  waiting for the complete burst.

The application, API client, and stored IQ see the same channel ordering and
sample blocks as an ordinary metadata capture. The only intentional observable
difference is that the first refill waits for the bounded device capture and
later refills drain faster than real time.

## Operation sequence

The implemented operation does the following:

1. Attest the exact radio, firmware ABI, receiver geometry, and TX-safe state.
2. Acquire an exclusive bounded-capture lease and reject concurrent readers.
3. Snapshot the exact RX settings and IIO buffer state.
4. Compute the requested byte count with checked arithmetic.
5. Enforce single RX and a 200,000,000-byte ceiling (two seconds at 25 MS/s).
6. Reserve a fixed system-memory safety margin of at least 128 MiB.
7. Allocate, prefault, and retain a 95.4- or 190.9-MiB anonymous arena.
8. Keep the validated four-by-4-MiB CMA staging queue.
9. Capture exact local refills into the DDR arena without concurrent network
   transmission.
10. Retain ABI-3 metadata per refill, including first-sample sequence, stream
    generation, flags, receiver mask, payload size, and CRC.
11. Reject any counter gap, regression, overflow ambiguity, short refill,
    layout mismatch, or terminal-state failure. Do not silently rebase time.
12. Stop after the admitted whole-frame count is complete.
13. Destroy the physical buffer and close the metadata provider before sealing;
    the host verifies restored settings after drain.
14. Transfer the frozen burst using ordinary metadata refills and release the
    radio-side memory deterministically.
15. On every terminal job path, have Pluto Plus Utils exact-restore and verify
    the complete RX snapshot, then return the durable capture receipt.

Hashing and optional format conversion occur after capture, not in the
real-time ingestion loop. The first implementation retains raw CI16 and adds no
compression, resampling, or quantization.

## Concrete implementation seams

Keep the change narrow and preserve one owner for each resource:

- `iiod/buffer-metadata.h` gains a provider-neutral internal capture-plan
  result. Ordinary providers and the original request return `OFF`.
- `iiod/spf-buffer-metadata.c` validates and splits the extended request,
  passes the unchanged 104-byte prefix to the tandem decoder, and returns the
  exact bounded plan. It continues to own metadata production and restoration
  of timestamp/tandem state.
- `iiod/ops.c` owns the arena and all state transitions in the existing
  per-device R/W thread. Its burst branch performs admission, local refills,
  fixed-slot metadata construction, sealing, cached replay, timeout, cancel,
  and teardown. The ordinary branch remains unchanged.
- `iiod/iiod.c` advertises the three read-only burst capability attributes only
  in a firmware build that includes the complete implementation.
- `libiio/local.c`, the Linux IIO/DMA drivers, HDL, CMA reservation, and public
  libiio buffer API do not change in the first version.
- Pluto Plus Utils adds the flag to `begin_metadata_capture()` and the metadata
  ladder, performs capability and geometry admission around
  `IioMetadataCaptureSession`, and keeps using the
  current `MetadataBuffer`/`SampleBlockV2` path. It adds diagnostics and tests
  as normal package commands and modules, never as side scripts.

The worker must have an explicit cached-replay branch before the current local
refill and `send_data()` path. Once `SEALED`, `entry->buf` may be destroyed, so
no replay code may dereference it or call the closed provider. Cached IQ and
metadata lengths are authoritative only after the frame table is sealed.

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

## Qualification gates before persistent promotion

The candidate uses three test layers:

1. **libiio host tests:** preserve every legacy metadata test byte-for-byte;
   add table-driven extension decoding, required-bit/reserved-field rejection,
   checked geometry arithmetic, state transitions, and cleanup idempotence.
2. **IIOD fake-device integration:** exercise prompt open followed by a blocked
   first refill, proactive multi-frame capture, immutable replay, `-ENODATA`,
   startup discard, counter gap, short frame, timeout, disconnect, cancel, and
   allocation failure without depending on radio hardware.
3. **Pluto Plus Utils tests:** prove the new flag defaults false, capability
   mismatch fails without fallback, exact geometry is deterministic, host
   batching is one, cancellation calls cancel then close, metadata is
   revalidated, requested/admitted geometry closes exactly, and every terminal
   path restores settings.

The implemented decoder, buffer-layout, tandem-session, temporary-cache,
metadata-batch core, IIOD command-batch, Python binding, and complete Pluto Plus
Utils suites pass. The source-locked CI image and bounded hardware gates above
also pass. The client is default-off and remains inert on old firmware. A
longer soak and the remaining promotion-only instrumentation below are still
appropriate before persistent release; the current policy cannot authorize
QSPI.

B2 and B6 pass directly. The forced disconnect and immediate-reuse portions of
B3 pass. B1's dedicated p99 copy instrumentation, exhaustive B3/B4 fault
injection, and long-duration B7 remain promotion gates rather than blockers for
this recoverable RAM candidate.

### B1: local sink throughput

Using a non-advertised instrumentation build of the same IIOD worker path,
orchestrated and receipted by Pluto Plus Utils, prove RX0 and RX1 local capture
into one repeatedly reused scratch frame at 25 MS/s for at least two seconds.
Require p99 complete four-megabyte ingestion below 20 ms, providing at least a
two-times timing margin against the 40-ms refill cadence, and require zero
counter gaps or device overflows.

### B2: prefaulted DDR throughput

Repeat into a prefaulted 200-MB normal-RAM arena. Measure CPU, memory bandwidth,
CMA, scheduler latency, refill cadence, and continuity. The complete two-second
capture must finish without allocation during the hot path and with the
128-MiB system reserve intact.

### B3: failure atomicity

Inject client disconnect, timeout, cancellation, allocation refusal, metadata
   error, and insufficient-memory conditions. Every path must release the arena,
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

- whether downloading may resume after a host reconnect;
- whether provider close should return a checked restoration result rather than
  relying on host-side restore/readback verification;
- whether a later server-side per-write deadline is warranted in addition to
  the 30-second sealed-idle deadline and finite client timeout;
- whether explicit memory zeroing is warranted beyond anonymous-page release
  for the deployment trust model;
- whether a later FPGA-assisted DDR writer is warranted if the ARM copy path
  cannot sustain the B1/B2 margin.

## Implementation constraints retained

The implementation satisfies the following constraints:

- the work is scoped as a separate feature with its own source lock and release
  identity;
- Pluto Plus Utils owns the host command, validation, and receipts;
- no shell sidecar or unbounded rootfs file is proposed as the production
  mechanism; and
- copy-path and B2 evidence is collected through first-class Pluto Plus Utils
  ladder and data-plane status commands, and passes on the RAM-booted CI
  firmware.
