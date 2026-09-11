# Split preflight identity: targeted path passes, full timing still fails

DO NOT MERGE or deploy. FW/HDL branch:
`codex/starlink-rx-only-do-not-merge-split-preflight-identity`.
FW `f5c10235cbb9d62b82570144365a7ee820d4468e`;
HDL `ac16ab63d9e79675586c5e9c08958e3b336a0035`. Both pushed.

## Implemented and verified

Each source/product bank is compared with the held descriptor before selecting
the one-bit equality result. This removes phase selection from the front of the
wide current preflight comparison. Default mode and the second expected-product
comparison are unchanged. X/Z phase retains the original merged-vector equality;
naively selecting two equality results is not four-state equivalent.

One of 22 runtime modules changes. No register, latency, lease transition, clock,
buffer, arithmetic or current fault gate changes. This is not a delayed or stale
certificate. The same opt-in profile is checked in actual simulation and synthesis.

**874 regression + ten new actual-evidence tests pass (884 distinct).** The 23
component/lint tests include twelve 8578-case comparisons, every metadata bit,
four-state phases/data, invalid profiles and rejected unsafe implementations.
The 17-test evidence run includes seven already-counted archive tests.

Both actual FFT campaigns pass. All **64512 indexed numerical records and CSV
bytes remain exact**, with service clocks `3663/3663/4929/11729/3663/3663`.
Current-equality witnesses cover 500645 main checks (570 source / 622 product
preflight observations) and 435366 auxiliary checks (368 / 584). Existing
corruption, cancellation, reset, pending-publication and recovery cases pass.
This is bounded simulation, not full receiver or continuous-RX qualification.

## Routed result

| Metric | Private-offer parent | Split preflight |
| --- | ---: | ---: |
| Targeted metadata-to-fast-fault slack, ns | -1.322 | +0.052 |
| Worst same-domain 175 MHz slack, ns | -1.322 | -1.037 |
| Global worst slack, ns | -1.322 | -1.373 |
| Total negative slack, ns | -323.338 | -292.853 |
| Failing setup endpoints | 622 | 580 |
| LUT / FF | 2808 / 5796 | 2758 / 5793 |

The exact product-bank metadata bit 34 to fast-fault path passes, with logic
depth reduced from eight to six. This does not mean all preflight paths or the
subsystem pass. The earlier quiet-fence candidate remains -1.241 global WNS /
-1.235 same-domain WNS / 572 failures; retain all candidates without receiver
promotion. Split preflight improves recent fast-domain timing, not full signoff.

Remaining fast-domain worst: fast-reset synchronizer stage 1 to output-bank
publication request, -1.037 ns, nine levels, 6.698 ns data delay (5.126 ns routing).
The queried reset-to-ROM-valid path improves -1.318 to -0.760 ns but still fails.
Global worst is held output metadata bit 6 crossing 175 to 100 MHz, zero logic
levels, 1.076 ns data delay; it needs separate CDC qualification.

All 8457 routable nets route without errors. Hold (+0.062 ns) and pulse (1.830 ns)
pass; DSP/RAMB18 remain 21/15. Original 100/175 MHz OOC clocks, route recipe and
exceptions are unchanged. No timing waiver was added.

Reset structural checks pass. CDC counts are nine CDC-3 information items and
**209 CDC-15 warnings, up one**: source metadata bit 6 has a synthesized reader
register replica. Output metadata bit 5 also uses its original source register
instead of the prior replica. Both reports are retained; the additional crossing
must be covered by eventual held-data physical bounds. There are still 114
unconstrained inputs and 124 outputs in OOC.

## Next step / path to deployment

Investigate a caller-specific reset-release simplification. In the actual top,
outer reset synchronizers are monotonic during a common epoch; the registered
release receipts may already imply their outer-running conjunctions. Prove that
implication under reset assertion/release, stopped clocks and unknown reset
values before removing any redundant combinational dependency. Preserve raw
asynchronous cancellation and generic default behavior. Then repeat actual FFT
and route before features; qualify held metadata CDC separately.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Full receiver timing/CDC/board clocks, actual RX calibration, continuous
RX, sustained Ethernet/IIO, blind GLRT, 120 ms dwells and 300 s scans remain gates.
Only then: pinned PPU package/rollback, .18 canary and .17 Ethernet-only deployment.
No radios were accessed, including .20/.21; no PPU/main, primary HDL or TX removal.

## Preserved evidence

[Archive](20260911-split-preflight-identity-evidence.tgz),
[read-back receipt](20260911-split-preflight-identity-evidence.json):
33,124,997 bytes / 5898 members, SHA256
`b9ed083dd3a56a0296cf7b27bb78f7ab9388af15886911781d653819cddf9ee7`.
All members verified. Includes frozen source, actual FFT logs/CSV, synthesis and
routed checkpoints, tests, inspections, parent source and parent CDC report.
Raw evidence remains `/dev/shm/starlink-split-preflight.2BQ3zjL5`.

Prepared: `1bf6ac30a6f5e3ee45b5cf489d1adecaeef08ab8ecc93495c6281fff035293c1`.
Routed DCP: `1f999a60e7f35e0ffddc8dd09ce7dcfb9c9213a733fb853bd3a983c9939865c5`.
Parent: [private quarantine offer](20260911-private-quarantine-offer-actual-route.md).

Disk housekeeping made only clean inactive split-product-capacity,
product-final-capacity and product-validation-stage FW worktrees sparse for
duplicate committed reports. Git retains them recoverably; their HDL, raw
evidence and primary reports were not removed.
