# Explicit 4096-block bank-owned capacity probe

This additive runner extension supports only 64 or 4096 capacity blocks. Four
arguments retain the original 64-block default. A fifth argument is allowed only
in capacity mode and must be exactly `64` or `4096`. Numeric mode and its original
fixture are unchanged. The legacy 64-block exact terminal marker is retained;
4096 has its own exact terminal, expected counts, progress inventory and scaled
watchdog. No detector RTL, arithmetic, source cadence, sink stall profile or clock
constraint changes accompany this extension.

For 4096 blocks the expected inventory is 1,830,977 contiguous canonical source
samples, 2,097,152 forward/product/inverse words each, and 1,830,912 ordered scores.
Every frame retains its independent actual-clock ordinal, TLAST, block identity,
forward exponent carry and inverse exponent consistency checks. Scheduler queue,
ring retention, energy lookup age, score age and candidate FIFO high-water marks
remain measured with the original bounds. Capacity data are deterministic order/
liveness vectors, not a numerical score reference or RF-accuracy measurement.

The requested actual-core soak is 175 MHz FFT / 100 MHz source and scorer, direct
canonical15 input, source burst pauses 12/40 slow clocks with accumulated arrivals,
and score READY blocked 3/97 slow clocks. A passing result represents about
122 ms of input, not the full 300-second objective. Source15/30/60 adapters, native
fine, 2.5 MS/s pilot IIO, RF, full receiver fit/timing/CDC remain outside this probe.
The earlier −2.557 ns standalone route failure is not corrected by longer RTL
simulation.

Launch with Vivado 2022.2 and a new output directory:

```text
simulate_iq_to_score_bank_owned.tcl NEW_OUTPUT capacity bursty-stalled 175 4096
```

The runner freezes sources and generated core/bench hashes before launch and
requires all 4096 progress receipts, exact terminal and frame inventories, and
absence of failure diagnostics. The collector separately rejects missing or
duplicated/out-of-order progress, mismatched scope/counts/metadata, faults, missing
sources and source changes. To collect a completed run:

```text
python -m tests.starlink_oracle.iq_bank_owned_evidence SOAK_DIRECTORY --single-capacity --blocks 4096 --fast-mhz 175 --profile bursty-stalled --output REPORT.json
```

The unchanged six v3 numeric/64-block reports regenerate byte-identically under
the extended collector. Existing 43 runner policy tests retain every negative
case; only their extracted postprocessor fixture now initializes the runner's
default `capacity_blocks=64`. New tests execute Tcl admission/generic/4096 progress
verification and reject truncated, duplicated and incorrectly labeled collector
receipts. Synthetic policy/collector fixtures are not actual soak evidence.

The parameterized runner also completed a fresh actual-core 64-block 175 MHz
bursty/stalled regression (`bank-iq-capacity-175-bursty-stalled-v4`), exiting zero
at 2026-09-10 01:35:18 UTC. It produced 28,608 ordered scores, candidate FIFO max
358, energy lookup age max 847/2048 and no ingress stalls, matching the preceding
profile's high-water marks. Its complete portable receipt is
`reports/starlink-bank-owned-capacity64-extension-20260910.json`. All **101** local
runner/collector/resource/slice unit tests and Ruff pass at extension freeze.

At this extension's initial freeze, the 4096 soak has **not completed**. Its
eventual status must come from its own terminal receipt; neither unit tests nor
the preceding 64-block passes count as a 4096 result. A tool poll timeout is not
permission to restart the simulation or overwrite evidence.
