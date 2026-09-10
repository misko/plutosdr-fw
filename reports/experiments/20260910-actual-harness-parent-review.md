# Retained-output actual-FFT preparation: independent offline harness gate

Parent original53417 exits0: **112 PASS in8.33s**, all66 captured source files
unchanged. A fresh seven-context scripted composition and its malformed-record
controls pass. The previously identified timestamp-checker gap is independently
closed. This is **OFFLINE_SCRIPT_NOT_FFT**, not vendor simulation, FPGA routing,
continuous receiver, native timing accuracy, IIO or radio qualification.

## Independent execution and review

Parent read the complete derivation helper, physical-interface witness,
seven-context scheduler, result checker and test suite. It reviewed the added
clock-pause observations and event joins against the preserved first draft.
Original46 sources, original arithmetic/input/retirement witnesses and numerical
vectors remain pinned; input/output numerical tolerances were not relaxed.
The script-only output-padding adapter has a whole-source inverse and is
explicitly excluded from the actual-core compiled profile.

The fresh parent result contains40 admissions,38 completed transforms and two
aborted forward prefixes of64/65 physical samples, across seven contexts. Its
independent inventory audit checks77953 numerical records:10752 source,
9857 forward inputs,9728 each inverse-input/forward-output/product/inverse-output/
private-inverse, and8704 slow reads. It separately joins all19456 raw FFT rows
to their recorded job and exact output cycle. Each complete transform retains
the declared1810-clock publication boundary and781-clock last-input→first-output
service. These are scripted model measurements, not actual FFT measurements.

The112 tests cover original-reference/ABI/recipe mutations, entire-bench inverse,
missing/duplicate or corrupted event receipts, mixed-case failure diagnostics,
all eight numerical stream classes, padding, identities, clocks and aborted
prefixes. The parent independently checked XML112 with no skip/error/failure,
the66 copied source pins, raw simulation status and complete stream inventory.

Exact final test SHA256:
`27b494b05575ebcae0dcacaac540796bf9e75e349381027528ed50d3d61d375d`.
Helper SHA256:
`c0837d8ba20886582dfd0a718d88a8c5e65d2422da250f5bb213546dc8695768`.
Result checker SHA256:
`679a1f4ef3971f40b8a01b67e06eac879d3a49b0f7ea7f5beaf53d0ef1e59f74`.

## Separate counterexample closure

Parent replays the saved `script-v2` data with the corrected checker:

- Untouched77953 records: accepted.
- Original first-output timestamp shifted one fast cycle: rejected by the
  independent slow-edge coordinate check.
- Original impossible slow counter: rejected by the same check.
- Stronger shifted timestamp with its slow counter changed consistently:
  rejected specifically by the raw-output row/job-ordinal time join.

No checker code changed during these probes. The first parent probe exits1
because its expected rejection label was too specific: the malformed timestamp
was correctly rejected at the earlier clock check. Its full outcome remains.
The second probe adds the consistent-clock counterexample and exits0, preserving
the exact original two mutations too. The earlier defective parser's acceptance
records remain in the previous report; they are not relabeled as passing tests.

## Portable evidence and next step

Fresh112 archive `20260910-actual-harness-parent.tgz`:28099644 bytes, SHA256
`61111c46fc84b9e271b542b718789a8318880a991bec254709dd31322dbfa647`.
Includes66-source snapshot, fresh bench/VVP/log/CSV, all test mutation evidence,
XML and independent inventory audit; pytest current symlinks excluded.
XML SHA256:
`b583bf8485f12e8534d412af6f1c264f5019c0c36c2c9ee92bf3effa00b0afa0`.
Audit SHA256:
`aa5812911da396be16558639947ef58facb4d49c35cf5804a752feacd011bcee`.

Counterexample archive `20260910-actual-ledger-corrected-parent.tgz`:11155127
bytes, SHA256
`6a91dbddae8e1958d147e706ce2155fd9d656e6cd6382577889162df14353ac0`.
Includes both probes, exact helper snapshots, complete original/modified CSVs
and receipts. Both archive comparisons exit0. Recovery directories:
`actual-harness-parent.DCDxaJHf` and `actual-ledger-corrected-parent.ZkCVHbAf`
under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

Remaining before actual-core launch: finalize/test the closed source bundle,
standalone CLI and one-shot runner, freeze their exact source manifest and
execution command, then review them for the source-specific vendor run. Parent
caught a launch dependency issue before execution: the normal venv Python is a
symlink, but resolving it loses NumPy imported by the unrelated package init.
The additive standalone CLI is being tested with an isolated stdlib import path
and the resolved interpreter; original package sources remain unchanged.

No vendor process or radio was started in this gate. The parallel P1 controller
integration, full receiver routing/calibration, causal coarse/native fine path,
2.5MS/s IIO evidence and `.18`→`.17` deployment remain required.
