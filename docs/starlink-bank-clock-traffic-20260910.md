# Generated 175 MHz clock under complete coarse traffic

The final v3 actual-IP simulation passes five full exact replays and four active
reset cases using the generated 175 MHz MMCM, real XFFT and unchanged complete
bank-owned IQ-to-score runtime. All 18 runtime RTL modules, seven numerical
goldens, kernel, clock/FFT helpers and existing/default benches are unchanged.
No RTL bug was found or fixed.

The final run checks 7,853 accepted scores, 10,752 forward words, 10,752 product
words and 9,985 inverse words exactly, including faulted provisional prefixes.
The retained VALID score in the manual-reset case is also checked repeatedly;
it is not counted as accepted. Five healthy epochs each supply 1,341 scores and
1,536 words at each transform stage. The four failed epochs supply accepted
score prefixes of 179, 387, 482 and 100.

This is functional simulation at the current runtime revision, not a receiver
profile switch, input-clock-loss detector, physical reset/CDC/timing signoff,
registered-control route-variant qualification, pilot/native fine test or RF
result. The independent 100 MHz input clock never stops.

## Contract frozen before evaluation

Read contracts: [complete bank coarse](starlink-bank-owned-iq-to-score-20260910.md),
[bank FFT ownership](starlink-fft-bank-owned-study-20260910.md), and existing
`reports/experiments/20260910-bank-clock-epoch.md`. The tested wiring is
`fft_resetn = resetn && manual_fft_resetn && locked`; this wiring is in the new
testbench, not a changed receiver clock/reset connection.

- Use actual generated Clocking Wizard 6.0 and XFFT IP through their unchanged
  checked helpers. The MMCM is 100 MHz input, nominal 175 MHz output, with
  primitive ratio 20.125 / 2 / 5.750. No forced LOCKED, clock, fault or payload.
- Drive only the immutable 1,406-sample/three-block numerical fixture at a
  15/100 phase-accumulator cadence. Each explicit epoch uses a fresh synthetic
  index origin. Check every actual forward/product acceptance on `fft_clk`,
  inverse acceptance on `clk`, and every presented score on `clk`, including
  stalled VALID and provisional prefixes. Check data, identity, ordinal, TLAST,
  both relevant exponents and denominator state, without a blanket fault-run
  numerical waiver. The actual complete scheduler, energy cache and score path
  are present; no stub transform, substituted score or altered arithmetic.
- Observe real MMCM LOCKED drop after reset request. Check domain reset fences,
  readiness, core input, inverse validity and public scores closed at a 2 ps
  simulation observation step after actual FFT-epoch reset fall. Do not charge
  this bound from raw MMCM reset or interpret it as hardware propagation timing.
- The still-enabled outer detector must latch its sticky fault by the next
  slow edge (10.0021 ns observation bound after actual epoch fall). Source data
  continues during quarantine; relock or manual-reset release alone must not
  restore operation. No stale score, inverse output or fast work may appear in
  quarantine, while FFT reset is asserted, or before fresh source admission.
- Recover explicitly with an enable-low interval, then enable-high and a fresh
  source-index epoch. Require exact full replay after every fault. This is the
  existing component's enable-cycle recovery contract, not PSMA health-history
  recovery; the outer `resetn` remains high throughout the active reset tests.
- Measure 1,024 generated-clock periods in every healthy replay, with the same
  preexisting ±0.005 ns average-period simulation tolerance. Require five unique
  exact-replay epochs, all four unique reset kinds and one exact terminal PASS;
  reject FAIL/FAULT or simulator fatal/error text even alongside PASS.

## Actual reset witnesses

All timestamps are ns of simulation time. The first two reset requests follow
actual vendor input acceptance at position 128, verified in its own FFT clock
domain, with second-block identity and direction. Output reset follows actual
slow-domain acceptance of second-block inverse position 256.

| Kind / live witness | Accepted score prefix | Raw request | Observed LOCKED / FFT-epoch fall | Closure observed | Outer fault observed |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0: second forward input | 179 | 222990.716 | 222991.716 | 222991.718 | 222995.002 |
| 1: second inverse input | 387 | 457290.715 | 457291.715 | 457291.717 | 457295.002 |
| 2: second inverse output prefix | 482 | 703775.002 | 703776.002 | 703776.004 | 703785.002 |
| 3: retained real score and nonempty candidate FIFO, manual FFT-only reset | 100 | 923750.002 | FFT epoch: 923750.002; LOCKED never falls | 923750.004 | 923755.002 |

In all three MMCM cases, this model's LOCKED falls 1.000 ns after raw reset.
The measured outer-fault observations follow epoch fall by 3.286, 3.287 and
9.000 ns; manual reset gives 5.000 ns. These are sampled simulation witnesses,
not worst-case hardware latency guarantees. MMCM relock is observed at
225827.500, 460127.500 and 706607.500 ns. Enable stays asserted and the outer
fault remains sticky through relock and a further 100 slow clocks. Manual reset
explicitly requires LOCKED to stay high throughout its observation window.

The reset discards unfinished work and may withdraw the unaccepted retained
score; it does not undo previously accepted provisional words. The checker does
not promote those failed-epoch prefixes to healthy acquisition or RF evidence.
Fresh exact replays start at distinct indices and cannot accept an old prefix as
their new data. The recovery interval itself requires no scores/inverse outputs
or fast input, closing the gap while per-epoch numerical counters restart.

Mean output periods across the five 1,024-edge observations are 5.714286133,
5.714285156, 5.714285156, 5.714285156 and 5.714286133 ns. This is primitive-model
quantization under the specified finite stimuli, not jitter or routed-clock
qualification. Final simulation duration is 1,074,922.142 ns. On x86_64 Linux
host `gauss`, Vivado 2022.2 reported simulator-kernel CPU 61.000 s and roughly
77 s elapsed for `launch_simulation`; these are offline host measurements, not
Zynq real-time capacity.

## Sources, tests and retained evidence

Independent worktree:
`/tmp/starlink-coarse-alternatives.Y3JzOI/clock-traffic`, branch
`codex/starlink-rx-only-do-not-merge-clock-traffic`.
Starting FW `135769292a8282d2d7a9e7beb30332e60eab2387`, HDL
`dbe744c015217c7b9c33a5f89e4745916b43100a`.
Additive HDL bench/runner commit: `7d4d6d8cb482e60cf7ee557f2e86905d26155dd5`.

- New bench: `hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_bank_clock_traffic.sv`.
- New runner: `hdl/library/starlink_pss_acquisition/simulate_bank_owned_clock_traffic.tcl`.
- New executable policy suite: `tests/test_starlink_bank_clock_traffic_policy.py`.
- Final full local evidence: `hdl/library/starlink_pss_acquisition/build/bank-clock-traffic-175-v3`.
- Adjacent JSON receipt: `docs/starlink-bank-clock-traffic-20260910.json`.
- Portable archive: `reports/experiments/20260910-bank-clock-traffic.tgz`.

Archive SHA-256: `2a1bbe146df0c61c5848c83eb437f48251097be6789e100215b2c9be7340e386`.

Each of v1/v2/v3 has 32 frozen local input files, generated clock/FFT wrapper
hashes, full Vivado transcript and actual simulator log. The archive retains
those non-vendor inputs, logs and receipts plus final JUnit output; generated
vendor RTL/project binaries are excluded and reproducible with the frozen
helpers. Original goldens are reused from
`/tmp/starlink-bank-route.I50MDJ/main-phase-map-175-v1/frozen_sources`.

Final selected SHA-256 values:

```text
bench       e318822e96fc82f87c906a4b024daa47a83fd2c94e02d6edbe811d17dea7a2c3
runner      42df150d985e7ff5ddc042cfd243aec2cf6fab71290cfcdcbfe9422b7e2a45e8
scope       7d59201a74a28a4dee73a0b9f3038c20a394994641041b317640881d2c9cea1e
simulate    ac349b0bfb38908dd91cdf23a3a35b2d2adc59c1f46f90328c709b359688ff71
MMCM top    862789262b9799660e3acde6330a38542a24e92d628b08e3530aaeec84ed22f7
MMCM inner  ca069bc37de99c84459775ff8a21f9a04156b9fb7fc735325568d6a8bd52dc5a
FFT wrapper a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68
```

All three actual-IP runs passed their then-current contracts with identical
numeric/reset results. V1's initial policy test had a copied protected-file list
for a different map/PSMA runner (60 pass, one failure); the failing source and a
clearly labeled failure receipt are retained. No runtime input changed to fix
that test. V2 froze the corrected/expanded policy suite and stricter unique
healthy-epoch postprocessing. Final v3 adds explicit stale-publication checks
in reset and pre-source recovery intervals. Earlier passes are not relabeled as
covering those added assertions. There was no actual RTL assertion failure.

Final new policy suite: 70 pass. Together with existing clock, bank-owned
runner and exact-receipt suites: 149 pass; Ruff and both git diff checks pass.
These unit tests cover strict arity/tool/non-overwrite admission, bounded
vector geometry/size, source freezing, missing/duplicate/wrong-count replay and
reset receipts, missing totals, duplicate terminal, FAIL and simulator fatal.
They supplement the actual-IP run, not replace it.

Reproduce from `hdl/library/starlink_pss_acquisition`, using a new output path:

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vitis_HLS/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -source simulate_bank_owned_clock_traffic.tcl \
  -tclargs NEW_OUTPUT EXISTING_NUMERIC_VECTORS
```

Remaining gates: arbitrary reset phase/width and ownership-state sweeps,
input-clock-loss behavior, physical recovery/removal and CDC timing, exact
receiver-generated clock/constraints/board reference preservation, production
duration/capacity, source30/60 adapters, concurrent pilot/native fine ownership,
PSMA/driver recovery, IIO/DMA and RF. No synth/route, receiver profile/BD/AXI edit,
radio, PPU mutation, main worktree edit, deployment or remote push occurred.
