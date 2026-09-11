# Combined private ACK retirement: actual FFT passes, timing remains open

Candidate branch: `codex/starlink-rx-only-do-not-merge-combined-private-ack`.
FW `b2faf19c9`; HDL `96b3c672b73c2eaee81cd146ff82479f4fdaad59`.
Parent is the integrated registered-input/private-descriptor experiment.
**No production promotion or deployment: setup timing still fails.**

## Implemented and tested

The existing private ACK-retirement change is now combined with the actual
512-point FFT, buffers, registered input identity and private descriptor capture.
Only the certified inverse owner opts in. A known fault may clear private ACK
occupancy, but original public ACK rejection and same-edge sticky quarantine
remain. Unknown fault behavior and legacy/forward modes are preserved.

**521 regression tests plus 18 paired-evidence tests pass**. Source-extracted
checks cover 128 transition combinations, 16384 four-state fault cases and
broken-variant rejection. Full source inverses constrain the runtime delta.

Two bounded real-FFT campaigns use the same 36-file prepared inventory:

- Main: **64512 numerical records**, CSV byte-identical to the parent; **500638**
  original-guard public/diagnostic comparisons. Service remains
  **3661/3661/4928/11728/3661/3661 clocks**. The 11728 case includes a deliberate
  9000-clock reader stall, excluded from the unchanged 5215-clock gate.
- Auxiliary: six actual reader-ACK boundary cases, **60721 checks**, **306**
  known-quarantined private differences. Vendor fault, orphan output/status,
  fast/slow reset and healthy release all end with fresh 512 correct reads and
  one real release. Fault-edge public ACK/release remains vetoed.

The main simulation's original 3,000,000 ns deadline is unchanged; extra ACK
cases use a separate bounded simulation top, not an extended deadline. Routing
requires both successful, re-audited, source-matched runs. Missing, failed or
mismatched auxiliary evidence rejects routing, including attempts to hide the
requirement by removing an audit field. These are finite subsystem tests, not
formal proof, RF frame counts or sustained native receiver qualification.

## Measured physical result

Synthesis takes 99.30 s; routing completes in 55.78 s, with verified sources and
checkpoints and unchanged diagnostic clocks/constraints.

| Metric | Descriptor parent | Combined private ACK |
| --- | ---: | ---: |
| WNS (ns) | -1.686 | -1.421 |
| TNS (ns) | -478.515 | -413.225 |
| Failing setup endpoints | 748 | 813 |
| LUTs | 2726 | 2763 |
| Flip-flops | 5667 | 5673 |

Worst slack improves 0.265 ns and total negative slack improves 65.290 ns, but
65 more endpoints fail. Retained guard facts still have better worst slack
(-1.340 ns), though worse TNS (-463.636 ns). No overall best-reference claim.

All 8335 nets route with zero routing errors. Hold is +0.062 ns and pulse width
+1.830 ns, with no failures. Resources include 21 DSPs and 15 RAMB18s. The OOC
build has 114 unconstrained inputs and 124 outputs; it is not board signoff.

The worst path now runs from inverse guard `fault_reasons_reg[1]` to the
scheduler's `forward_committed` register: ten logic levels, 7.083 ns data delay,
including 5.387 ns routing (76.1%). Shared fault/admission qualification still
feeds the forward-completion token. Removing more TX logic does not address
this isolated dependency.

## Next bounded step

Investigate a registered **qualified forward-completion receipt**. The guard
already registers `commit_pulse <= final_commit`; using local registered
evidence is a candidate, not a proved replacement. `forward_committed` controls
both product publication and mailbox readiness. Simply delaying it can leave
kernel readiness selected for an extra cycle while the guard awaits ACK,
potentially acknowledging before the product bank is actually ready.

Specify and test the entire transition: retain status/exponent/final-input
qualification, hold ACK until actual product ownership, preserve current/sticky
fault veto and cancel receipts on reset. Test faults and resets on both sides
of the new register, held LAST/status delay, downstream stalls, no early
publication/ACK, fresh recovery and the unchanged service budget. Then repeat
actual FFT numerical checks and routing. No next-boundary RTL is implemented
in this checkpoint.

Native 60 MS/s fine search and independent 2.5 MS/s inspection remain unchanged.
Full receiver timing/CDC/reset/board-clock checks, actual 60 MS/s RX calibration
and sustained Ethernet/IIO qualification remain before reversible `.18` canary
and `.17` PPU Ethernet-only deployment with pinned rollback. Final acceptance
still requires 300-second scanning, 120 ms valid dwells and blind host GLRT.
No radios, PPU/main or primary production HDL were changed.

## Preserved evidence

[Read-back verified archive](20260911-staged-ackcombined-evidence.tgz) and
[receipt](20260911-staged-ackcombined-evidence.json): **16134995 bytes, 7657
members**, every member SHA-verified; archive SHA256:
`afbc76a605af0b9c16bda45e46cef498eac793b8dbb342023f39d6bccd71fdd9`.

- Prepared: `ecb302eab62a44de27a6b27d4d0414effe487e270498d2adb1ec83f79d01a38a`.
- CSV: `44fae7467811a9e0f71d63330ee5c868c676c9a4c0ffb29f6f649be23e003279`.
- Synthesis: `aabad4bdf77a144490b67108ae81e68cf546d804f16abc784fe845b4ce632dc9`.
- Route: `7705d40e93b31778cd166ea5f9957d3e4bbcfa1198a931aeca65b53157b38251`.

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/combined-private-ack-worktree-v1`.
Sibling artifacts: `staged-ackcombined-{prepared,actual,aux,synth,route}-v1`.
Test scratch `/dev/shm/starlink-combined-ack.ECDcHL` is captured in the archive.
All build/test processes are terminal. Primary production HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
