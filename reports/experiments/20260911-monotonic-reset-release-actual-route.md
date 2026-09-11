# Monotonic reset release: exact behavior, fewer failures, timing still open

DO NOT MERGE or deploy. FW/HDL branch:
`codex/starlink-rx-only-do-not-merge-monotonic-reset-release`.
FW `fd574fe0b259a68bc48fe475f0de1d631c9c3e2b`;
HDL `5b8589c9966642927ac2f19a036b07d6105a456e`. Both pushed.

## Implemented and verified

The actual top's four reset synchronizers rise monotonically within a common
raw reset epoch. Existing release receipts therefore already imply the outer
readiness terms. An explicit opt-in removes those two redundant terms from
the barrier outputs; the raw asynchronous reset fence and every state update
remain unchanged. Generic callers retain the original vetoes by default.
Tests demonstrate why arbitrary nonmonotonic outer inputs cannot use the opt-in.

Only the barrier and its top-level parameter connection change in the 22-module
runtime. No registers, latency, payload buffers, FFT arithmetic, publication
semantics or constraints are added/changed. Synthesis and actual FFT use the same
enabled profile; independent witnesses compare the original release expressions.

**948 distinct tests pass:** 921 regression, 16 additional explicitly enabled
payload-mailbox tests and 11 new evidence/profile rejection tests. The focused
component campaign compares the complete parent barrier using actual top reset
logic over three clock ratios, four phases, both modes and 25 reset epochs/run.
It covers independent X/Z reset, unknown idle, stopped clocks, release before
restart and unsafe release mutants. The mailbox campaign completes 156 blocks
through 120 resets and rejects four unsafe mailbox implementations.

Both real generated-FFT campaigns pass. All **64,512 indexed numerical records
and CSV bytes match the parent**, with unchanged service clocks
`3663/3663/4929/11729/3663/3663`. Reset witness counts (fast/slow/reset):
main `503564/287723/272`; auxiliary `437625/250071/215`. Inherited fault,
corruption, cancellation, pending-publication and fresh-recovery checks pass.
This remains bounded simulation, not continuous RX or board qualification.

## Physical results — not a promotion

| Metric | Split-preflight parent | Monotonic release |
| --- | ---: | ---: |
| Global WNS, ns | -1.373 | -1.399 |
| Same 175 MHz domain WNS, ns | -1.037 | -1.324 |
| TNS, ns | -292.853 | -250.635 |
| Failing setup endpoints | 580 | 446 |
| LUT / FF | 2758 / 5793 | 2739 / 5787 |

Both exact old reset-stage-1 paths (to output request and ROM valid) are absent.
The earlier product metadata bit 34 to fast-fault path passes at +0.137 ns.
Nevertheless worst same-domain timing regresses: the new worst path is
`epoch_barrier/fast_release_reg/C` → `fast_fault_reg/D`, ten logic levels,
6.983 ns data delay, 5.287 ns routing (75.7%). Its reset-enable cone has a
2156-fanout net and traverses product readiness and forward fault logic.
Removing an old source did not eliminate that downstream control chain.

Global worst is `fast_fault_reg/C` → `fast_fault_slow_reg[0]/D`, a 175→100 MHz
synchronizer crossing; this needs separate CDC constraint/physical qualification,
not a blanket waiver. All 8426 nets route without errors. Hold +0.075 ns and
pulse +1.830 ns pass; DSP/RAMB18 remain 21/15. Clocks and route recipe unchanged.

Reset first-stage fanout and registered-purge structure checks pass. CDC counts
are nine CDC-3 information items and 208 CDC-15 warnings (parent 209); both
reports are retained. This count reduction does not qualify held-data CDC.
The OOC 114 unconstrained inputs and 124 outputs remain unqualified.

## Next step / deployment gates

Keep this candidate and parent; do not promote based on endpoint count alone.
Inspect and simplify the release→product-ready→forward-fault cone. Require an
exact proof of registered fault next-state and public transfers across all phases,
reset and fault events before altering it. Merely moving the same reset term,
delaying a veto or adding an unsupported timing exception is not a fix.
Repeat the actual FFT and route gate for any candidate; qualify CDC independently.

Native 60 MS/s fine search and the independent 2.5 MS/s CI16 IIO inspection stream
remain required. Full receiver timing/CDC/real board clocks, actual 60 MS/s RX
calibration, continuous RX, sustained Ethernet/IIO, blind GLRT comparison, 120 ms
dwells and 300 s scans remain deployment gates. Then use pinned PPU firmware and
rollback for `.18` canary, followed by `.17` Ethernet-only reception verification.
No radios were accessed; `.20/.21` remain untouched. No PPU/main, primary HDL,
TX or clock/exception changes were made.

## Preserved evidence

[Archive](20260911-monotonic-reset-release-evidence.tgz),
[read-back receipt](20260911-monotonic-reset-release-evidence.json):
33,148,925 bytes / 6552 members, SHA256
`51154f5b7588766a241996786a98422324ed2fd963507524927e5829a8637062`.
Every member verified. Includes frozen source, real FFT logs/CSV, synthesis and
routed checkpoints, regression/component evidence, inspections and parent CDC.
Raw evidence remains `/dev/shm/starlink-monotonic-reset.pL4aOpKf`.

Prepared: `adb2543750adea239f66f5b187057aef1ecdbd112cbcf5faef2161f7f6ddb3f3`.
Routed DCP: `97363f456b8fc8527d455e37f1348ab6f26bee232a6d42ed8c0c8236a8a9904d`.
Parent: [split preflight](20260911-split-preflight-identity-actual-route.md).
