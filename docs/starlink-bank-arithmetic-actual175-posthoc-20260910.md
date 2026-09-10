# Bank arithmetic actual175: functional assessment and preserved automation failures

**Both complete HDL functional suites pass post-hoc verification. Both original
automation runs remain EXIT1/FAIL.** No simulation was repeated to repair the
logging receipt, and neither original `results.json` was created.

## Original actual executions and classification

Source FW`deb023b36b2780bd25aa5257eee52d905a662174`,
HDL`18aa1b6f58fe7abcf06672fccf6d93551174de54`; immutable actual generated18-bit FFT,
175MHz, R1/B0/O0 baseline and R1/B1/O1 candidate. R is registered scheduling,
B is boundary rounding, and O is the operand register.

| Arm | Original handle | Vivado terminal UTC | Original outcome |
|---|---|---|---|
| baseline | 65522 | 09:27:00 | run_status1 / after_status0 |
| candidate | 58122 | 09:26:54 | run_status1 / after_status0 |

Both benches reached all 11 required functional terminal markers, including the
full original control/fault suite and new arithmetic marker. The automation
then rejected the diagnostic marker because Tcl `puts` appeared in the outer
Vivado log but not the HDL-only `simulate.log`. The 111/115 signal inventories
were valid. Original raw files and failure outcomes were frozen before further
assessment and remain unchanged. Earlier epoch14-failing actual-v2 evidence
also remains failed and preserved; it is not relabeled by these later results.

## Separate read-only post-hoc assessment

The original frozen helper was used without edits. Its complete functional
parser, event oracle, and timing rules verify both runs:

- All 44 frozen inputs, manifest/preflight/postflight and generated-IP
  before/after/live identities match.
- All 76 nominal/stalled FFT jobs retain config 3, input span 513,
  last-input-to-first-output 781, and admission-to-commit 1810 clocks.
- Each stream contains 19,456 exact ordered forward/product/inverse words,
  including independent positions, start indices, exponents, and TLAST checks.
- Each run yields 16,986 exact output-derived sample scores: **oracle-only**,
  not scorer-RTL evidence. The provisional 130-word fault prefix stays provisional.
- Baseline's complete historical CSV matches SHA256
  `25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`.
- Observed maximum nominal forward intervals are 4548 baseline and 4549 candidate
  clocks. These observations do not establish a guaranteed continuous-source
  or full-receiver throughput bound.

The frozen diagnostic parser passes when explicitly given the original outer
logs, each with its single marker at line448. Their SHA256 identities are
baseline`1be6604273852b95b0f900cc7e10470612dcd517ab8e43ac72b38c3e2b70268d`
and candidate`3a8037b2e7b9fbcfb1f3b86b2884d76a10db33e57634e7eff957c5fd482dc033`.
This separate assessment does not claim that the original runner succeeded.

Read-only Vivado WDB queries verified actual histories for all 111/115 paths at
three fixed times (333/345 values). All were non-Blank; WDB and inventory hashes
were unchanged. Six qualified 119-bit comparisons per arm equal independently
reassembled reference fields. At the original epoch14 failure times, all four
monitor vectors equal`600ba0066440280000000800380000`; external/wrapper overflow
is1, inner/reference overflow is0, current fault is1, and product commit and
handoff ACK are both vetoed. Thus the intended monitor boundary and still-live
transport fault are directly observed in the actual bank simulation.

Raw queries, scripts, and `posthoc_assessment.json` are retained under
`hdl/library/starlink_pss_acquisition/build/bank-arithmetic-monitor-actual-assessment-v1.OsPugx`
and in the additive evidence archive. Parent independently repeated these
functional/source/WDB checks.

## Portable preservation

The complete original archive is 241,304,017 bytes with 341 safe unique files,
SHA256`470f5a8c81ca725d77efcdbbe8bd506a2b02921d9be88ac40602eb5c0304848e`.
The local monolithic file is retained and exactly ignored, not committed.
Six tracked parts are at most 40 MiB each. Their ordered size/hash manifest is
`reports/experiments/20260910-bank-arithmetic-monitor-actual175-originals-v3.parts.json`
(SHA`9fcadecb63d073c1ab362e832ed93f00974ed8eb45a3fb11b71d4d91c1a924ec`).
The original 341-member inventory remains in the adjacent `.json` receipt.

Reconstruct into a new absent directory using
`tools/starlink_reconstruct_archive_parts.py --manifest <parts.json> --output-dir <new-dir>`.
The helper validates ordered filenames, indices, sizes, per-part and whole
hashes, and refuses overwrites. Independent reconstruction tests also reread
and verify every safe archive member. No extraction is required.

## Future-only receipt fix and offline gate

Source FW`94c6fda9a87a9f7eb4ddcd3de1e85b6600f6b7bf`,
HDL`8bbfee6ebb1d77b58b33080e8a58bdcca978fd28`. Only the diagnostic Tcl changes in
HDL: five added/one removed lines write the same marker to an exclusive closed
receipt file before `run all`. The collector reads that explicit receipt plus
the inventory, rejecting missing/duplicate/malformed/late-error content.
All runtime, bench, checker, stimulus, numeric and clock bytes remain those
actually simulated. This receipt fix itself has **offline**, not actual-run,
qualification.

The final offline gate passes 246 tests in 25.23 s and Ruff, including the unchanged
226 tests, nine new receipt tests, and eleven archive-part tests. Raw evidence is
at `/tmp/starlink-bank-arithmetic-receipt-offline-v2.kxP9Lj`. The earlier 246-pass
attempt and two Ruff import-order failures/source snapshot are preserved.
Future 44-file v4 preparations are frozen but unlaunched (baseline manifest
`1177f40e2ad24f34b29899e82bf93faca4915c2dcb68ded4f4cc8f27cde58d49`, candidate
`92264c2eb55d267e715f6553f4ed7654ab1020fe43fdb4340379e7397a851a06`).

The additive assessment/test/future-source archive
`reports/experiments/20260910-bank-arithmetic-monitor-posthoc-evidence-v1.tgz`
has 9,644 safe unique files, 47,001,765 bytes, SHA256
`bac2e967d91fa4e5a348084c049bbb6387e24bd3f40a55ebeaa48329f8683468`.
All member hashes were reread and verified. Byte-identical reconstructed 241 MB
test outputs are retained locally and explicitly listed as duplicate exclusions;
their bytes are already preserved by the six portable parts.

No arithmetic physical run, full receiver, scorer RTL, RF accuracy, or deployment
qualification follows. Continuous canonical15MS/s coarse at source15/30/60,
original-rate native fine, independent2.5MS/s pilot, .18 before .17, and eventual
eight-target120ms/300s operation remain the full objective.
