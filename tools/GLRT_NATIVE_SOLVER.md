# Native full-pilot radio solver

`glrt_native_solver.c` consumes CPU-endian GLS1 result words and solves one
bounded timing/CFO update without observed IQ, FFTs, allocation or I/O. It is
portable C99 with double precision and libm. The caller must first associate
epoch, batch, repeat, sequence, rounded start and carrier step using its retained
finite descriptor. Packet shape alone is not acquisition or association.

The three columns are the exact quantized B04 reference, negative derivative
per microsecond and frequency derivative per kHz at centered native sample
times. `generate_glrt_native_gram.py` pins the coefficient bank SHA-256 and
generates the constant 3x3 Hermitian Gram matrix. The reference/derivative
projections come directly from FPGA sums. The frequency projection is
`-j*pi*1000/60000000 * ((N-1)*reference_sum - 2*prefix_integral)`.
The centered integer quantity is calculated in signed 96-bit limbs before
conversion to double, including near cancellation. No ARM `__int128` is needed.

The solver profiles complex gain, projects it out of the two derivative
columns and solves a real 2x2 system. This follows the qualified local streaming
algorithm through a firmware-owned implementation; the tracker repositories
are not runtime dependencies. The C implementation has no connection to a
radio until a caller supplies already retained/associated moments.

Corrections are relative to the **actual rounded engine start** and reported
carrier step. Keep start as u64 plus a separate fractional correction; do not
convert the whole source index to double. CFO is relative to the input pilot
band and applies at pilot center under the local model. It does not isolate
satellite Doppler from oscillator/LNB drift.

Default local bounds remain 250 ns / 250 Hz, with minimum prediction coherence
0.05. Faulted or incomplete observations are retained with rejection flags and
never fitted using the full-pilot Gram matrix. Malformed integer encodings or
source-index wrap return an error. A nonzero rejection forbids feeding the
correction into tracking. A supported linearized fit still does not certify
pilot acquisition, calibrated physical timing, uncertainty or RF truth.

## Verification and radio benchmark

`tests/starlink_glrt/test_native_solver.py` passes 43 tests: an independent tall
real least-squares SVD matches the C corrections and both coherences; tests also
cover noise/tone/zero controls, local bounds, malformed packets, partial faults,
signed carrier steps, u64 coordinates and exact integer carry/cancellation.
The generated Gram matrix must match regeneration from the pinned bank.

Artifacts under `/srv/bulk/leo/glrt-deployment-20260909/native-solver-benchmark-v1`
retain the host/ARM executables, exact five saved test packets, dense-fit
expectations, source/binary hashes and PPU Ethernet operator receipts.
`operator-v2.json` records **100,000 calls averaging 2.62945197 us** on radio
`winbond-db620818a328172c` at `192.168.1.14`. All five ARM estimates match the host
within 1e-18 s / 1e-8 Hz and 1e-12 coherence, including the rejected out-of-bound
case. The first operator attempt failed because the minimal radio rootfs lacks
`base64`; that receipt is retained. The successful attempt used PPU's binary-safe
SSH stream and verified both input and executable hashes on the radio.

This benchmark used no RF collection, changed no firmware, confirmed the pinned
deployed manual profile and idle/TX-off state before and after, and removed its
temporary radio files. It measures only the solver, **excluding sysfs access,
record retention, scheduling, tracking and Linux scheduling jitter**. Those
costs still require an end-to-end 750 Hz test. This is not a precision evaluation
of newly received signals.

Example host build:

```
cc -std=c99 -O2 -Wall -Wextra -Werror tools/glrt_native_solver.c \
  tools/glrt_native_solver_bench.c -lm -o /tmp/glrt-native-solver-bench
```

The saved-packet benchmark accepts `PACKETS_TEXT ITERATIONS`, at most 64 packets
and one million calls, with a ten-second computation ceiling checked every
1,024 calls. It emits per-packet estimates and aggregate elapsed time. It never
opens a device or changes any firmware/configuration.

## Radio result association port

`glrt_native_schedule.c/.h` provides the C controller's descriptor encoder,
exact fractional/modulo prediction, length-bounded GLS1 text-envelope parsing,
snapshot conservation and associated solve. It has no radio or storage access
and adds no tracker-repository dependency. `glrt_native_associated_solve`
requires the caller's retained descriptor and expected admitted sequence; it
checks epoch, tag, repeat, rounded source start, phase seed/step and full-pilot
expiry before entering the solver. A malformed or mismatched result returns
an error with a rejection flag; an associated partial/faulted result remains
drainable and cannot produce a supported correction.

The raw envelope parser does not by itself validate the moment payload: retain
the raw text, parse, associate/solve, then acknowledge. Never use an envelope
parse as permission to POP. Both the solver return code and rejection bits
must pass before feedback. An explicitly drained snapshot may have source
faults: draining retained evidence is distinct from permitting new predictions.
The controller must separately require a healthy current source epoch.

`native-radio-association-v1.xml` records **102 passing tests**, comprising the
59 association/transport tests and 43 solver tests. The prediction tests compare
2,500 cases against Python's exact `Fraction` oracle, including u64 coordinates
and signed modulo carrier ramps. Snapshot tests check conservation with wide
counter sums; envelope failures leave no partial output. The port also compiles
with the target Cortex-A9 hard-float compiler and `-Wall -Wextra -Werror`.
This is a tested port for the future radio-local runtime, not a deployed
feedback loop or an end-to-end I/O benchmark.

## Finite causal trend core

`glrt_native_trend.c/.h` is the allocation-free development predictor around
the associated solver. Its input frame ordinal must come from the retained
descriptor history across batches; the GLS1 packet's repeat field resets at
each batch and cannot serve as that ordinal. The runtime must retain that
mapping with each submission. Source epoch, sequence and payload association
are checked by the port before an observation enters this core.

The core fits timing offsets and received CFO against frame ordinal using only
supported observations in the preceding 96 frame positions (about 128 ms).
Eight supported points are required. Integer source coordinates are subtracted
before conversion to double, preserving fractional timing at large indexes.
The two fitted slopes set the repeat period and carrier-step delta. CFO rate
uses the fitted period before scheduling quantization. The output descriptor
uses Q16 timing/period, modulo-48 carrier phase steps, exact full-pilot expiry,
and at most 32 future frames beyond the last supported observation (about
42.7 ms). The finite horizon includes the batch's last repeat. Predictions
cannot start at or before the last observed frame, even if that observation
was rejected. Producing a descriptor has no state or submission side effect.

Rejected local fits do not enter the regression. Faulted/incomplete source
support, epoch changes, malformed values and out-of-order frames fence the
trend until explicit reset and fresh acquisition. Old observations age out
after 96 frame positions, including through losses. A source epoch is bounded
to 1,350,000 frame positions (30 minutes at the nominal cadence). These are
development controller limits, not new scientific acceptance criteria.

`native-radio-trend-v3.xml` passes **40 tests** against independent least squares
and analytic timing/carrier ramps, including both rate signs, both timing-drift
signs, positive/negative/zero-centered CFO, large indexes, rejected controls,
warmup, horizon/expiry, loss ageing, immutable prior descriptors and source
fences. An earlier test exposed that the reported CFO rate used the quantized
period; the implementation now reports the unquantized fitted slope. The
previous failed receipt is retained. The core compiles with the Cortex-A9
hard-float compiler and all warnings treated as errors.

This tests prediction from supplied estimates. It does **not** establish an
acquired, closed-loop precision result. Integration still needs workstation
bootstrap, a retained global-frame mapping, radio-local sysfs reads/writes,
deadlines checked against the live native index, durable head retention before
POP, finite active/pending schedule ownership, and measured I/O/jitter. The
existing native-IQ and real 25 MS/s qualification gates remain required; these
unit tests do not replace them.
