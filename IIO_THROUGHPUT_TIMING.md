# IIO throughput timing prototype

The candidate `v0.45-plutoplus-spf-iio-throughput-timing-v1-rc1` retains the
HOLD v2 refill-fence prototype and adds aggregate timing to iiOD. It is a
diagnostic RAM-boot candidate, not a persistent-flash release.

The IIO context advertises `iio,buffer-metadata-timing-log=1`. Closing the last
client for an opened device emits `SPF_IIOD_TIMING_V1` records to iiOD stderr
(the Pluto supervisor routes this to the kernel log). Each record includes
the device, metadata/burst/ring mode, IQ frame size, measured capture wall
time, stage count, total nanoseconds, and maximum nanoseconds.

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
stage completion. It logs only on final device-entry teardown. Timing-clock
failure drops the affected measurement without changing capture behavior.
The wire format, IIO API, sampler cadence, DMA queue sizes, and DDR admission
limits are unchanged.

Validation must compare ordinary, HOLD metadata, AUTO metadata, and 200 MB
DDR-ring captures with identical sample rate, frame size, kernel-buffer
count, host, and physical Ethernet endpoint. Repeating an ordinary and HOLD
run against the uninstrumented HOLD v2 candidate establishes whether timing
overhead is material. Stage timing can localize blocking but does not by
itself distinguish CPU execution from scheduling or network backpressure;
those require correlation with CPU and transport measurements.
