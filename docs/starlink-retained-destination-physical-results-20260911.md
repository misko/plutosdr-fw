# Contextual destination candidate — experimental, DO NOT MERGE

This candidate is separate from bank-local identity. No radio or production
HDL promotion is implied. Firmware remains on the rom-prefetch do-not-merge lane.

## Actual FFT qualification

Root-owned vendor session 3613 terminated successfully in 61.05 seconds.
All 77,953 numerical rows match the offered-summary reference byte-for-byte:
`07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
An independent comparison of the entire parsed result also matches after removing
only the additive destination witness. Seven context service times remain
3645/3645/4912/3645/3645/3645/3645 cycles. The new witness makes 89,723 pre-edge
and 89,723 post-edge comparisons and observes 17 releases, 19 admissions and
19 publications. Original numerical, fault, reset and service checks remain.

The 85-test preparation gate passes with 132 source files unchanged. Original
and executed source checks pass, as does the generated vendor FFT source hash.
This is seven-context simulation, not continuous 60 MS/s RX or physical signoff.

## Physical preparation

The new physical recipe derives the complete helper, Tcl, admission and test
files from the offered-summary reference with checked whole-file inverses.
It replaces exactly three runtime files; all other thirteen are unchanged.
The old retained owner is compiled only for the simulation observer and is
explicitly excluded from synthesis. The contextual option is enabled and its
effective generic readback is checked.

69 physical-policy tests pass, with all 22 source assets unchanged. These include
the inherited 60 tests plus nine destination-specific checks: actual compiled
runtime selection, five option-readback mutations, real read-only actual
admission, and two complete-file inverse mutation checks. Mock Tcl fixtures do
not constitute vendor execution. The prepared inventory contains 149 entries
plus SHA256SUMS, whose SHA256 is
`f528f69000db4552498f013c5a17f7a667fc13cda7c899658cade811753ec764`.

Same FPGA part, single FFT, 100/175 MHz diagnostic clocks, synthesis settings,
route recipe and constraints as the reference. No new timing exceptions.
Synthesis and routing results must be recorded separately before any promotion.
The recipe still depends on the pinned recovery-local original actual bundle;
it is an experimental source-specific reproduction, not a portable release tool.

## Evidence

All paths below are under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:

- `destination-actual-prepare-parent.vbfomY3U/final`: 85-test gate and snapshots.
- `destination-actual-prelaunch-parent-v1`: frozen actual bundle, manifest SHA256
  `183a0ccce954efc48d30f598d4965459695e756e20e8ca32ba47c7ee21bf3363`.
- `destination-actual-parent.LQnQo9ny`: terminal actual owner, complete run and independent audit.
- `destination-physical-prep-parent.NJlhw5AK`: 69-test gate and 22-source snapshot.
- `destination-synthesis-prepared-parent-v1`: frozen physical inputs.
- `destination-synth-parent.G1XLB1ik`: source-specific synthesis owner and run.

Remaining release gates: routed island timing, complete receiver setup/hold,
CDC/reset/board-I/O qualification, sustained acquisition plus 2.5 MS/s IIO,
actual 60 MS/s RX calibration, `.18` canary, then `.17` PPU Ethernet deployment
and bounded 300-second blind FPGA/host comparison.
