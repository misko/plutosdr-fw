# Local first-admission actual equivalence — preparation only

Final new-only offline suite: **121 PASS / 5.89 s**, Ruff PASS. No vendor FFT,
synthesis, placement, routing or receiver execution was launched. The previously
accepted 349-test guard/arithmetic suite was not rerun merely for packaging.

Tested source: FW `5c479ff19740e473501d90353cd0c376bec20d15` /
HDL `e0e075d72711e27a866bdadebc1c14ef19c58326`. The only HDL additions since the
accepted local guard pin `461eda9f` are a test-only observer and its include.
All runtime bytes, original benches, old arithmetic helper and goldens are unchanged.

## Prepared contract

Both bundles are fixed R1/B1/O1 at source100/island175 MHz; L is
LOCAL_FIRST_ADMISSION. L0 is an offline control preparation, not a requested second
vendor execution. The smallest proposed next evaluation is **one L1/175 actual
run**, separately authorized against its exact manifest below.

The new bench is generated using five literal anchors: module rename, default-L
declaration, new-top/L forwarding, observer include, and final observer receipt.
Its strict inverse restores the complete unchanged arithmetic actual bench, whose
existing inverse restores the dec20 original. All original forces, waits,
current/late fault predicates, certificate checks and two 119-bit product monitor
boundaries remain literal. No stimulus is modified to satisfy the observer.

The observer consumes the actual guard's **input ports**, not its derived
eligibility or certificate signals. It instantiates the literal original guard
(module rename only, CHECK_IDENTITY=1/BALANCED=1) and the new guard with the L
parameter deliberately omitted. Every output, all 85 state bits and current
internal predicates form an unmasked 155-bit comparison, checked before/after
both clock edges and asynchronous reset. Actual top/guard L and omitted default0
are checked through hierarchy. Old state-mux/input/result/product shadows remain.

The observer requires positive reset, forward/inverse starts, current/sticky
faults, completed-slot prefetch and duplicate-start observations; it does not seed
those counters. Its read-only diagnostic Tcl adds exactly 14 selected observer
paths, including all three 155-bit vectors, and exclusive closed receipt/inventory
files. Original arithmetic logging and `run all` remain untouched. Script inventory
is **not proof of recorded WDB history**; that must be checked after any later run.

All eight original numeric files are immutable. Acceptance retains the original
11 complete functional terminals, 76 nominal/stalled real-core job records with
config3/input-span513/last-input-to-output781/commit1810 clocks, 19,456 ordered
words per forward/product/inverse stream, and 16,986 output-derived scores.
Scores remain oracle-only, not scorer-RTL evidence. Operand latency remains
four accepted-input-to-bank clocks (3+O); L adds no cycle. The **entire** previous
R1/B1/O1 CSV must match SHA
`e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71`.
There is no shifted trace or fault-observation tolerance.

## Freeze and launch policy

Each final bundle contains 45 frozen files, 19 compiled Verilog/SystemVerilog
sources (eight runtime), and eight numerical vector files. Only three explicitly
loaded standard-library-only Python modules execute: local_admission_actual,
local_admission, bank_arithmetic_actual. No package initializer/import scan or
installed numerical model is needed. The new policy test is frozen too.

Factory SHA remains `0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d`.
The original realtime18-bit generated FFT configuration/port checks remain exact;
synthetic vendor-module definitions are rejected. Whole filename inventory,
hashes, compiled list, runtime inverses and fixed numerical/bounds checks are
verified independently. Aliases and dangling symlinks at destination/source roots,
parents, manifests and frozen directories are rejected before normalization.
The Tcl adapter rejects raw output/runner aliases before its own `file normalize`.

The source-specific runner requires the manifest hash as a third argument,
Vivado2022.2, two threads and an explicit Python executable. All Python children
clear PYTHONHOME/PYTHONPATH/LD_LIBRARY_PATH and use `-B`; parent vendor environment
is preserved. It refuses existing project/start receipts, retains the original
run error and independent after-integrity result, and publishes results.json only
after both succeed. No original failed automation is generically accepted.

The fixed prior v3 candidate manifest, run_outcome and separate post-hoc assessment
are carried as history. Its **automation remains FAIL** solely for the known
diagnostic-marker log-source error, while its separately reviewed full functional,
numerical and WDB assessment remains distinct. New runs use the reviewed exclusive
closed arithmetic diagnostic receipt; old files/results are not rewritten.

Final prepared directories, relative to `hdl/library/starlink_pss_acquisition/build`:

- `local-admission-actual-R1B1O1-L0-175-prepared-v2`, manifest
  `e252c209ae16840929fdad89966757b651374cbc0510ed2c6a1e442c10a2a675`.
- `local-admission-actual-R1B1O1-L1-175-prepared-v2`, manifest
  `a84e723cb3de7b2c3382dbc88b89b6edc533d7493856540d1871d4ecd31831d5`.

Both use frozen runner SHA
`f76090eba45113c44eff258fa1482198b663747787b76b14ce24a39bee7ebb98`.
Neither has a project or launch receipt. The v1 preparations remain preserved,
unlaunched and superseded for the reviewed lexical-path hardening.

## Retained offline attempts

- Original10715: 73 PASS / one policy FAIL, 3.80 s,
  `/tmp/starlink-local-actual-policy-v1.Z5FUcW`. The scanner incorrectly treated
  the comment “No stimulus or force here” as a force statement. The correction
  checks statement starts; no observer predicate or stimulus changed.
- Original64540: 89 PASS / 5.76 s,
  `/tmp/starlink-local-actual-policy-v2.hHzSJq`.
- Original50434: 121 PASS / 5.89 s,
  `/tmp/starlink-local-actual-policy-v3.GPcaXK`.

Exact final command is sanitized repository Python `-B -m pytest
tests/test_starlink_local_admission_actual_policy.py -q`, with retained explicit
basetemp/log/XML. Tests execute guard-only Icarus comparisons and reject 18 genuine
state/output-corruption cases plus invalid/omitted-L binding. Full derived bench
elaboration uses Icarus `-i` with the vendor core absent, **never vvp**: syntax
only. Mock Tcl project/launch/after-integrity tests never call Vivado. Collector
tests use clearly named `MOCK_ONLY_NOT_AN_ACTUAL_RUN` copied old receipts, including
strict missing-terminal, late-error, changed trace/event/IP/wave rejection; these
fixtures are not new actual evidence. All raw attempts and frozen generated test
sources are preserved in the associated archive.

No D/S/CDC union, canonical runtime promotion or physical measurement is included.
Full canonical15/source15/30/60 coarse, native sparse fine, independent2.5MS/s pilot,
.18-before-.17 and eight-target/120ms/300s objectives remain unchanged and open.
