# Lower FFT clock experiment — rejected for the unchanged pipeline

This is retained negative evidence, not a receiver clock change. At canonical
15 MS/s, both 150 and 175 MHz pass the short 1341-score numeric replay but fail
the 64-block burst/stall workload with energy-cache misses. The required entry
has already been overwritten. Measured completed-block rates are approximately
12.93 and 14.37 million scores/s, respectively, below the 15 million/s input.

The full receiver continues to use its original 100/200 MHz clocks. Neither a
larger cache nor a short numerical pass establishes sustainable throughput.
No radio or receiver timing constraint was changed.

The JSON receipt is `reports/starlink-fft-clock-throughput-20260909.json`.
It records source identities, exact failures, checksums and evidence limits.

## Reproduction

Use an isolated HDL worktree at `18c96bb93f0aea5f868fb8b4c15a2eb1bce7a873`.
The archived patch changes only `simulate_iq_to_score_shared.tcl`; it also
applies cleanly to its unchanged runner at baseline `6090190c4442d2fd0e825136d87b692e2ad6deef`.
Do not apply it to a live build's worktree.

1. Apply `20260909-fft-clock-throughput.patch` with `git apply --unidiff-zero`
   inside the isolated HDL worktree. This zero-context archive avoids retaining
   trailing whitespace in patch context; use only the pinned source above.
2. Set `STARLINK_PSS_CLOCK_EXPERIMENT_HDL` to that worktree and run pytest on
   `20260909-fft-clock-policy-probe.py`. All 18 policy checks must pass.
3. With Vivado 2022.2 and fresh output directories, run the patched runner with
   `STARLINK_PSS_SIM_FFT_MHZ=150` or `175`:

   - Numeric arguments: `NEW_OUTPUT numeric FROZEN_VECTORS 1`.
   - Capacity arguments: `NEW_OUTPUT capacity 64 bursty-stalled 1`.

4. Preserve complete logs and nonzero exits. Inspect the actual fatal cause,
   required/available cache indexes, completed blocks and simulation time.

The seven immutable numeric vectors are retained under
`hdl/library/starlink_pss_raw_correlator/build/input-cursor-paired-v1/frozen_sources`
in the original firmware workspace. Each generated evidence directory freezes
all its exact RTL, coefficients and stimulus. The nominal 200 MHz generated FFT
configuration is deliberately unchanged; only its behavioral clock changes.
