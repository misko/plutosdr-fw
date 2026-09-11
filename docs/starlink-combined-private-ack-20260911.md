# Combined private ACK retirement — DO NOT MERGE experiment

Parent descriptor/input-stage runtime: FW `9edd8c9439b0fd45359c077772f0e89012e72106`,
HDL `fc16f21aa8a62fe48e9d7f2889f6fc0f4a820be8`. Candidate branch:
`codex/starlink-rx-only-do-not-merge-combined-private-ack`.

## Recombined runtime and safety contract

Apply the exact guard delta from the earlier private-ACK alternate
`470eae1919e1ebaab2b5b3af7e05a3a9137af375`; its pre-change guard matches this
parent byte-for-byte. Enable it only for the certified inverse owner. Private
`awaiting_ack` may clear on a known current fault, while original public ACK
rejection and same-edge sticky fault accounting remain intact. Unknown fault
behavior and disabled-mode transitions retain the original conditional behavior.
Private occupancy clearing is not reader acknowledgment or bank reuse authority.

Only the top's opt-in parameter and this guard change at runtime. Full source
inverses cover both. Current registered-input and private-descriptor changes
are retained; their historical inverses and current predicate tests remain.
The unrestricted idle-fault accounting prerequisite is tested. The legacy
mode and forward owner are not opted into private ACK retirement.

## Two bounded actual-FFT campaigns

The existing full main campaign remains intact, including its 3,000,000 ns
deadline and 5215-clock service gate. ACK-specific fault/reset cases run in a
separate simulation top using the exact same prepared runtime, vectors and
generated FFT. This avoids extending or weakening the main campaign's deadline.
A complete bench inverse verifies that all original main assertions/cases remain.
The auxiliary top has the same bounded deadline; it does not claim the main
campaign's seven-stream numerical inventory.

The routing driver requires both successful source-bound outcomes, identical
prepared roots and inventory digests, and fresh re-audits of both logs. The
compiled bench identifies the auxiliary requirement: deleting a JSON audit
field cannot bypass it. Both auxiliary outcome and log are hashed before and
after routing. A missing, failed or mismatched auxiliary run rejects routing.

## Verification results

25 focused tests pass in 10.61 s. Reused source-extracted tests cover 128 ACK
transition combinations, including the one intended known-fault private clear,
and 16384 four-state idle-fault combinations using the actual guard. Mutants
reject unconditional unknown clearing, missing fallback/private clear, omitted
external fault accounting and an incompatible phase-fault mode.

The full regression passes **521 tests in 75.27 s**, no failures/errors/skips.
Final paired-evidence tests pass **18 cases in 0.19 s**. An earlier partial
audit invocation passed 16 cases with its main-dependent test deselected; the
final 18-case invocation supersedes that partial coverage, not an extra count.

- Main actual FFT: **197.31 s**, all **64512 numerical records** and CSV exact
  to the parent. Original inverse-guard public/diagnostic outputs match over
  **500638 checked cycles**. Service remains
  **3661/3661/4928/11728/3661/3661 clocks**. The 11728 case includes the deliberate
  9000-clock reader stall, excluded from the unchanged service gate.
- Auxiliary actual FFT: **42.41 s**, all six reader-ACK edge cases pass: vendor
  fault, orphan output, orphan status, fast reset, slow reset and healthy release.
  Public/diagnostic outputs match over **60721 checks**. All **306** private
  occupancy differences are known-quarantined. Faulted public release is vetoed;
  every case finishes with fresh 512 correct reads and one actual release.
- Synthesis: **99.30 s**, source receipts unchanged. Synthesis DCP:
  `aabad4bdf77a144490b67108ae81e68cf546d804f16abc784fe845b4ce632dc9`.

Prepared inventory (36 files):
`ecb302eab62a44de27a6b27d4d0414effe487e270498d2adb1ec83f79d01a38a`.
Numerical CSV:
`44fae7467811a9e0f71d63330ee5c868c676c9a4c0ffb29f6f649be23e003279`.
These are finite component/subsystem observations, not RTL formal proof, RF frame
counts or continuous native receiver qualification.

## Physical comparison and end-state gates

Routing completes in **55.78 s** with unchanged sources/constraints and verified
checkpoints. **Setup still fails: -1.421 ns WNS / -413.225 ns TNS / 813 of 13811
endpoints**. All 8335 nets route with zero routing errors. Hold is +0.062 ns and
pulse width +1.830 ns, with no failures. Resources: 2763 LUTs, 5673 flip-flops,
21 DSPs, 15 RAMB18s and no RAMB36s. Routed DCP:
`7705d40e93b31778cd166ea5f9957d3e4bbcfa1198a931aeca65b53157b38251`.

Compared with the descriptor parent (-1.686 / -478.515 / 748), worst slack
improves 0.265 ns and total negative slack improves 65.290 ns, but there are
65 more failing endpoints. Compared with retained guard facts (-1.340 /
-463.636 / 821), worst slack remains 0.081 ns worse. This is a mixed result,
not an overall best reference or permission to deploy.

The new worst path is inverse `fault_reasons_reg[1]` to registered scheduler
`forward_committed`: ten logic levels, 7.083 ns data delay, including 5.387 ns
routing (76.1%). It crosses ACK/admission, job-start/input-fault and qualified
forward-completion logic. The private ACK change moved the worst path; it did
not remove the shared fault-control dependency.

The next investigation is the **forward completion receipt boundary**, not a
raw LAST shortcut. `forward_committed` authorizes product-bank publication and
changes mailbox readiness; setting it early can authorize incomplete data or
deadlock the handoff. Any candidate must retain final status/exponent checks,
certified final input, current/sticky fault veto, actual bank ownership and
reset cancellation. Prove a local registered completion receipt first, then
re-run actual FFT numerical/service, boundary-fault tests and physical routing.
No such next candidate is implemented here.

The diagnostic OOC build still has 114 unconstrained inputs and 124 outputs;
it is not full receiver or board timing signoff.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
untouched. Full receiver timing/CDC/reset/board clocks, sustained capture, actual
60 MS/s RX calibration and Ethernet/IIO qualification are still required before
reversible `.18` canary and `.17` PPU Ethernet-only deployment with pinned rollback.
Final gate remains 300-second scanning, 120 ms valid dwells and blind host GLRT.
No radios, PPU/main or primary production HDL changes in this experiment.

## Evidence locations

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/combined-private-ack-worktree-v1`.
Sibling artifacts: `staged-ackcombined-{prepared,actual,aux,synth,route}-v1`.
RAM-backed test scratch: `/dev/shm/starlink-combined-ack.ECDcHL`; preserve its
sources/logs/XML in the curated package with explicit `--test-root` before handoff.
