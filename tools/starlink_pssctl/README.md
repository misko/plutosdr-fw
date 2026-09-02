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

This controller and FPGA belong only on
`codex/starlink-rx-only-do-not-merge`. They must not be merged into HDL or
firmware main. Generic PPU radio-mode support remains separate and mergeable to
PPU main.
