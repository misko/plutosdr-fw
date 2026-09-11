# Clocked admission: actual PASS, improved routing still FAILS

Implemented a clocked private admission certificate in the real shared FFT and
buffer subsystem. It captures independent validation facts only after the
required capacities are available, then issues one ownership token. Current
faults still quarantine private occupancy before emitted FFT start; publication
and actual reader ACK checks remain unchanged. A follow-up removes live
completion-valid gating from the private descriptor lookup, using held inverse
ownership instead. Full descriptor validation still precedes publication.

## Verified results

Final V3 actual generated-FFT simulation passes in 73.66 seconds. All **64,512
numerical records**, service intervals and previous reset/fault results match V2
exactly, and numerical data/exponents independently match the earlier pinned
actual reference. Six numerical/backpressure contexts, two stopped-reader reset
cases, seven previous fault cases and **six new admission cancellation cases**
pass. A fast-edge assertion checks the partitioned reject facts against the
original current-fault predicate throughout the actual campaign.

Normal service is **3657 fast clocks**, two more than the prior handover design.
The qualifying stalled case remains 4927, below the unchanged 5215-cycle cap.
The deliberately 9000-clock-stalled reader is checked without a capacity claim.
Forward processing still overlaps an older retained inverse output.

**321 regression tests pass in 43.87 seconds**, including isolated token tests
with 66 zero/X/Z rejection trials, four unsafe RTL mutants, and admission-audit
negative controls against both actual runs. Parser controls are not extra
hardware executions. V1 actual integration exposed a frozen-not-ready capacity
bug; the failed run and its synthesis are retained, not counted as successful.

## Physical comparison

All rows use the same device, diagnostic 100/175 MHz clocks, FFT configuration
and route recipe, with no additional timing exceptions.

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Handover baseline | -3.970 ns | -2566.980 ns | 2261 |
| Clocked admission V2 | -3.451 ns | -1926.674 ns | 1602 |
| Held lookup V3 | **-3.080 ns** | **-1541.860 ns** | **1511** |

V3 synthesis/route finish in 105.80/55.04 seconds. Hold +0.060 ns and pulse
+1.830 ns pass; 8281 nets route with zero errors. Resources are 2765 LUT,
5552 FF, 21 DSP and 15 RAMB18. Timing still fails, and WNS remains worse than
the older staged-output -2.726 ns baseline. This is not full-island timing
closure, a continuous 60 MS/s result or a deployable package.

The worst path now runs from held phase through input identity/fault checking
into the **completion receipt**: 11 logic levels, 8.697 ns data delay, including
6.877 ns routing. Descriptor validation remains among other top paths.
Five critical CDC findings, 208 warnings and 114/124 unconstrained I/O remain.

## Next step and deployment path

Apply a clocked validation/ownership certificate to producer completion,
holding the descriptor/bank identity while it is checked. Preserve reset/fault
cancellation, immediate publication fences, and quiet/raw-event checks before
core reset/reuse. Test cancellation at every new stage boundary, then repeat
actual FFT verification and route before adding features. This must not become
a global delayed-fault shortcut or a timing waiver.

Full receiver timing/CDC/reset/board constraints, sustained native **60 MS/s fine
search** plus independent **2.5 MS/s CI16 IIO inspection**, and actual RX
calibration remain release gates. Then `.18` reversible canary, `.17` PPU
Ethernet-only deployment with pinned rollback, and the 300-second scan with
120 ms valid dwells and blind host GLRT comparison. No radio, PPU or main branch
was changed; the primary production HDL gitlink remains unchanged.

## Reproducible evidence

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Final directories: `staged-admission-prepared-v3`, `staged-admission-actual-v3`,
`staged-admission-synth-v3`, `staged-admission-route-v3`. All vendor handles are
terminal. Independent audit checks source receipts/checkpoints, every clock
pair, timing summary, utilization and routing status.

Final frozen inventory: `a2d6340562dbbbdea164f991e2e50d283805c2d43b1fbbe0121c57dc193c617b`.
V2/V3 numerical CSV: `b3543f3daa7a99d9fc6e945b5af7e9febaabab00cc6eed4761db41f1d4ce2c59`.
Final synthesis DCP: `b718847bb26446357b0a6644b662a857e79afbfde8c8e3721c59010c73837fd0`.
Final routed DCP: `53a8540ee842e9da4aad0e8218478c8f28787c2f34fab3a29fdd73a1646fad76`.

[Verified source/results archive](20260911-staged-admission-evidence.tgz):
28,451,091 bytes, 10,229 regular members, all read-back checked by SHA256 and
size. SHA256: `4939f42cf2432e73c359680a74c79718a8c004a582b7780657722e9558c49d29`.
It contains all three frozen candidates, actual logs including the failed V1,
three synthesis results, both routed attempts, test and audit evidence.

Implementation commits: FW `017202701ebb784dcadce91476066a70530ebdcd`,
HDL `956dc4a1a303e974b4aa55af56253094414857df`, on the separate remote
`codex/starlink-rx-only-do-not-merge-rom-prefetch` lane. No merge into main.
