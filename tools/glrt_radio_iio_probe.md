# Bounded radio-local IQ ingestion

`glrt_radio_iio_probe.c` measures the capture-owner boundary needed by automatic
tracking. It opens a local libiio context on the radio, owns one finite IQ DMA
prefix, copies it into the recent-IQ ring, and retains IQ, events and source
snapshots for independent review. It does not submit tracking jobs, change RF
configuration, enable TX, or install firmware.

The caller holds the exact production radio lease and device lock, verifies the
resident image/boot path through PPU, and runs the executable over Ethernet SSH:

```text
probe SERIAL FIRMWARE VISIT EVEN_CHUNK BLOCKS /NEW_OUTPUT_DIR
```

The request must fit whole DMA buffers, at most 250,000 complex samples per
buffer and five seconds total. The executable requires the direct 2.5-MS/s
GLA1 acquisition image, the exact supplied serial/firmware, a new visit, the
expected CI16/event scan layouts and TX LO powered down. It checks RF state
before and after reception without writing PHY attributes. Existing output
directories are rejected. New filenames are created exclusively.

One nonblocking local event buffer is drained by the IQ owner between refills
and after the IQ buffer is destroyed. This avoids a second IQ consumer and
retains complete finite event evidence. Four IQ kernel buffers and 1,024 event
records are requested, matching the existing collector. No event thread is
needed for this bounded probe. A future automatic owner must qualify concurrent
resolution/export under load; this probe alone does not do that work.

## Source time and retained data

`glrt_capture_source` decodes the existing public GLA1 snapshot into a strict C
value. It binds each delivered block to the driver's frozen pre-ARM baseline
and its new post-refill snapshot. Visit, source geometry, event-loss counters,
prefix endpoints, delivery counts, monotonically advancing snapshot generation
and source time must agree. Generation wrap is allowed; stale/reversed snapshots,
counter regressions and discontinuities fence the cursor without advancing its
retained count. Snapshot decoding does not itself establish radio identity.

The exclusive current receiver coordinate is `latest_ingress_index + 1`.
It is distinct from the end of the block just received. Each block enters the
one-second, 10-MB CI16 ring and is copied back and compared byte-for-byte before
being saved. Ring and evidence-store costs are included in the measurements.
`glrt_tracking_iq_owner` now serializes publication and copying through a
mutex. Each copy returns the matching retained interval, receiver source
coordinate, observation timestamp and generation. Workers perform numerical
work after the copy returns. Source/time regression fences history; normal
closure keeps past evidence readable but forbids publication. This prepares
concurrent bootstrap access; the ingestion probe still does not resolve live
candidates or submit tracking jobs.

An optional `GLRT_PROBE_BOOTSTRAP` build now connects a real background session
to this owner. The default invocation above retains its ingestion-only behavior.
The additional invocation is:

```text
probe SERIAL FIRMWARE VISIT EVEN_CHUNK BLOCKS /NEW_OUTPUT_DIR --bootstrap /ATTESTED_REFERENCES.bin
```

The reference file is exactly 105,600 bytes: four phase banks, each with 3,300
rows of four little-endian signed 16-bit reference/derivative coefficients.
The operator pins its full hash and the executable/library identities before
execution. The executable rejects missing, nonregular, symlinked or incorrectly
sized reference files before opening a radio context. This profile remains
direct 2.5 MS/s, upper edge only; it does not generalize the seed convention to
a decimated higher-rate source.

One waiting pthread accepts at most one pending event while idle. Every event
gets a retained disposition: ignored, queued, busy or stopped. The original
raw stream is retained before dispatch. FFT and bootstrap computation use the
protected IQ copy outside the capture thread. The session uses the existing
one-second seed-age limit, a two-second source deadline from event origin and
a three-second wall budget. These are explicit rejection bounds, not measured
latency promises. New publication wakes the worker; bounded timed waits also
permit cancellation if publication stops.

Three extra files retain the diagnostic:

- `bootstrap_events.csv`: original event sequence, dispatch time and disposition.
- `bootstrap.jsonl`: explicit versioned fields for seed selection, all resolver
  hypotheses, past-pilot moments/estimates, history/proposals and terminal status.
- `bootstrap.iq.ci16`: the exact seed and past-pilot copies, indexed by each
  JSON record's complex-sample offset/count.

Worker evidence is limited to 8 MiB including the event-disposition log. A
failed write, invalid event or worker-port error fails the probe. Unsupported
history, expired work or normal stop cancellation are retained diagnostic
outcomes. A queued event canceled before computation gets its terminal record.
Only the worker writes its IQ/JSON journal; only the capture thread writes
event dispositions. The session mutex never encloses FFT or pilot arithmetic.

STOP and SIGINT/SIGTERM request worker cancellation before IQ teardown. Final
event draining records stopped dispositions, then joins the worker before
destroying owner storage, references or the FFT plan. A HANDOFF record is a
proposal: a later terminal failure can invalidate it. This diagnostic build
performs **zero hardware tracking submissions**, including after READY. Actual
controller/driver admission remains a separate integration gate.

The optional build additionally links `glrt_tracking_session.c`, the seed,
worker, bootstrap/solver/schedule dependencies, and double-precision FFTW.
Its FFTW plan allows unaligned worker storage explicitly. The `fftw` test
marker requires native FFTW headers/library; `GLRT_FFTW_PREFIX` may select a
local installation. Missing dependencies fail explicitly. The declared IIO
fixture can supply continuous synthetic pilot samples and a modeled accepted
coarse event while the actual pthread, FFTW and bootstrap run. That test is
not RF or FPGA detector qualification. Real-radio verification is separate.

`blocks.csv` records absolute source coordinates and monotonic timestamps
around refill, snapshot read, ring copying, evidence storage and event draining.
`block_snapshots.txt` retains the underlying wire evidence. Receiver backlog
at the snapshot is `(source_now - first - chunk_samples) / 2500000` seconds.
Snapshot-read and later processing latency remain separate columns; that
backlog is not a promise about the final tracking admission time.

The driver baseline/final IQ, closure and local-search snapshots and all event
bytes are retained even after a capture failure when those attributes remain
available. Destroying the owned IQ buffer precedes final event drain. The
program reports `captured` only after its own checks; independent
`starlink_glrt_local_abi.attest_capture` and host IQ analysis are still required.
No supported signal in a short probe is inconclusive for detector sensitivity.

## Build and qualification

Link `glrt_radio_iio_probe.c`, `glrt_capture_source.c`,
`glrt_tracking_recent_iq.c` and `glrt_tracking_iq_owner.c` with libiio 0.x and
`-pthread`. The ARM build uses the firmware's
Buildroot toolchain and its real libiio header/library. Local libiio includes
its final NUL in attribute byte counts; the owner accepts a final terminator
and rejects embedded NULs. The parser's input length excludes the terminator.

The `--base64` mode opens no IIO context. It converts at most 60 MB from stdin
to explicitly delimited base64 for PPU's text SSH port, so evidence can be
exported after RX without depending on additional BusyBox applets. The operator
validates archive membership, source/binary identities and exported file hashes.

Owned tests are `test_capture_source.py` and `test_radio_iio_probe.py`.
The latter uses a finite IIO fixture and independent Python closure/IQ checks;
it is software qualification, not a silently substituted hardware test.
Real-radio receipts and measurements must be reported separately. Tests cover
RF/identity/layout refusal, partial or failed refills, stale/source-loss evidence,
event reordering, buffer teardown, RF changes and byte-exact export boundaries.
