# IIO throughput R/W-worker affinity prototype

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
The wire format, IIO API, sampler cadence, DMA queue sizes, and DDR admission
limits are unchanged.

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
