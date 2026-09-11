# Quiet publication fence: integrated actual FFT, improved route, not closed

DO NOT MERGE or deploy. FW/HDL branch:
`codex/starlink-rx-only-do-not-merge-replay-quiet-fence`.

FW `d146246cd01446b3dd30d1008e7b725b7f2edc80`.
HDL `587c2dd5302e991ac46e58e6cb2f765dd6cc3c32`.
Both branches are pushed; primary receiver HDL is not promoted.

## Implemented and tested

The simpler quiet-phase publication controller now drives the actual FFT and
buffer subsystem. It is opt-in in both simulation and synthesis, retains the
original default predicate and fails closed for unsupported profiles. Only one
of 22 compiled runtime modules changes, with no new clocked state, latency,
arithmetic or buffer changes. Current external/mailbox faults and late event
rejection remain enforced; active-job validation is not globally replaced.

**820 regression plus 12 new evidence tests pass (832 distinct).** The separate
19-test audit run includes seven already-counted archive tests. A first command
used a nonexistent filename and ran no tests; the corrected command passed.
71 focused preflight tests also pass. Both actual FFT campaigns pass, with
**64,512 numerical records and CSV bytes identical to the parent**, unchanged
service clocks `3663/3663/4929/11729/3663/3663`, 512 status-byte/valid sweep
cases, ten late-event rejection/fresh-recovery cases and 3075 forced-stall
observations. Predicted-accept counters include stalled observations and are
not publication counts. This is bounded simulation, not a universal formal proof.

## Measured physical result

| Metric | Parent | Integrated fence |
| --- | ---: | ---: |
| Worst setup slack, ns | -1.661 | -1.241 |
| Total negative slack, ns | -474.560 | -274.139 |
| Failing setup endpoints | 944 | 572 |
| Same-domain 175 MHz slack, ns | -1.661 | -1.235 |

All 8502 routable nets route without errors; hold and pulse checks pass. The
candidate uses 2825 LUT, 5796 FF, 21 DSP and 15 RAMB18. The route uses the exact
original 100/175 MHz OOC constraints and recipe, with no new timing exceptions.

**The old status-payload-to-output-request path is removed.** Read-only queries
of all five actual FFT status FIFO payload registers find no path to
`output_bank/request_toggle_reg/D`, including the previously failing bit 0.

Two distinct problems remain:

1. Same-domain guard fault/commit feedback is still -1.235 ns, ten logic levels,
   6.803 ns data delay (5.107 ns routing). Source is inverse guard fault-reason
   bit 3; destination is that guard's commit pulse. Related fast-fault slack is
   -1.228 ns. This is a real fast-clock logic problem even if CDC is qualified.
2. Global worst is held output metadata bit 8 crossing 175 to 100 MHz:
   -1.241 ns, zero logic levels, 0.894 ns data delay, against a 0.002 ns
   inter-clock edge requirement. It needs a justified bundled-data handshake
   contract and physical bounds, not blanket false-path masking.

Reset structural checks remain intact. CDC inventory is unchanged: nine CDC-3
information items and 208 CDC-15 warnings. There are 114 unconstrained inputs
and 124 outputs in this OOC report. **No full receiver or deployment signoff.**

## Next step and preserved scope

Keep this candidate pinned. Next derive and test a local, phase-specific guard
commit/fault contract for the remaining fast-domain cone, without stale grants
or delayed rejection of a bad publication. Repeat actual FFT and route before
adding features. Separately qualify held CDC lifetimes and propose bounded
delay/skew constraints using the actual board clock plan; report that change
independently.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required; no TX functionality was removed. Full receiver integration/timing,
continuous RX, actual 60 MS/s calibration, sustained Ethernet/IIO, blind GLRT
comparison, 120 ms dwells and 300 s scanning remain release gates. Only then
use a pinned PPU package/rollback for .18 canary and .17 Ethernet deployment.
No radios, PPU/main or primary production HDL were changed.

## Durable evidence

[Archive](20260911-replay-quiet-fence-evidence.tgz) and
[read-back receipt](20260911-replay-quiet-fence-evidence.json):
32,999,091 bytes / 5917 members, SHA256
`a97442502574c0643e544025369f8f57db53c70a75b3e85eaebcf9b10149f2da`.
All archived members are individually verified. Includes frozen sources, actual
FFT logs/CSV, synthesized and routed checkpoints, test XML, inspection receipts
and reference shadow sources. Raw RAM evidence remains retained.

Prepared: `74a8ab46a668e51ee3d9b7e3f8a8f4e7a83180b7c9c3168b3ea4b71ab60800a9`.
Routed DCP: `52822300aeea2cba032328efda2c40db032ccb93a6a22385c0e359f9166c7bec`.
Parent: [quiet-phase shadow contract](20260911-replay-quiet-contract.md).
Implementation details are in the experimental branch's
`docs/starlink-replay-quiet-fence-20260911.md`.

Disk housekeeping made only clean, inactive completion-stage and private-facts
FW worktrees sparse for committed reports, freeing duplicate checkout space.
Those reports remain recoverable from Git; HDL, raw evidence and primary reports
were not removed.
