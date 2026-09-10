# Inverse sealed-bank integration: parent verification

DO NOT MERGE firmware. This is offline functional evidence, not a flashable
receiver, actual FFT throughput, timing closure or RF qualification.

## Frozen 136-test repeat

Parent read the complete revised contract, test bodies and new bench changes at
FW `fbfcd628855d8d9b6e1daa7c2ec23f37e6a9e593` / HDL
`0e1f103c3427424aeb6aa92e9b2d0c5cf2c9ddec`. Independent original **62163
exited 0: 136 tests passed in 11.96 seconds**. Eight RTL/bench/test/recipe source
hashes matched before and after. The runtime remains the previously reviewed
issuer `8ad9c2e7`, CDC bank `ea27c4e2`, integrated top `2f988a16`, and unchanged
result guard `09ab3533`; full hashes are in the earlier smoke review and receipts.

Recovery-parent `inverse-full-parent.ZiUWdIT9` contains the before-source hashes,
every case's exact sources/commands/compile/simulation logs, pytest log and JUnit.
Log SHA-256: `ed87616dfbeabe4c0d3224a28b042943bd60a120a7a101bdb28585842249a30e`.
JUnit: `f7f327a44612568655f36d72066f0e96652e6e6227fb6489e5c9681718da791d`.

Verified scope:

- Original 16 synthetic ownership tests and their old guard shadows remain.
- Nonzero 512-word data with exact full 75-bit metadata through actual result
  guards and the new issuer/bank, two leases, and immediate/300-cycle-delayed
  status. The raw-result generator is not an FFT arithmetic model.
- Ten relative clock phases, five scenarios each. The 40 healthy lifecycle
  receipts show publication +2 fast clocks, actual ACK-to-release 1, and reuse
  +4 to +6 versus the concurrent original guard/mailbox. The separate long
  first/final-stall scenario reports reuse +3. These are observed cases, not an
  exhaustive CDC phase bound or complete FFT-pair service measurement.
- Deadline expiry at actual guard age 8191 vetoes the new would-publish edge
  while the independent certificate has already been captured. A new current
  fault also prevents publication.
- Paused slow read prefixes reach exactly 19 from 17 and 512 from 510 under
  the existing two-stage fault visibility; neither permits healthy release.
  A request not yet synchronized before fault produces zero output words.
- Thirty directed metadata-corruption cases: ten selected bits at first,
  interior and final tokens, covering exponent/start/direction and bits 72–74.
  These are not 75 separate bit corruptions at every position. Delayed check
  faults retain the correct offered position and lease.
- Fourteen common-reset joins (seven ownership stages, each raw-reset side),
  fresh recovery and first/final stalled VALID/data stability.
- Eight complete-top paused-source reset cases, described below.
- Ten executed mutants fail at their intended checks: certificate loss, actual
  ACK, held-final new-offer handling, second-job lease, owned reservation,
  stalled VALID withdrawal, and both source reset barriers on both raw sides.
  The wrong-lease mutant is detected by the bounded watchdog, not an immediate
  wrong-lease-specific assertion; this distinction remains in the raw logs.

## Independent directed checks before the full repeat

Parent also reconstructed the earlier immutable seven-case nonzero suite:
**7 passed in 0.50 s**, recovery `inverse-guard-parent.aZEe1gS6`, with all seven
source inventories equal to the original. Removing only the certificate-loss
veto in a temporary copy causes `commit=0, publication=1, age=8191`. Splitting
the original combined premise/veto assertion proved the exact defect. Restoring
the unchanged issuer with that diagnostic split passes. The implementation
owner incorporated the split and mutation before the 136-test freeze. Both
expected failing mutant attempts and the passing control are preserved.

The eight paused-source cases were separately repeated from immutable copies:
original **62773 exited 0: 8 passed in 1.56 s**, recovery
`inverse-purge-parent.xjURA3TY`; all eight 17-file inventories match the original.
Both raw-reset sides are tested with two separately reachable old states:
healthy unread full source, or malformed empty source with a sticky fault.
The slow clock remains paused for 80 fast clocks after reset release. The
reader, fault synchronizer, core and preflight must remain closed. Recovery
then verifies 512 fresh source identities and 512 synthetic-zero outputs,
including a fresh full source filled while fast clock is paused. A genuinely
new source fault must still cross and quarantine afterwards.

Two additional parent temporary mutants independently disable the actual reader
reset barrier and the source-fault synchronizer barrier. Each fails the stale
state check in its naturally reachable fixture. The original top was restored
to its exact hash; no implementation worktree or radio was modified by these
negative controls.

## Portable receipts and next gate

All three parent artifact trees, including expected failures, are archived in
`20260910-inverse-sealed-parent-integration.tgz`: 14,640,513 bytes, SHA-256
`b5ac7dee44012c8c2db215f06cbd5d25373b7904fd8ab93997a47c7436357e01`.
The archive was compared to its originals with `tar --compare`. Redundant pytest
`*current` symlinks are excluded; original files remain in the recovery tree.

This cut establishes enough functional evidence to start additive **offline
actual-core preparation** while the independent event/source/dependency receipt
checks finish. Keep original FFT, arithmetic, numerical vectors and fault gates;
explicitly account for changed private fault timing and added lifecycle latency.
Freeze the preparation and review its source closure/observers before vendor
execution. No synthesis, routing, full receiver promotion or deployment is
authorized by this result. Firmware main and the primary runtime HDL gitlink
remain unchanged. Source 15/30/60, native fine search, independent 2.5 MS/s IIO,
causal 120 ms/300 s scanning and staged hardware deployment remain the full goal.

## Final independent event/source/graph repeat

Parent original82374 exited0: **235 passed in15.98 seconds**, using both
`test_inverse_sealed.py` and `test_inverse_sealed_receipts.py` at source FW
`4ebd11f8a1653f3c8dffc5b81c3812d709fe66cb` / HDL
`1df9b316216d7d35866d87a0d34dd8bb1846a482`. Recovery tree:
`inverse-final-parent.eIGWIG5L`. Log SHA-256
`eaa7932225b6a0279b05a2f21364e116d59047fe432678915d1cb289b52078e1`;
JUnit `c3b7b1ea472d5a82e73e4e1179e2e80f3d9f4f4fbf720c2da9715a449d51fa7d`.

The sole HDL delta from the136 cut is11 testbench lines for an actual tagged
release opportunity: after512 reads and ACK, a current fault must suppress
release/reuse. Its missing-veto mutant fails the specific edge assertion.
Runtime issuer/bank/top are unchanged. New tests also enforce invalid/X/Z
parameter rejection, exact imported Python source closure and compiler errors
even if Icarus exits0. Continuous/net graph checks detect deliberate registered-
diagnostic bypass feedback; procedural state is a cut, not a physical CDC proof.

Parent review found a verifier timestamp gap: S1 checked slow-clock order but
did not advance its cursor. The one-line model fix plus a post-S1 OUT moved to
S1-1 now fails specifically for slow event order; the missing-update mutant
accepts that same19-word negative log. This changes evidence validation, not RTL.
The previous234 run and separate99-test correction remain preserved, not
retroactively described as one235-test execution.

All parent results and per-case source copies are in
`20260910-inverse-final-parent.tgz`,17694601 bytes, SHA-256
`9d87de080bbef872d75b4212d661a20b3e04bdfccf9bae365bef62cf9d916c42`.
`tar --compare` matches originals, excluding redundant pytest `*current` aliases.
Publication to the separate DNM branch is approved; no runtime gitlink promotion.

Next: additive actual-core preparation. Inspection of the old actual CSV shows
status preceding the last raw result, unlike the delayed-status fixture. A
directed early-status case must measure that join before fixing service bounds;
the delayed-status +2 publication observation is not a universal latency claim.
Preserve the original absolute service budget, arithmetic and fault intents.

Parent also independently reconstructed the two committed archive parts at FW
`652e2ea37aa7c2e08e4adb19006d8fd0b19fc240`:72134497 bytes, SHA-256
`1701af578e98da39555a0aecfbe757c7fe4a8907f5aaa797d6fc02c7140d3c71`.
All11890 payload hashes plus the separately pinned inventory hash verify;
11891 unique safe regular members, exact closure, no extraction. First audit
11630 rejected the distinct inventory entry with `KeyError: inventory.json`;
corrected audit54371 explicitly checks its existing external hash and exits0.
No archive/source was modified. The owner's FW32532 and HDL64538 pushes report
terminal0 to the inverse DNM remote, not main.

### Actual early-status and clock-domain baseline audit

Parent independently parsed the entire accepted L1 trace at
`/tmp/starlink-coarse-alternatives.Y3JzOI/bank-arithmetic/hdl/library/starlink_pss_acquisition/build/local-admission-actual-R1B1O1-L1-175-prepared-v4/project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim/fft_bank_owned_trace.csv`,
first checking SHA-256
`e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71`.
All76 healthy jobs (38 forward/38 inverse) satisfy config+3,512 input samples
from+5 through+517,512 raw outputs from+1298 through+1809, status+1300 and
old commit+1810, relative to admission. Status is on the THIRD raw output
(zero-based ordinal2), not the first. First inverse absolute fast cycles are
admission2772/status4072/last raw4581/commit4582.

Forward admission intervals in nominal epoch1 are24x4548 and7x4549 fast cycles;
backpressure epoch2 has3x4821 and2x4822. Nominal maximum4549 at175MHz is
25.994286us against447 canonical samples/15MS/s =29.8us =5215 fast clocks,
leaving666 nominal cycles. These are original ideal-clock observations, not
new sealed-bank full-pair throughput or arbitrary-stall guarantees.

The independent review and parent source read also confirm the arithmetic
event CSV's `cycle` column is stream-dependent: forward/product record
`fast_cycle`; inverse records `slow_cycle`. Future event-indexed equivalence
must retain sample/metadata identity AND use explicit domain mapping plus
absolute fast-domain complete-pair measurements. Subtracting unlike counters
or discarding all time columns would not prove the service requirement.

The owner's directed first-word early-status test reports14PASS and publication
+3/reuse+6..7, separately from the old delayed-status+2/+4..6. Root requested
an additional actual-third-word witness before the next source freeze; this
owner result is not yet a parent repeated test or actual-core throughput pass.
