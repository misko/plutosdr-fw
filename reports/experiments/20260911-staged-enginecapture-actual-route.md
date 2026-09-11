# Private engine descriptor: actual FFT proof and mixed route result

Branch `codex/starlink-rx-only-do-not-merge-private-engine-descriptor`:
FW `9edd8c943`, HDL `fc16f21aa8a62fe48e9d7f2889f6fc0f4a820be8`.
Based on the integrated input-stage candidate, not a production promotion.
**Functional verification passes. Setup timing still fails; do not deploy.**

## What changed

The registered scheduler's 70-bit descriptor follows selected metadata while
WAIT_BANK, then freezes when the original ownership transition advances state.
Capacity and quarantine no longer drive this private payload's enable. The
state/phase/lease, reservations, admission and completion decisions are unchanged.
The legacy scheduler branch is unchanged. No added register, cycle or CDC.

The payload can differ from the old implementation while waiting or cancelling,
including unknown input metadata. It must equal the old descriptor on healthy
transfer and never use a private-only difference for a job start, FFT operation
or new publication. Previously published/unread data retains independent reader
ownership. A full top source inverse confines this change; other runtime modules
are preserved. Historical input-stage comparisons use their pinned parent while
the current descriptor change has its own complete inverse.

## Verification

**504 regression tests pass in 73.33 s**, plus **nine evidence-auditor tests** in
1.43 s. Focused source-extracted testing covers 4096 four-state combinations,
including 732 extra private captures, with transfer equality and active freeze.
Four broken variants fail: active capture, missed transfer, lost reset and data
corruption. These are tests and source arguments, not full RTL formal proof.

Actual generated FFT passes in **197.42 s**. All **64512 numerical records** and
the parent's CSV are exact. Service is unchanged:
3661/3661/4928/11728/3661/3661 clocks. The deliberately stalled reader contributes
9000 clocks to the 11728 case, excluded from the unchanged 5215-clock service
gate. The original simulation deadline was not extended.

An independent original-descriptor witness checks **500505 cycles** and observes
**171981 private-only differences**, none reaching an owned/public operation.
Six new actual FFT cases cover invalid-source known/unknown metadata, blocked
destination with queued input, a current vendor fault, and fast/slow resets.
All resume/recover with 512 correct reads and one actual reader release. The
known/unknown idle-source cases resume without resetting; the capacity-stall
case consumes the same queued bank. All inherited fault, input-stage, reset,
publication pause and numerical assertions remain active. These counts are not
RF frames or continuous native receiver throughput.

## Physical result

Synthesis completes in 99.06 s, unchanged routing in 48.53 s. Source/checkpoint
audits pass, with no routing errors. Setup still fails:

| Metric | Input-stage parent | Private engine capture |
| --- | ---: | ---: |
| WNS (ns) | -1.503 | -1.686 |
| TNS (ns) | -521.325 | -478.515 |
| Failing setup endpoints | 896 | 748 |
| LUTs | 2724 | 2726 |
| Flip-flops | 5670 | 5667 |

There are **148 fewer failing endpoints** and 42.810 ns less total negative slack,
but worst slack is 0.183 ns worse. Retain both candidates; neither dominates.
The older guard-fact reference is -1.340 ns WNS / -463.636 ns TNS / 821 endpoints.
Both new candidates use 21 DSPs and 15 RAMB18s. Engine capture has 8261 fully
routed nets, hold +0.072 ns and pulse +1.830 ns with no failures. The diagnostic
OOC build still has 114 unconstrained inputs and 124 unconstrained outputs.

The reported worst path is now **product metadata -> product-bank framing
comparison/current faults -> inverse guard awaiting-ACK D**: eight levels,
7.347 ns data delay, 5.837 ns routing (79.4%). The descriptor-enable change moved
the worst path but did not close the remaining shared fault-control network.

## Next bounded combination

Evaluate the existing private ACK-retirement alternate, HDL
`470eae1919e1ebaab2b5b3af7e05a3a9137af375`, on this runtime. Its pre-change guard
is byte-identical to the current guard (SHA
`ba0b9e308e2747e43edeec6c9b4bb486b2c1fc12d7d850d2bbf6a6ff02cc4431`).
It allows private ACK occupancy to clear under a known fault while retaining the
original public ACK rejection and same-edge sticky quarantine. Do not treat
private occupancy clearing as actual reader release or bank reuse permission.
Its earlier proof does not qualify this combination: recheck full idle-fault
accounting, X/Z behavior, reader ownership, held payload, reset/recovery,
numerical/service agreement, then route. No such combination is implemented here.

Full receiver timing/CDC/reset/board clocks, sustained native capture, actual
60 MS/s calibration and Ethernet/IIO qualification remain before reversible
`.18` canary and `.17` PPU Ethernet-only deployment with pinned rollback. Final
gate remains 300-second scanning, 120 ms valid dwells and blind host GLRT.
Native 60 MS/s fine search and independent 2.5 MS/s inspection remain untouched.
No radios, PPU/main or primary production HDL changes.

## Preserved evidence

[Read-back verified archive](20260911-staged-enginecapture-evidence.tgz) and
[receipt](20260911-staged-enginecapture-evidence.json): 15873555 bytes, 7527
members. SHA256:
`1e339cf91ee11d1cfd91c7590ad7aeb49a15d0c42014e48574762fc1c8424287`.
Includes frozen sources, actual numerical/fault logs, prepared inventory,
synthesis/routed checkpoints and reports, tests, source references and XML.

- Prepared: `f6e1d4b8dd2df5c927fdcf0859ca6a17fee6c53c675a0b7c01668a9d413b08f7`.
- CSV: `44fae7467811a9e0f71d63330ee5c868c676c9a4c0ffb29f6f649be23e003279`.
- Synthesis: `6dd0976739854008c2e6f7c949ce97d02197a1a4adeeff2ebd2e2d8ad4cbfe0e`.
- Route: `d47abc1369d28ee3a5dc35870c6376f3011524105dc50cebd82c3630500b287a`.

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/private-engine-descriptor-worktree-v1`.
Sibling artifacts: `staged-enginecapture-{prepared,actual,synth,route}-v1`.
RAM-backed test scratch: `/dev/shm/starlink-engine-tests.tbmC57`; sources/logs/XML
were captured in the archive above before handoff. No live build remains.
Primary production HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
