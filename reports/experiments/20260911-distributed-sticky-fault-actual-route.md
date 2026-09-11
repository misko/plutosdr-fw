# Distributed sticky capture: functionally equivalent, physical regression

DO NOT MERGE or deploy. Branch:
`codex/starlink-rx-only-do-not-merge-distributed-sticky-fault`.
FW `9de4677902fb05dfd6c921a78ea1238b2b211d39`;
HDL `6ae94a38681a1c3448eb5483748ddc83a434144a`.

Nineteen independent cause groups replace the single scalar sticky-fault
capture, on the same clock edge. Their registered OR becomes fast_fault.
The supported known configuration uses existing admission-reject groups with
the exact preflight context selection; other/unknown configurations fall back
to the original scalar. Per-bit procedural conditionals retain the original
X/Z and sticky behavior. Immediate publication vetoes remain unchanged.
Only the top changes at runtime, plus an additive bench witness; all 22 runtime
modules, arithmetic, clocks, helper/Tcl recipe and interfaces remain in scope.

## Tests and actual generated FFT

**1027 distinct tests pass:** 1017 regression and ten witness-gate checks.
The current capture block and source-extracted scalar reference pass 313297
clocked four-state checks; reset, lost causes, nonsticky updates, context and
fallback mutants fail. Exact inverses reconstruct the parent runtime/bench.

Both actual campaigns preserve all 64512 CSV records and service clocks
`3663/3663/4929/11729/3663/3663`. Scalar/source and same-edge sticky comparisons
cover 503565 main and 437626 auxiliary clocks. Fault-present clocks are
6957/2750, reset clocks 2922/2260. Cause masks are 0x663ff/0x40fdd, union
0x66fff: groups 12, 15 and 16 were not asserted by the actual campaign and have
finite source-level, not integrated injection, coverage. All inherited
forward-final, summary-force, late-fault, reset, publication and recovery checks
pass. No continuous-RX or RF accuracy claim follows from these simulations.

## Routed result: reject

| Metric | Scalar parent | Distributed capture |
| --- | ---: | ---: |
| Global WNS (ns) | -1.331 | -2.514 |
| Same-island WNS (ns) | -1.189 | -2.120 |
| TNS (ns) | -277.204 | -678.141 |
| Setup failures | 526 | 1184 |
| LUT / FF | 2732 / 5798 | 2775 / 5809 |
| FFT → fault capture (ns) | -1.189 | +0.624 |
| Worst capture-register → island (ns) | -0.976 | -1.999 |

The input path improves, but the OR moves onto downstream controls. Global
worst is cause 18 to fast_fault_slow's first synchronizer stage. The report adds
**one critical CDC-10: combinational logic before a synchronizer**. CDC-3 falls
9→8; CDC-15 stays 208. No waiver is applied. Same-island worst is inverse guard
fault reasons through input/control qualification to the forward input-counter
enable, nine logic levels, 7.581 ns data delay, 76.7% routing.

All 8475 nets route without errors; hold +0.058 ns and pulse +1.830 ns pass.
DSP/RAMB18 remain 21/15. Reset first-stage/purge checks pass but do not qualify
the changed fault crossing. OOC 114/124 input/output ports remain unqualified.
Matched queries include all nineteen cause registers and one replica.
Two initial read-only probes failed closed on wildcard/hierarchy selection;
their scripts/logs are retained. Corrected probes ran against both checkpoints.
An absent object was never interpreted as a removed timing path.

## Next step and release gates

Do not promote this topology. Retain the scalar parent and rejected evidence.
Next keep the original single fault register and its direct registered CDC
source, but feed it from the flatter checked cause expression. This tests
input-side logic absorption without moving the register boundary or delaying
faults. Require source/four-state, actual fault/reset/publication, numerical and
service checks, a direct registered fault-CDC structural check, then routing.
Its physical benefit is not yet established.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Full receiver timing/CDC/real clocks, actual 60 MS/s RX calibration,
continuous RX, sustained Ethernet/IIO, blind GLRT, 120 ms dwells and 300 s scans
remain deployment gates. Then qualify pinned PPU/rollback on .18 before .17
Ethernet-only deployment. No radios, PPU/main, primary HDL pointer or TX changes;
.20/.21 remain excluded.

## Evidence

[Archive](20260911-distributed-sticky-fault-evidence.tgz),
[read-back receipt](20260911-distributed-sticky-fault-evidence.json):
33,633,059 bytes / 6405 members, SHA256
`0efa5e404fb4069b0efd8b83a9f1a86f7a1bba553e9a7085bcdfcce5bb5aae94`.
Includes sources, numerical logs/CSV, synthesis/routed checkpoints, tests,
failed/corrected probes, targeted paths and CDC reports.
Raw: `/dev/shm/starlink-sticky-fault.4qIKHja5`.
Prepared SHA: `9cd61fa49b0dc1313c1c6c03679a5cf0fd757cb6ac76ad8c2b8325fcf5e40f50`.
Routed DCP SHA: `4a0895a2a56ffcf7f93a11e6dc20786e3e9f78547456327d8c59d44b82e52793`.
Parent: [forward-final route](20260911-forward-final-commit-actual-route.md).
