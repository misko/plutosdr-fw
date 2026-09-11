# Staged output ownership: actual FFT PASS, routed timing FAIL

Implemented a synthesizable command arbiter/publication adapter and integrated
it into the inverse-output side of the actual shared FFT/kernel/IFFT subsystem.
It retains the full descriptor once, carries compact output-bank tags, replays
the final private word only after validated COMMIT, and waits for real reader
ACK before RELEASE. A held allocation return or full descriptor table cannot
block an older job's completion/release. The forward/cutover controls are not
yet replaced; no production receiver/radio is using this candidate.

## Verified results

- Actual generated FFT: four healthy/backpressure contexts pass; all **43,008
  numerical records** match the previous actual FFT evidence independently.
  Each context contains six transforms and 1536 complete final reader samples.
- Normal service: **3655 fast clocks**, versus 3645 before. The qualifying
  stalled case takes 4927, below the unchanged 5215-cycle cap. A deliberately
  9000-clock-stalled reader is tested separately, without a capacity claim.
- The actual bench observes forward processing while the old inverse result
  remains reader-owned; this overlap was not removed to simplify the design.
- **259 combined regression tests** pass; nine additional audit tests pass,
  including rejection of corrupted/missing results. These are not RF tests.
- Synthesis and routing both complete using the unchanged device, diagnostic
  clocks and route directives. No timing exception was added.

Timing still **FAILS**: WNS **-2.726 ns**, TNS -1156.969 ns, 1110 failing setup
endpoints. Hold +0.061 ns passes; 7967 nets are fully routed with zero errors.
Routed resources are 2625 LUT, 5310 FF, 21 DSP and 15 RAMB18. Worst slack is
better than the last -3.106 ns candidate, but worse than the -2.504 ns reference;
this is not an accepted overall timing/resource improvement.

The worst path now goes from expected-product metadata through shared fault
logic and completion acceptance into FFT cutover/reset state: **ten logic
levels, 8.387 ns data delay**, of which 6.492 ns is routing. The old inverse
retained-owner endpoint is removed. The next step is to stage the remaining
admission/completion handover rather than feeding raw wide checks into cutover.

## Important remaining qualifications

Five critical CDC findings and 114/124 unconstrained input/output ports remain.
The new descriptor lookup currently ends at output ports, not a restored
reader-clock descriptor register. Reduced metadata CDC warning counts therefore
do not establish safety; that boundary must be added and qualified. Four healthy
contexts do not replace the full reset/fault/paused-clock campaign. This is not
full receiver timing, sustained 60 MS/s, Ethernet/IIO or deployment verification.

Native 60 MS/s fine search and independent 2.5 MS/s IIO remain required. Firmware
and HDL work stay on the remote **codex/starlink-rx-only-do-not-merge-rom-prefetch**
lane. The primary production HDL gitlink, PPU, main branches and all radios are
unchanged. After full qualification: `.18` reversible canary, then `.17` via
PPU Ethernet and the 300-second blind FPGA/host GLRT comparison.

## Evidence

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Successful actual/synthesis/route directories: `staged-output-actual-v5`,
`staged-output-synth-v5`, `staged-output-route-v5`. Failed v1–v4 runs are retained:
an XSim logging exception, a pending-reservation integration bug, and an implicit
generated-scope readiness wire. Checks caught them; none was accepted as PASS.

Frozen input digest: `ebbbf355df97b09b174bd2d96aa09693b52b84e1e320114aea0a1bcb007dfd11`.
Numerical CSV: `c35159d51b2ebdda97287ac9557a096da1931c0ced38911f8f142ec67d7a4f8b`.
Routed DCP: `fed1e302410c65e7d00fff133499190ee3094190b4663b2584c9391dd23b7ba7`.
Independent audit verifies original/copied sources, checkpoints, all clock-pair
worst paths, timing summary, resource counts and route status. All vendor handles
are terminal. Detailed implementation contract is in the experiment worktree's
`docs/starlink-staged-output-integration-20260911.md`.

[Verified source/results archive](20260911-staged-output-evidence.tgz):
11,057,556 bytes, 4093 regular members, all read-back checked against SHA256
and size in its manifest. Archive SHA256:
`c6ce2f962dca5cfe71a6e7b922deebd9fe4ee189ec9e1bf03791d7da979829af`.
Includes all five prepared revisions, failed and passing actual logs, numerical
CSV, source-matched synthesis/routing checkpoints and reports, and test evidence.
Generated vendor caches/waveforms are excluded, not silently counted as tests.
