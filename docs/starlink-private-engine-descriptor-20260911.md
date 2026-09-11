# Private scheduler descriptor capture — DO NOT MERGE candidate

Parent integrated input stage: FW `6af13552f961eba23e0caeea4d2782773fd72a7c`,
HDL `73363ec5e2a865d0b3d63cfb5c5d0277d33d47d0`. New branch:
`codex/starlink-rx-only-do-not-merge-private-engine-descriptor`.

## Runtime change and proof boundary

Only the registered scheduler's 70-bit `engine_metadata` capture changes. In
WAIT_BANK it follows selected metadata every clock, without destination-capacity
or quarantine gating. The payload freezes on leaving WAIT_BANK. Original state,
phase/lease, reservation, admission and completion decisions remain literal.
The legacy scheduler branch is unchanged. No new register, cycle or CDC.

On the original healthy WAIT_BANK transfer both versions capture the same
selected metadata. While waiting, extra private captures may differ, including
unknown metadata and a cancelled capture on the quarantine edge. They must not
reach job admission, FFT configuration/delivery or new output publication.
Previously published/unread output is a separate ownership domain and may still
be read; this change does not cancel healthy old reader ownership.

A full top inverse permits only the separate capture process and removal of its
two old assignments. The other 18 compiled runtime modules are unchanged.
The historical input-stage inverse uses its pinned parent while the current
capture has its own complete inverse. Current input-stage, fault, certificate
and publication equations remain tested.

## Frozen verification gates and results

18 focused tests pass in 0.45 s. A source-extracted sequential test covers 4096
four-state reset/state/quarantine/valid/capacity/payload combinations using the
original procedural if/case semantics, with 732 private-only differences. It requires reset, equality on original
transfer and freeze through active processing. Four mutants fail: capture while
active, miss the transfer edge, lose reset and corrupt captured data. This is
not full RTL formal verification or arbitrary-state control equivalence.

The broader suite passes **504 tests in 73.33 s**, no failures/errors/skips.
The real-FFT bench has an independent original descriptor register witness.
Differences are allowed only in WAIT_BANK/quarantine with no new admission,
configuration, FFT delivery, output completion or replay authorization.
Six new cases exercise known/unknown invalid-source data, unavailable destination
with queued input, current vendor fault cancellation, and fast/slow reset after
extra private capture. Each requires fresh 512-read/one-release recovery.
All inherited numerical, input-stage, fault/reset, publication and service tests
remain active. The 5215-clock gate and 3,000,000 ns deadline are unchanged.

Prepared inventory (36 files):
`f6e1d4b8dd2df5c927fdcf0859ca6a17fee6c53c675a0b7c01668a9d413b08f7`.
Synthesis succeeds in 99.06 s with unchanged source receipts, DCP
`6dd0976739854008c2e6f7c949ce97d02197a1a4adeeff2ebd2e2d8ad4cbfe0e`.
Actual generated FFT passes in **197.42 s**. All 64512 numerical records match
the reference and the input-stage parent's CSV remains byte-identical:
`44fae7467811a9e0f71d63330ee5c868c676c9a4c0ffb29f6f649be23e003279`.
Service stays 3661/3661/4928/11728/3661/3661 clocks; the 11728 case includes the
deliberate 9000-clock reader stall, excluded from the unchanged service bound.

The original-engine witness checks 500505 cycles, observing 171981 private-only
descriptor differences and no difference reaching an owned/public operation.
All six new boundary cases recover with 512 correct reads and one actual reader
release. Invalid-source known/unknown capture resumes without requiring a reset;
the queued-input capacity stall resumes the same bank; fault/reset cases recover
after coordinated reset. These are cycle observations, not RF frame counts or
all-state formal equivalence. All inherited assertions remain active.
Nine evidence-auditor tests pass in 1.43 s, rejecting incomplete cases, missing
recovery/release, stale reads, inadequate coverage and lost owned-data proof.

## Routed result

The unchanged route completes in 48.53 s with source/checkpoint audits passing
and zero routing errors. **Setup still fails. No timing or deployment promotion.**

| Metric | Input-stage parent | Private engine capture |
| --- | ---: | ---: |
| WNS (ns) | -1.503 | -1.686 |
| TNS (ns) | -521.325 | -478.515 |
| Failing setup endpoints | 896 | 748 |
| LUTs | 2724 | 2726 |
| Flip-flops | 5670 | 5667 |

Total negative slack improves by 42.810 ns and 148 fewer endpoints fail, but
worst slack regresses by 0.183 ns. Neither candidate dominates all metrics.
Both use 21 DSPs and 15 RAMB18s. New route: 8261 fully routed nets, hold +0.072 ns
and pulse +1.830 ns with no failures. The same 114 unconstrained inputs and
124 unconstrained outputs remain visible in this diagnostic OOC build.
Routed DCP:
`d47abc1369d28ee3a5dc35870c6376f3011524105dc50cebd82c3630500b287a`.

The reported worst path moved from engine-metadata CE to product output metadata
through the product bank's framing comparison/current fault aggregation and into
the inverse guard's `awaiting_ack` D. It has eight levels and 7.347 ns data delay,
including 5.837 ns routing (79.4%). Removing one wide enable did not close the
remaining shared fault-control network.

Next evaluate recombining the previously verified private ACK-retirement
alternate (`470eae1919e1ebaab2b5b3af7e05a3a9137af375`) with this runtime. Its
pre-change guard matches the current guard exactly. It separates private ACK
occupancy from the current fault while retaining the original public ACK and
same-edge sticky quarantine. That prior isolated proof/route is not proof for
this combination: recheck fault accounting, known/unknown behavior, actual
reader release, held payload, fresh recovery, numerical/service equivalence and
route. Do not assume occupancy clearing is permission to release/reuse a bank.
No ACK-retirement change is implemented by this candidate.

## Physical target and full release scope

The parent route fails at -1.503 ns WNS / -521.325 ns TNS / 896 endpoints.
Worst path is output-bank fault through capacity to engine-metadata CE, with
seven levels and a final enable driving 72 loads. This candidate removes the
capacity/quarantine gate from that private payload enable. Only a routed result
can establish improvement. The retained guard-fact reference remains -1.340 ns
WNS / -463.636 ns TNS / 821 endpoints; neither is deployment-qualified.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
unchanged. Full receiver timing/CDC/reset/board constraints, sustained capture,
actual 60 MS/s calibration and Ethernet/IIO tests still precede reversible `.18`
canary and `.17` PPU Ethernet-only deployment with pinned rollback. Final gate
is 300-second scanning, 120 ms valid dwells and blind host GLRT comparison.
No radio, PPU/main or primary production HDL change in this experiment.

## Evidence locations

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/private-engine-descriptor-worktree-v1`.
Actual/synthesis/prepared/route artifacts are sibling `staged-enginecapture-*`.
Test scratch is `/dev/shm/starlink-engine-tests.tbmC57` to avoid disk exhaustion;
this RAM-backed scratch is volatile. The curated package must preserve its
sources/logs/XML before handoff, using the explicit `--test-root` argument.
No radio or production evidence is stored only in RAM scratch.
