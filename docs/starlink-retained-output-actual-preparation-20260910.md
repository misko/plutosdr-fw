# Retained-output actual-FFT preparation and compile-language correction

This report freezes additive preparation, not an actual FFT PASS. The parent
owns vendor execution and its separate receipts. This lane has launched no
vendor process. The original 46-file retained-output prototype, all eight
goldens, arithmetic, bench stimulus, clocks and acceptance budgets are unchanged.

## Source and bundle identities

| Cut | FW | HDL | External bundle manifest SHA256 |
| --- | --- | --- | --- |
| Reviewed 138-test preparation | `36338495cedfe8b4579dfa9d02553e64b865cfc7` | `c095c1dfba7201e7da335fd5d32d9b0cf66ad6e3` | `e524c0ba1b3f4ac0135d58a891ee3dc4b7fbe37b338f4797032159072b8311fc` |
| Runner language correction, 31 targeted tests | `2f8a57fb6295a4ea3559e60e27a8033010846040` | `ac357cf1e954604e110ef27a654e14960c41ae7a` | `3a0eb7872722b65764178c813ec96946e61ce0ac226c0202ea0a70d24e559eeb` |

All external paths below are beneath
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Original bundle: `retained-output-actual-prelaunch-v1`; corrected bundle:
`retained-output-actual-prelaunch-language-v2`. Both contain 71 frozen sources,
74 file receipts and their external-hash-bound manifest (75 regular files).
The original source signature is
`4a2210fe004dba4e20b828eda1f62fe9fe04a8324a3baaf669e95cb5ef870c33`;
the corrected signature is
`a7e6016bdc950b8324ad2c12c6e95dc708ee0a668a7351d814dd5178f388a91b`.

The closure is the original 46 sources, 13 original-reference/manifest files and
12 additive preparation files. It includes the recipe, documented output ABI,
two tests, parser/helpers, CLI, runner, context and witness. Each source receipt
joins the actual snapshot file; a self-consistent but disconnected source
signature is rejected. The expanded bench, profile and environment are separately
hashed. Exact original-body/binding inverses are checked before preparation.

Only two source receipts differ between bundles: the Tcl runner and its bundle
test. The other 69 sources, expanded bench, profile and environment byte-match.
The original bundle remains intact; its old live-source verification must not be
misrepresented after these two intentional live changes.

## Executed offline evidence

| Attempt | Original terminal | Evidence directory | Classification |
| --- | --- | --- | --- |
| Draft full preparation | 16891: exit 1, 133 PASS / 1 FAIL | `retained-actual-gate.dwywUQMK` | Test setup `StopIteration`: zero-byte-file mutant assumed a file absent from the closed inventory; no RTL failure |
| Final preparation | 62296: exit 0, 138 PASS, 9.07 s | `retained-actual-final.2VAeyjCJ` | 113 actual-harness/script/parser tests plus 25 bundle/CLI/Tcl-stub tests |
| Parent independent final repeat | 70316: exit 0, 138 PASS, 9.04 s | Parent-owned evidence | All 71 sources unchanged; independent frozen CLI/bundle audit PASS |
| Language-only correction | Tool chunk `496690`: exit 0, 31 PASS, 0.78 s | `retained-actual-language-tests.7tqwIaNj` | Original 25 bundle tests plus six exact compile-plan controls; no vendor |

The final full command was Python `-B -m pytest -q -p no:cacheprovider` with
`tests/test_starlink_retained_output_actual.py` and
`tests/test_starlink_retained_output_actual_bundle.py`, a unique retained
`--basetemp` and `--junitxml`; the language replay uses only the latter file.
`TMPDIR` and outputs were in their named recovery directories; PYTHONHOME,
PYTHONPATH, PYTHONOPTIMIZE and LD_LIBRARY_PATH were cleared. The test interpreter
was `/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python`.
No unchanged 113-test harness replay is claimed for the language-only change.
Ruff F/E9 passed for the edited test source.

The complete scripted witness emits 77,953 numerical rows and explicit
`OFFLINE_SCRIPT_NOT_FFT` status. Its raw input, arithmetic, retirement, two
unchanged guard shadows, reset prefixes and seven context receipts are checked.
Those rows are not generated FFT evidence. Original compile-only/script-v1 and
corrected script-v2 attempts remain in `retained-actual-preparation-v1`.

Parent parser-only counterexamples exposed a real receipt gap: a first-raw
timestamp shift on the valid clock grid, or an arbitrary slow-counter change,
passed the earlier parser. The correction independently reconstructs actual
slow edges, including the two pause/resume intervals, and joins each numerical
row to its job, ordinal and exact event time. Parent independently rejected
both original mutants and an additional clock shift with a consistent slow
counter. Originals remain in `actual-ledger-time-parent.dqaOlckA`; corrected
checks remain in `actual-ledger-corrected-parent.ZkCVHbAf`. These are parser-only
findings, not vendor or RTL failures.

## Parent-owned first vendor attempt and narrow correction

Parent process 49345 ended with exit 1 after 18.02 s at
`retained-actual-parent.G1rTdLfN`. Simulation did not run: Vivado treated a `.v`
wrapper as Verilog and rejected its unchanged SystemVerilog `island(.*)` syntax.
Original/copied-source checks and generated-IP before/after checks passed.
The full project, logs, original exit and source receipts remain parent-owned.
This failure is preserved; neither launcher progress nor successful IP generation
is called a simulation PASS.

The approved runner-only correction marks each exact `.v`/`.sv` entry from
`compiled_names` as SystemVerilog in `sim_1`, matching prior Icarus `-g2012`.
There are 27 entries, including the expanded bench. Generated FFT VHDL/IP and
eight memory files are not selected. Unexpected compiled extensions reject.
Executed Tcl stubs record all 27 actual selections; missing assignment, wildcard
scope, wrong language, omitted bench and an injected generated-VHDL entry reject.
Create/launch failures and copied-source corruption still preserve after-checks
and never manufacture `results.json`. No vendor is called by these tests.

Corrected runner SHA256:
`7867e76a88c833996f99c881d5065b3a86877bd02c0838c307524de3fe926d38`.
Corrected bundle-test SHA256:
`36ef44f70887ab61c4ae366fd22efa6f4a01ac69b780aa82810f27f8ba75805d`.

## Actual acceptance prepared, not weakened

The fixed contexts are H0/H1/H2/H4/H5/R1/R2 at ideal fast/slow half-periods
2,857,143/5,000,000 fs, slow offset 1,300,000 fs. Every actual 48-bit input is
zero-padded exactly as the DUT constructs it. The original two signed 18-bit
output-lane arithmetic checks remain; all output bits are logged, with byte-lane
sign extension and TUSER zero extension bound to the frozen PG109 ABI contract.

The recipe requires 21 F and 19 I admissions, 19 complete pairs, two aborted F
prefixes, 10,752 source words, 9,728 each F/product/private-I words, 8,704 real
slow reads, 19,456 raw outputs and 38 statuses. Exactly 1,024 unread old inverse
words are discarded only by the two common resets. All visible aborted inputs
are checked, not excluded by an expected-fault flag.

Timing remains event-indexed: configuration +3, complete-input span 513,
last input to first raw +781, raw last +1,809, qualified publication +1,810,
status at raw ordinal 2. Limits remain 1,500,000 fast clocks overall, 25,000
drain, 8,192 active watchdog and 20 healthy post-drain clocks. Reset requires
at least two sampled core cycles and the existing additional quiet observation.
The earlier 24+32 injected-fault intervals remain separate and are not covered
by this seven-context actual campaign.

The source-ready-conditional dispatch target is eight fast clocks; nominal
3,645 recurrence is not a continuous-rate claim. Real retained-reader stalls,
actual ACK, final-prefetch ownership, common-reset purge and all descriptor
identities remain mandatory. No blanket CSV shift or nominal average substitutes
for each absolute/event-indexed service check.

## Runner and ownership boundary

The frozen standalone CLI works from `/` with unoptimized Python 3.11.16 at
`/home/mouse9911/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11`,
binary SHA256 `2874a0b9344d06b7767aebb1e6e25a759ffcbdb544e99400ecc74dc6092d1174`.
It avoids unrelated NumPy imports via fixed package namespaces, without changing
the old package initializer. The runner pins this nonsymlink interpreter, uses
Vivado 2022.2 and two threads, sanitizes only Python child environments, and
requires an explicit external manifest digest and absent one-shot output.
The vendor launcher needs the installed SuSE library path; it is not passed to
the verifier subprocess. Source/copy/generated-IP after-checks run on Tcl failure
as well as success. Only strict results plus genuine terminal evidence qualify.

The parent exclusively owns subsequent actual authorization and processes.
This lane performed no push and no vendor, physical, radio or PPU operation.
The same FFT, DSP and three payload banks are retained. This island test has
burst-available overlapping windows, not continuous canonical15/native60 input,
full production maps, native/PIL1 pairing, lower-clock closure or RF accuracy.
No union with inverse-sealed, P1, K/M or C1 variants is implied.
