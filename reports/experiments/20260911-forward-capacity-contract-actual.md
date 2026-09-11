# Parallel forward readiness: actual-FFT shadow contract, not routed integration

DO NOT MERGE or deploy. FW/HDL branch:
`codex/starlink-rx-only-do-not-merge-forward-capacity-contract`.
FW `11b161a694d24bec1def5bbb3fe67f2b0f2bd2f7`;
HDL `ac869ae20b6844b88aecf153d6f4f9f059195295`. Both pushed.

## What this establishes

The previous worst same-domain path traverses reset release, several backward
ready decisions and forward fault detection. A parallel calculation can express
the same capacity using five pipeline occupancy bits plus the private product
slot's current capacity/fault conditions. No delayed readiness, removed reset
fence or assumed always-ready destination is needed for the equation.

The algebra comparison passes 110,592 combinations: exhaustive binary inputs,
individual X/Z substitutions and randomized four-state data/control. Outer reset
is known zero/one, as supplied by the common barrier. Five mutants dropping
reset, fault, occupancy or final-slot checks are rejected.

**964 distinct tests pass:** 956 corrected regression tests and eight new
source-bound evidence rejection tests. Both corrected actual generated-FFT
campaigns pass. All 64,512 numerical records/CSV bytes and service clocks
`3663/3663/4929/11729/3663/3663` remain identical to the parent.

| Shadow observations | Main | Auxiliary |
| --- | ---: | ---: |
| Exact unforced readiness checks | 503564 | 437625 |
| Healthy external-fault condition | 493734 | 432630 |
| External fault asserted | 6911 | 2736 |
| Deliberately overridden kernel ready | 16 | 0 |
| Deliberately overridden summary bit | 2 | 0 |
| Hypothetical common-summary differences | 2 | 0 |
| Unexplained differences | 0 | 0 |

All 22 runtime modules and the synthesis profile are byte-identical to the
monotonic-reset parent. This commit adds observations to the bench, not control
to the receiver. No new synthesis or routing result is claimed. Inherited timing
still FAILS: −1.399 ns global / −1.324 ns same-domain WNS, 446 setup failures.

## Failure found and corrected

The first auxiliary run stopped at product-stage boundary 11, which deliberately
forces the transport `product_valid` wire to X. The shadow had incorrectly used
that wire for the arithmetic output occupancy. The original arithmetic READY
uses its owning output-valid register. Version 2 changes only that observation
to `product.arithmetic.output_valid`; the forced-X test and runtime are unchanged.
The first failed run, its snapshot and the successful reruns are preserved.

The two main common-summary differences are also retained, not called exact
behavior: a test forcibly replaces an internal summary bit. These observations
do not authorize bypassing a ready failure or fault input in production.

## Concrete next implementation

1. Export current arithmetic/operand pipeline occupancy through explicit module
   ports; retain all numerical operations and storage behavior byte-for-byte.
2. Factor the producer's authoritative kernel READY calculation with a parallel
   capacity input. Keep defaults unchanged, the original reset/protocol-fault
   fence, and the original output-stage enables. Do not introduce an independent
   capacity-based fault summary that ignores the existing READY/summary inputs.
3. Compare old/new READY and accepted transfers cycle-for-cycle. Preserve the
   original direct-ready and summary fault injections and require their same
   cancellation/quarantine/publication behavior, plus reset and stopped clocks.
4. Freeze the integrated source, repeat the complete actual-FFT campaigns, then
   synthesize and route at the unchanged clocks. A shadow pass alone is not
   evidence that this refactor improves physical timing.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
requirements. Full receiver timing/CDC/board-clock qualification, 60 MS/s RX
calibration, continuous RX, sustained Ethernet/IIO, blind GLRT and 120 ms/300 s
scan verification remain gates. Only then qualify pinned PPU firmware/rollback
on `.18`, followed by `.17` Ethernet-only deployment and outdoor verification.
No radios, PPU/main, primary HDL, clocks, timing exceptions or TX were changed;
`.20/.21` remain untouched.

## Evidence

[Read-back-verified archive](20260911-forward-capacity-contract-evidence.tgz),
[receipt](20260911-forward-capacity-contract-evidence.json):
32,822,959 bytes / 11684 members; SHA256
`cd39f2f0d71164d0dc25fc3de58eb00c9117b492b99ed8bd765bf213c836d300`.
Includes both source versions and runs, tests, logs/CSV and explicitly labelled
inherited failing route evidence. Raw data: `/dev/shm/starlink-forward-capacity.tHq0mgHO`.
Version 2 prepared SHA:
`a00d28c144210551b42a63b64f204f9ad0707b4553345abbaa1d193f4323a08e`.
Parent: [monotonic reset release](20260911-monotonic-reset-release-actual-route.md).
