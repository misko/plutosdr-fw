# IIO throughput CPU-isolation prototypes

The candidate `v0.45-plutoplus-spf-iio-throughput-rw-affinity-v2-rc1` retains
the HOLD v2 refill-fence prototype and aggregate timing from timing v1. It pins
only iiOD's per-device read/write workers to CPU1, leaving client, metadata,
and DDR-ring producer threads schedulable on both CPUs. Ethernet, DMA, and USB
hardware IRQs remain on CPU0. The affinity is an opt-in iiOD startup option
and is enabled only by this diagnostic firmware. This is a RAM-boot candidate,
not a persistent-flash release.

The IIO context advertises `iio,iiod-rw-cpu-affinity=1`. It must not advertise
the v1 whole-process attribute `iio,iiod-cpu-affinity`; the two iiOD modes are
mutually exclusive and both are disabled by default upstream. The worker is
created with its CPU mask already applied, so a capture cannot begin in an
unattested scheduling state.

The thread pool records the daemon's original allowed-CPU mask before any
device worker exists. An unqualified nested worker receives that recorded mask
explicitly instead of inheriting its creator's specialized mask. This matters
for the DDR-ring producer, which is created by the CPU1 R/W worker but must
remain schedulable independently for capture and transport to overlap.

The IIO context advertises `iio,buffer-metadata-timing-log=1`. Every 100
transported frames, and again when the last client closes an opened device,
iiOD emits `SPF_IIOD_TIMING_V1` records to stderr (the Pluto supervisor routes
this to the kernel log). Each record includes whether it is an in-flight
snapshot, the device, metadata/burst/ring mode, IQ frame size, successfully
transported IQ bytes and frames, measured capture wall time, stage count, total
nanoseconds, and maximum nanoseconds.

| Stage | What is timed |
| --- | --- |
| `sampler_admit` | Metadata provider's pre-refill admission fence |
| `dma_refill` | `iio_buffer_refill`, including any wait for a completed DMA buffer |
| `sampler_finish` | Metadata provider's post-refill observation fence |
| `metadata_build` | Capture-associated metadata collection and serialization |
| `ddr_copy` | IQ copy from the DMA buffer into burst/ring DDR storage |
| `transport_frame` | Complete frame-send call, including metadata construction on the ordinary metadata path |
| `transport_iq` | IQ transport write, including socket backpressure and scheduling |
| `ring_producer_wait` | Ring slot reservation and any wait for a free slot |
| `ring_consumer_wait` | Wait for the ring to make a frame available |

These are elapsed wall-clock measurements, not CPU-time measurements. The
transport IQ stage is nested inside transport frame, metadata construction
is nested inside the ordinary metadata frame send, and ring producer and
consumer work overlap. Do not sum all stages and call the result capture
time. Compare per-stage averages and maxima against the separately reported
wall time and host-side throughput evidence.

The implementation uses a monotonic clock and one short statistics lock per
stage completion. It advances the in-flight snapshot counter from successfully
transported IQ bytes rather than transport-call count, emitting every 100 full
frames and again on device-entry teardown. Timing-clock failure drops the
affected measurement without changing capture behavior.
In v2, the wire format, IIO API, sampler cadence, DMA queue sizes, and DDR
admission limits are unchanged.

Validation must compare ordinary, HOLD metadata, AUTO metadata, and 200 MB
DDR-ring captures with identical sample rate, frame size, kernel-buffer
count, host, and physical Ethernet endpoint. Repeating an ordinary and HOLD
run against the uninstrumented HOLD v2 candidate establishes whether timing
overhead is material. Stage timing can localize blocking but does not by
itself distinguish CPU execution from scheduling or network backpressure;
those require correlation with CPU and transport measurements.

Affinity v1 pinned every iiOD thread to CPU1. It improved ordinary raw 20 MS/s
delivery from about 61 MB/s to 73.15 MB/s, confirming CPU/IRQ contention, but
starved the concurrent DDR-ring producer and caused an immediate counter gap.
That candidate is rejected. V2 is acceptable only if ordinary throughput keeps
the gain, a 200 MB ring completes without continuity loss, and a following
ordinary capture returns to baseline without rebooting.

## V2 hardware result and v3 sampler prototype

RAM-only testing on the physical `192.168.1.17` path showed that v2 fixes the
v1 cleanup failure but is not a complete throughput remedy. Two ordinary raw
20 MS/s runs delivered 72.63 and 72.68 MB/s, and PyADI delivered 61.38 MB/s.
Two 200 MB ring runs completed all 100 frames with no ring error and the exact
197,132,288-byte admitted prefix contiguous; an ordinary run immediately after
each ring returned to 72.6 MB/s. HOLD metadata reached 47.75 MB/s and the ring
settled near 42 MB/s, however, so v2 remains diagnostic and non-promotable.

Live per-thread evidence explains the remaining metadata gap. The gain sampler
is deliberately pinned to CPU1 and its fixed 100 us counter poll issues up to
10,000 register reads and timer wakeups per second. During a ring capture the
sampler and CPU1 R/W/transport worker accumulated roughly 2.44 and 2.57 CPU
seconds concurrently on that one core, while the independently schedulable
ring producer accumulated 3.62 CPU seconds. Selective affinity therefore
removed Ethernet-IRQ contention but exposed sampler/transport contention.

The v3 candidate preserves the v2 transport affinity and every wire, refill-
fence, ring, and admission contract. It replaces the fixed sampler sleep with
a delay derived from the live AD936x sampling frequency and counter distance
to the next observation. The sampler sleeps for half the estimated remaining
time, clamped to 100 us–1 ms. High-rate AUTO retains its short observation
cadence; sparse HOLD capture reduces redundant polling by up to 10x; a forced
refill observation can never wait more than 1 ms for the polling sleep. V3 is
RAM-only until identical ordinary, HOLD, AUTO, 200 MB ring, PyADI, and immediate
recovery tests prove both metadata semantics and throughput on hardware.

## V3 hardware result and v4 refill-fenced prototype

RAM-only v3 testing on the same AD9363A radio and physical `192.168.1.17`
path disproved adaptive counter polling as a sufficient remedy. Ordinary raw
IIO still delivered 71.71 MB/s, but HOLD without the DDR ring delivered 44.27
MB/s, AUTO delivered 37.79 MB/s, and an unmonitored 200 MB ring delivered
42.11 MB/s. Every ring run still completed 100 frames, retained the exact
197,132,288-byte contiguous prefix, terminated `target_complete` with error
zero, restored settings, and permitted immediate ordinary capture. V3 is
therefore safe but not throughput-promotable.

A low-intrusion four-second CPU sample during a ring run found 117 sampler
jiffies, 108 pinned R/W-worker jiffies, and 225 ring-producer jiffies. Those
are about 27%, 25%, and 52% of one CPU respectively. Timing over a 400 MiB
ring capture attributed about 4.24 seconds to DMA-buffer-to-DDR copies and
6.48 seconds to IQ transport; those stages overlap and must not be summed.
The adaptive sleep removed redundant counter wakeups, but each scheduled
observation still performs real SPI-backed AD936x gain and RSSI reads. HOLD
requests four observations per frame and AUTO requests a 32,768-sample
cadence, so those mandatory reads dominate the sampler cost.

The v4 candidate changes only the requested observation cadence. Every refill
after the first already has a fail-closed fence that starts one real gain/RSSI
observation before DMA refill and completes its synchronized counter interval
after refill; the bounded startup-discard contract covers the first frame.
HOLD cannot transition, while AUTO already carries authoritative FPGA gain
events with exact sample sequences for every intra-frame transition. V4 uses
one refill-fenced observation per frame for both modes and keeps the event
stream unchanged. It does not synthesize observations, change the wire ABI,
relax overflow/counter validation, or authorize persistence. Hardware
qualification must show lower sampler CPU while preserving AUTO events,
metadata closure, ring status, recovery, and ordinary/PyADI compatibility.

## V4 hardware result and v5 interruptible-wait prototype

RAM-only v4 testing on the spare radio at physical `192.168.1.17` proved the
refill fence is safe and useful, but not sufficient for promotion. A 100-frame
20 MS/s HOLD capture improved from 44.27 MB/s on v3 to 55.58 MB/s on v4, and
AUTO delivered 55.68 MB/s with valid FPGA events and no event or observation
overflow. Ordinary raw IIO remained about 72 MB/s and PyADI delivered 61.01
MB/s. The directly comparable 100-frame, 200 MB DDR-ring capture improved only
from 42.11 to 43.90 MB/s. Every ring run retained the exact 197,132,288-byte
prefix, completed its requested frame count with error zero, restored settings,
and allowed immediate ordinary capture.

The sampler still consumed about 30% of one core during a monitored 200-frame
ring run. V4 records far fewer observations, but the v3 cadence helper still
caps every predicted wait at one millisecond. It therefore reads the
synchronized FPGA counter roughly one thousand times per second even when a
20 MS/s refill observation is needed only about every 52 ms.

V5 replaces only that polling sleep. It waits on the existing sampler condition
variable for half the estimated counter interval, capped at 50 ms. Refill-fence
and stop notifications interrupt the wait, and the predicate is checked while
holding the same mutex as the broadcaster, so notifications cannot be lost.
Unrelated condition broadcasts resume the original absolute deadline instead
of causing an extra counter read. The refill fence, synchronized-counter
records, FPGA AUTO events, DDR behavior, fail-closed policy, and wire ABI are
unchanged. V5 remains RAM-only until hardware proves lower sampler CPU without
regressing throughput, metadata closure, or recovery.

## V5 hardware regression and v6 queue-coverage prototype

V5 improved the 20 MS/s HOLD and AUTO paths by about 7% and the 200 MB DDR
ring by about 5%, but two 200-frame ring captures failed after 66 and 176
frames with `-ENODATA`. The ring reported `dma_error`; radio logs prove the
DMA refill itself succeeded and the metadata provider rejected a frame with no
overlapping gain observation. For the first failure, the frame ended 1,649,865
samples (82.49 ms at 20 MS/s) before the earliest retained observation. That
run's one 49.57 ms ring-producer wait plus normal 32.54 ms DDR-copy work totals
82.10 ms, matching the uncovered interval.

The existing refill fence resets sampler credit to two frames. That is too
short when four already-queued kernel DMA blocks can continue capturing while
the ring producer copies or waits for a slot. V6 computes one fixed coverage
window from the actual kernel queue depth: `samples_per_frame *
(kernel_buffers + 1)`. Initial arm and every later refill reset to that same
bounded window. With four kernel buffers, the forced fence consumes one frame
of credit and four frames remain to cover all in-flight DMA work. Credit never
accumulates across refills, so an idle or fast producer cannot create unbounded
sampling history. A pure coverage-plan helper and boundary tests bind the
queue-depth arithmetic; the v5 interruptible wait, metadata ABI, DDR sizes,
and fail-closed validation remain unchanged.
