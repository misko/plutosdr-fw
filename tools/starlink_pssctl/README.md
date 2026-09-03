# Stage-15 PSS tracker controller — experimental firmware only

`starlink_pssctl` is the fail-closed userspace boundary for the RX-only
Stage-15 FPGA tracker. It accepts only hardware ID `PSST`, ABI 1.2, 15 MS/s,
66 taps, a 130-sample capture, 61 lags (`-30..+30`), and capability word
`0x3d`. It maps only the fixed tracker aperture at `0x79030000`.

Every invocation also requires `--expect-serial`. The value must exactly match
the radio's hardware-derived `/etc/serial` before `/dev/mem` is opened. This is
an extra local guard; PPU still owns host-side USB/interface/route locks and is
the authority for selecting and recovering the radio.

Build and run the native mock/fixture test plus the static ARM target:

```sh
make check
```

The test verifies strict ABI rejection, fixture I/Q conversion, coefficient
loading/commit, exact 130-sample injection loading and I/Q conversion, atomic
telemetry, future scheduling, every success-counter delta, retained packet
decoding, fail-with-result-retained behavior, seven-entry batch prequeue/refill,
ordered batch delivery, and accepted-sample clock-slope arithmetic. It does not
access a radio.

The source coefficient memory format is one eight-digit hex `IIIIQQQQ` word
per line. Exactly 66 lines are required. The controller deliberately converts
that fixture convention to the AXI register convention `{Q[15:0], I[15:0]}`.
Injection fixtures use the same source convention and require exactly 130
lines.

Typical commands on the already PPU-locked, RAM-booted radio are:

```sh
SERIAL=104000bac4950008230026001b440a003a
./starlink_pssctl --expect-serial "$SERIAL" info
./starlink_pssctl --expect-serial "$SERIAL" counters
./starlink_pssctl --expect-serial "$SERIAL" load \
  --coeff upper_minus100k_coefficients_q15.mem --generation 0x07120001
./starlink_pssctl --expect-serial "$SERIAL" clock-slope \
  --duration-ms 1000 --tolerance-ppm 5000
./starlink_pssctl --expect-serial "$SERIAL" track --request 1
./starlink_pssctl --expect-serial "$SERIAL" track-batch \
  --request-base 0x75000000 --count 45000 --period 20000 \
  --lead 1000000 --queue-target 7 --timeout-ms 5000
./starlink_pssctl --expect-serial "$SERIAL" inject-load \
  --samples real_071200_window0_samples_ci16.mem --generation 0x1a120001
./starlink_pssctl --expect-serial "$SERIAL" inject-track --request 2
```

`track` defaults to one million samples of lead (about 66.7 ms at 15 MS/s) and
requires at least 65,536 samples even with `--center` or `--lead`. It snapshots
the sample-clock counters atomically before and after the job, requires exactly
one admitted/completed/published/processed result and zero increments in every
error counter, validates all packet identity/geometry fields, and only then
releases the immutable result bank. On a packet or counter-gate failure it
leaves the result retained for diagnosis and exits nonzero.

`clock-slope` brackets two accepted-sample index snapshots with
`CLOCK_MONOTONIC` reads, uses each host-read midpoint, and compares the measured
slope with the ABI-fixed 15 MHz clock. The default observation is one second
with a 5000 ppm bound. Its JSON records both MMIO read spans so host scheduling
uncertainty remains visible.

`track-batch` uses the existing ABI 1.2 command FIFO; it does not require an RTL
change. The frozen Stage-15 continuity geometry is one center every 20,000
accepted samples (750 Hz), one million samples of initial lead, and all seven
usable FIFO entries. It emits one validated `batch_result` JSON object per line
and a final `batch_summary`. The controller refills after every completion,
preserves result order, records conservative post-submit lead, requires at least
65,536 samples of lead for every accepted command, and verifies aggregate
success-counter deltas plus zero change in every error counter. Saturated counters
or insufficient counter headroom are rejected before the first submission. A
partial failure leaves prior lines as valid NDJSON and exits nonzero without a
success summary.

`inject-load` clears, writes, and commits an immutable 130-sample fixture.
`inject-track` arms that fixture at a future absolute accepted-sample index,
schedules `TRACK_ONE` at `start+32`, and succeeds only if both the ordinary
packet/counter gates and the injection completion/generation gates pass. The
FPGA substitutes I/Q before the shared tracker/RX-DMA fan-out; strobe, enable,
index, and timestamp remain source-derived. A late start, incomplete fixture,
overlapping command, or accepted-index discontinuity is sticky and fail-closed.
This is deterministic hardware-path evidence, not live Starlink evidence.

## Continuous-acquisition library checkpoint

`starlink_pss_acquisition.c` is the source-only ARM policy layer for the
separate `PSMA` phase-map bridge. It accepts the fixed 15 MS/s geometry:
20,000 one-sample phase bins, 64 frames per map, 16-bit map words, and two
immutable banks. The parser accepts exactly ABI 1.0/capability `0x1f` and ABI
1.1/capability `0x3f`; unknown versions or mismatched capability words fail
closed. It is compiled as a strict ARM EABI object by `make check`; it is not
yet linked into `starlink_pssctl`, installed in the root filesystem, or
assigned an MMIO aperture. Those steps wait for RX-shell integration and a
complete linked-system route.

The copy sequence takes one atomic hardware snapshot, reads exactly 20,000
zero-extended words, brackets the copy with a second atomic snapshot, and
releases the selected bank only after its generation, start index, command
status, and all acquisition/bridge fault epochs remain coherent. ABI 1.1 adds
one atomic snapshot of ingress drops/FIFO occupancy, scheduler gaps/index
errors/overflows, detector faults, phase discontinuities, zero denominators,
candidate FIFO occupancy, and sticky cause flags. Continuity checks reject a
copy when any data-integrity fault epoch changes or saturates; changing queue
occupancy and zero-denominator telemetry remain observable but do not falsely
invalidate an otherwise coherent copy. ABI 1.0 snapshots synthesize zero for
the absent health fields and never access the new register range. Failed copies
retain FPGA ownership. Each successful copy carries its before/after health
epochs; `pss_map_copies_contiguous()` accepts only adjacent generations and
1,280,000-sample start-index steps with unchanged, nonsaturated fault counters.

Candidate extraction keeps three consecutive maps and evaluates at most seven
strictly increasing shift-and-sum hypotheses. The production bank is
`[-12, -8, -4, 0, 4, 8, 12]` bins per 64-frame tile: approximately
`[-9.375, -6.25, -3.125, 0, 3.125, 6.25, 9.375]` ppm around the nominal
20,000-sample period. It preserves the Python oracle's tie order (smallest
drift, then smallest phase), exact odd/even median and MAD construction,
peak-to-median ratio, robust z score, and estimated frame period.

The fixed working set is about 320 kB: 120 kB for three maps, 160 kB for two
20,000-word `uint32_t` scratch arrays, and 40 kB for the incoming immutable
copy buffer. The state controller is explicitly
`ACQUIRE -> CONFIRM -> LOCK -> TRACK -> HOLDOVER -> ACQUIRE`. A lock requires
multiple threshold-passing, phase/cadence-consistent observations. Metadata or
hardware-health discontinuity resets acquisition without consuming the current
candidate; bounded misses enter holdover and then return to acquisition.

The native C test covers both supported ABI contracts, the ABI 1.1 health-word
unpacking, proof that ABI 1.0 never reads ABI 1.1 registers, the complete
20,000-word transfer, no-release failure paths, ingress/base fault epochs and
map continuity, mutable non-fault telemetry, fixed-memory drift extraction,
tie and finite/zero-MAD cases, unsafe-bound rejection, and the complete state
path.
`tests/test_starlink_pss_acquisition_c.py` additionally compares C against the
frozen Python acquisition oracle across randomized odd/even map sizes and a
zero-MAD tie. This checkpoint is candidate-selection and policy logic, not a
shell connection, autonomous scheduler, on-radio result, live PSS detection,
or demonstrated frame lock.

This controller and FPGA belong only on
`codex/starlink-rx-only-do-not-merge`. They must not be merged into HDL or
firmware main. Generic PPU radio-mode support remains separate and mergeable to
PPU main.
