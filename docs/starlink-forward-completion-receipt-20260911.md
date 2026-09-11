# Registered forward completion receipt — DO NOT MERGE experiment

Parent FW `b2faf19c92eff096ab49dbe9deb5ff12e6e07fa2`, HDL
`96b3c672b73c2eaee81cd146ff82479f4fdaad59`. Branch:
`codex/starlink-rx-only-do-not-merge-forward-completion-receipt`.

## Runtime boundary

The certified registered scheduler now updates its persistent forward-completion
token from the guard's existing registered `commit_pulse`, instead of the long
combinational final-commit qualification path. The guard still registers exactly
`final_commit = mailbox_commit_valid && mailbox_input_ready`. All input, final
status/exponent, ownership and same-edge fault qualification remain unchanged.
No raw LAST or speculative completion becomes authority.

Delaying the token alone would be unsafe: for one cycle the guard awaits ACK,
but the old readiness mux would still select kernel-input readiness. Therefore
`forward_receipt_wait = forward_committed || (CERTIFIED_ADMISSION && guard_commit[0])`
selects actual product-bank readiness during that receipt cycle too. The same
selection is used at both the guard and top-level destination interface.

The receipt pulse alone does not authorize product publication. The persistent
token retains the original current/sticky fault veto at the bank. Reset cancels
the guard pulse and token; the bank's existing reset domain immediately prevents
new writes/publication. Non-certified and original scheduler behavior retain
their existing completion predicates. Only the top module changes at runtime;
the other 18 compiled runtime files are unchanged.

This adds no register or clock domain. The persistent token updates one cycle
later, while measured complete FFT service intervals are unchanged. It is not a
claim of continuous native receiver throughput or full receiver timing closure.

## Verification

The first focused invocation stopped at test collection because of an incorrect
Python test-module import. The import was fixed, with no RTL change: V2 passed
20 focused cases. V3 passed the six dedicated receipt tests after removing
redundant known-control histories from that model. The preserved XML includes
the initial collection failure; it is not counted as successful coverage.

**545 regression tests pass in 76.74 s**, including complete source inverses,
known completion transitions, known/X/Z product readiness, raw-LAST rejection,
publication-subset and ACK-interlock checks. Four unsafe variants are rejected:
missing ACK interlock, raw-LAST authority, missing receipt and lost fallback.
These are finite tests, not general four-state or RTL formal equivalence.

**14 new evidence tests pass in 0.50 s**, including complete bench inverse,
same-source actual campaigns, missing/altered coverage and attempts to remove
required main/auxiliary audit fields. **Seven shared archive-writer tests pass
in 0.02 s**, covering byte read-back, unsafe member names, symlinks, missing
sources and no-overwrite behavior. Total: 566 distinct tests in these suites.

Actual generated FFT, main campaign: **199.29 s**, all **64512 indexed numerical
results** exact to the frozen reference. Service:
**3661/3661/4928/11728/3661/3661 clocks**. The deliberately stalled reader adds
9000 clocks to the 11728 case, excluded from the unchanged 5215-clock gate.
The CSV file hash changes due to four differently ordered row positions; an
independent sorted-record comparison confirms identical multisets and headers.
No indexed numerical value changes. All original main assertions/cases and the
3,000,000 ns deadline remain.

The original immediate-token witness checks **500638 cycles**, observing **98**
one-cycle receipt windows. ACK-wait selection is exact; publication authority
never expands. Original inverse-ACK public/diagnostic comparisons also pass.

Actual generated FFT, auxiliary: **77.84 s**, including the original six ACK
cases and **12 new forward receipt cases**. Fault, fast reset, slow reset and
healthy continuation are exercised before qualified completion, during the
registered receipt, and after persistent-token capture. Every case finishes
with 512 correct reads and one real release. Fault/reset cases check no stale
publication or ACK before fresh recovery. The witness checks **151827 cycles**
and **29** one-cycle receipt windows. The original six-case ACK receipt reports
60721 checks and 306 known-quarantined private differences before the new cases;
its comparison monitor remains active throughout the auxiliary run.

Synthesis completes in **98.39 s**. Both actual FFT runs and synthesis use the
same 36-file prepared inventory and unchanged source receipts. Routing requires
both re-audited numerical/ACK/forward-receipt proofs, not just a simulation exit.

## Physical result

Routing completes in **45.71 s**, source/checkpoint verified, with zero routing
errors across 8261 nets. **Setup still fails: -1.567 ns WNS / -497.191 ns TNS /
681 of 13792 endpoints**. Hold is +0.082 ns and pulse width +1.830 ns, no failures.
Resources: 2716 LUTs, 5665 flip-flops, 21 DSPs, 15 RAMB18s and no RAMB36s.

Versus parent -1.421 / -413.225 / 813, there are 132 fewer failing endpoints,
47 fewer LUTs and eight fewer flip-flops, but worst slack is 0.146 ns worse and
TNS is 83.966 ns worse. Retain as a tested alternate; do not promote as a better
overall reference or deploy. No clock relaxation or timing exceptions changed.

The worst path is now product arithmetic `output_block_start_index_reg[61]`
through the product-bank metadata/framing check and shared fault logic to
forward guard `awaiting_ack_reg/D`: nine logic levels and 7.226 ns data delay.
The next path reaches the joiner's kernel-ROM output-valid register through
the same product identity/fault logic. The registered receipt removes one
control dependency but leaves this wide validation feedback path.

Next investigate a **product-buffer input validation boundary**, holding data
and a checked identity/framing result together before public retirement or
publication. Do not merely delay the global fault bit: a bad final word must
remain unpublished, same-edge reset must cancel the private slot, and stalls
must conserve all 512 product words. Compare this against removing redundant
per-beat metadata transport only if descriptor/epoch ownership and corruption
checks can be proved equivalent. No such next RTL is implemented here.

The diagnostic OOC build still has 114 unconstrained inputs and 124 outputs.
It is not full receiver or board timing signoff.

## Scope and deployment gates

Native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection remain
unchanged. Full receiver timing/CDC/reset/board clocks, actual 60 MS/s RX
calibration and sustained Ethernet/IIO qualification remain open. Only after
those gates: reversible `.18` canary, then `.17` PPU Ethernet-only deployment
with pinned rollback. Final acceptance remains 300-second scans, 120 ms valid
dwells and blind host GLRT comparison. No radios, PPU/main or primary production
HDL were changed by this experiment.

## Evidence and reproduction

RAM-backed artifact root: `/dev/shm/starlink-forward-receipt.7z0zKX`.
Prepared inventory:
`0d222aa4968145b0026ac4e8c9288c9b1ad5fc9f8f9b1bdd07a6d3eda4f1af8b`.
Numerical CSV:
`b515f6f4146e28db877474891ed9cebdfa533e8f98bf8c6eb4754afe60bf273d`.
Synthesis DCP:
`ba880cbe1bcabbfc8eb0d6bdf9e16db4119ca13fd34e2aebb4e157fa2082f648`.
Routed DCP:
`b353c34642db403990d06908531052c92386c508d78181da4fa273c9dbaa7653`.

`tools/package_forward_receipt_evidence.py ARTIFACT_ROOT OUTPUT.tgz` preserves
frozen runtime/vectors, both simulations, synthesis/route reports/checkpoints,
source tests, generated test sources/logs/XML and this document. The shared
archive writer verifies every member after read-back. Historical regression
fixtures remain an explicit dependency on the already-pushed parent archive
`20260911-staged-ackcombined-evidence.tgz`, SHA256
`afbc76a605af0b9c16bda45e46cef498eac793b8dbb342023f39d6bccd71fdd9`;
the new archive records its receipt rather than duplicating the archive.

Set `STARLINK_RECEIPT_EVIDENCE` to a relocated artifact root for the new evidence
tests. Historical tests retain their existing pinned recovery-root references.
This packet is not advertised as a standalone reconstruction of all historical
fixtures. No FPGA deployment eligibility follows from packaging success.
