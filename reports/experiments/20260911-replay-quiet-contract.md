# Replay quiet-phase contract: verified shadow, runtime unchanged

DO NOT MERGE or deploy. Branch (FW/HDL):
`codex/starlink-rx-only-do-not-merge-replay-quiet-contract`.
FW `476a32b89`, HDL `ae352b231`.

## What this establishes

During output replay, the tested subsystem is in inverse ACK_DRAIN with both
producer guards inactive and no preflight in progress. In that context, a new
status/output/frame/input event is an orphan regardless of its payload. The
inactive guard fault summary reduces exactly to event presence plus mailbox
fault; status exponent/header decoding is unnecessary at this boundary.

The proposed shadow publication predicate retains current external, retained,
product, output-bank, framing and result-fault checks. It is not a global
replacement for active-job validation: an active producer can legitimately
receive status. All **22 compiled runtime modules remain byte-identical**.
Only tests/shadow logic changed; no new synthesis or route was run.

## Evidence

- Thirteen new component/source tests include eight 4112-case four-state
  algebra checks and four rejected unsafe reductions, including applying the
  inactive reduction to an active producer.
- **767 regression tests pass** before the monitor correction; 59 focused and
  30 historical compatibility tests pass afterward. Eleven new evidence tests
  pass, plus seven overlapping archive tests: **778 distinct regression/new-
  evidence tests**, excluding repeated subsets.
- Corrected actual FFT main/auxiliary campaigns pass in **199.18 / 185.73 s**.
  All **64512 indexed numerical records and CSV bytes match the parent**.
  Service remains 3663/3663/4929/11729/3663/3663 clocks.
- Main shadow: 500645 checks, 3136 replay offers, 3132 predicted accepts and
  **3075 deliberately paused observations**. Predicted accepts during forced
  stalls are not actual publications. The original unforced predicate and
  the deliberately forced-off signal are independently checked.
- Auxiliary: 435888 checks, 588 offers, 311 predicted accepts; **all 256 status
  bytes with valid low and high** (512 checks), plus ten clocked late-event
  cases. Status patterns include X/Z, and late output/frame events are covered.
  Every clocked case rejects publication and demonstrates fresh 512-word,
  one-release recovery. Existing fault/reset/ACK tests remain passing.

The first main run compared against an output intentionally forced low by an
existing stall test. It was rejected and retained. The correction compares the
original equation through those stalls and separately verifies the override;
no test was skipped and no runtime source changed. This is bounded simulation
plus inactive-guard algebra, not formal proof of all possible scheduler states.

## Next step and deployment gate

Implement an opt-in replay-specific publication fence using explicit owner-
active signals and this current phase/fault predicate. Retain the original as
the default/reference and keep active-job status validation unchanged. Recheck
late events, corruption, forced stalls, resets, recovery and numerical equality
on the changed runtime, then route under unchanged constraints. Compare the
exact status-to-publication path and overall timing, not only the local result.

Timing remains the inherited **−1.661 ns WNS / −474.560 ns TNS / 944 failing
endpoints**. No improvement or deployment is claimed. Native 60 MS/s fine
search and independent 2.5 MS/s CI16 inspection remain required. Full receiver
timing/CDC/reset, board clocks, actual RX calibration, sustained IIO/Ethernet,
reversible `.18` canary and `.17` PPU Ethernet-only deployment with rollback,
120 ms dwells, 300 s scans and blind host GLRT comparison remain outstanding.
No radios, PPU/main or primary production HDL changed.

## Preserved artifacts

[Archive](20260911-replay-quiet-contract-evidence.tgz),
[verified readback](20260911-replay-quiet-contract-evidence.json):
26697186 bytes / 6199 members, SHA256
`aeff44c6bdd10f5dd6eb3ec7e3cd4b25b219e90865ac1f97b3c527d49f83ad9f`.
Includes rejected/corrected snapshots and logs, actual CSVs, tests and the
explicitly labeled inherited parent checkpoint/report. No raw evidence deleted.

V2 prepared: `4608ae9ac75663c6e5eee752ee2489d7ef79c38701172d0572218413860ec850`.
Inherited routed DCP: `456b3dbb87310f1c68a0188f4568d72552091b8b7e86b9ec81e52a90c7254d1e`.
Parent: [private-admission facts route](20260911-private-admission-facts-actual-route.md).
