# PSS firmware stop decision — 2026-09-12 05:09 UTC

## Decision: NO-GO; abort the incremental timing-closure path

The user requested strict goals and an end to open-ended work after three days.
No more timing variants, refactors, build sweeps or speculative deployment ETAs
are authorized under this incremental approach. Preserve all evidence and the
existing firmware. No radio is flashed, no experimental HDL is promoted and
nothing is merged into main.

The current in-flight product-publication candidate has completed routing:
- Same-175 MHz setup slack: **-1.067 ns**, versus previous **-0.881 ns**.
- Overall WNS **-1.210 ns**, TNS **-344.221 ns**.
- **880 failing endpoints**, versus previous **655**.
- No routing errors, but routing completion is not timing closure.
- 114 inputs and 124 outputs remain unqualified.
- Native 60 MS/s sustained receiver, DMA/IIO, calibration and RF deployment
  qualification have not been established by these subsystem tests.

The actual source-bound audit is at:
`/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/product-publication-artifacts.wq8KFULp/route-v1/audit.json`.
Routed DCP SHA256:
`259a284f5761f8ca527bea1ae888bd429b5015e5ea58032e77e4ec08b436cc08`.

## Hard gates, not a rolling ETA

1. Current actual-FFT/buffer subsystem must pass all required setup, hold and
   pulse timing without unsupported timing exceptions. **FAILED: stop.**
2. Only after gate 1: full receiver timing/CDC/reset/I/O qualification at actual
   board clocks, preserving native 60 MS/s fine search and the independent
   2.5 MS/s inspection stream.
3. Only after gate 2: serial-verified .18 calibration and sustained 60 MS/s
   operation, independent correctness checks and clean restart.
4. Only after gate 3: reversible Ethernet PPU deployment to .17, bounded
   outdoor reception and host/replay comparison.

Passing simulations or a smaller negative slack cannot substitute for any gate.
The full implement/test/deploy/verify objective is **not achieved**.

## Permitted closeout only

Allow already-running simulations/regression to finish for an honest final
record, preserve their terminal results and the failed route, and push the
checkpoint to the explicit do-not-merge branch. Do not launch additional
implementation or timing experiments. Closeout does not reopen development.

Branch: `codex/starlink-rx-only-do-not-merge-product-publication`.
No PPU, main or radio changes. .14/.20/.21 remain excluded.

Any future effort needs an explicit user-approved restart: a materially revised
architecture or hardware choice, a fixed budget/deadline, and the same end-to-end
release gates. Do not automatically resume the incremental sequence from an
active-goal continuation.
