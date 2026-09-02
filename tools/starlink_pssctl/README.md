# Stage-15 PSS tracker controller — experimental firmware only

`starlink_pssctl` is the fail-closed userspace boundary for the RX-only
Stage-15 FPGA tracker. It accepts only hardware ID `PSST`, ABI 1.1, 15 MS/s,
66 taps, a 130-sample capture, 61 lags (`-30..+30`), and capability word
`0x1d`. It maps only the fixed tracker aperture at `0x79030000`.

Every invocation also requires `--expect-serial`. The value must exactly match
the radio's hardware-derived `/etc/serial` before `/dev/mem` is opened. This is
an extra local guard; PPU still owns host-side USB/interface/route locks and is
the authority for selecting and recovering the radio.

Build and run the native mock/fixture test plus the static ARM target:

```sh
make check
```

The test verifies strict ABI rejection, fixture I/Q conversion, coefficient
loading/commit, atomic telemetry, future scheduling, every success-counter
delta, retained packet decoding, and fail-with-result-retained behavior. It
does not access a radio.

The source coefficient memory format is one eight-digit hex `IIIIQQQQ` word
per line. Exactly 66 lines are required. The controller deliberately converts
that fixture convention to the AXI register convention `{Q[15:0], I[15:0]}`.

Typical commands on the already PPU-locked, RAM-booted radio are:

```sh
SERIAL=104000bac4950008230026001b440a003a
./starlink_pssctl --expect-serial "$SERIAL" info
./starlink_pssctl --expect-serial "$SERIAL" counters
./starlink_pssctl --expect-serial "$SERIAL" load \
  --coeff upper_minus100k_coefficients_q15.mem --generation 0x07120001
./starlink_pssctl --expect-serial "$SERIAL" track --request 1
```

`track` defaults to one million samples of lead (about 66.7 ms at 15 MS/s) and
requires at least 65,536 samples even with `--center` or `--lead`. It snapshots
the sample-clock counters atomically before and after the job, requires exactly
one admitted/completed/published/processed result and zero increments in every
error counter, validates all packet identity/geometry fields, and only then
releases the immutable result bank. On a packet or counter-gate failure it
leaves the result retained for diagnosis and exits nonzero.

This controller and FPGA belong only on
`codex/starlink-rx-only-do-not-merge`. They must not be merged into HDL or
firmware main. Generic PPU radio-mode support remains separate and mergeable to
PPU main.
