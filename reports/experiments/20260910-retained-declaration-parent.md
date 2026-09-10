# Completion declaration corrected; actual run reaches a formatter crash

## Independently verified correction

Parent28041 exits0:155 tests PASS in13.55s. All73 source pins remain unchanged
through the run. The delta from the prior71-source bundle is exactly four
changed files and two added files;67 original sources remain byte-identical.
Runtime changes are only an early `wire completion_accept;` declaration and
replacement of the later `wire completion_accept =` with `assign`. A strict
two-edit inverse restores the complete original runtime SHA256. The entire
logic RHS, reset behavior, guard checks and other RTL remain unchanged.

The other three changed files bind that strict inverse into the exact original
source check and add its helper/test to the transparent bundle inventory. No
other original-source pin is exempted. The new bundle contains actual corrected
source hashes; it does not pretend the runtime retained its old hash.

Test scope:113 existing actual-harness/script tests,31 bundle/runner tests and
11 declaration tests. These include eight rejected source mutations,32768
binary expression combinations plus352 single-control X/Z probes (not all
four-state combinations), and a read-only seven-context scripted witness for
known completion ports and the prior-cycle registered receipt. The independent
parent verifies155 clean XML cases, source-to-bundle hashes, and byte-identical
bench/profile/vectors/compiled list before the vendor call.

FW `946ea9fa747097a5a2730acca93ae39b656cf232`;
HDL `c02fb48b72c4abcb43bc2aab4f7b0d0511ef1b52`.
Runtime SHA256 `2f11bc7e08e907209336775877155839becf45f8015126bd99769c2dccc550d4`.
Manifest SHA256 `cb3bfc9af54809f67c95e20fd642019c1b953f3a51f40bf3a75e3a502eabd583`.

## Actual outcome — incomplete, not PASS

Parent43908 exits1 after29.40s without timeout. Original-source and copied-source
verification both exit0. The compiler warning for completion_accept's implicit
declaration disappears. The unchanged health assertion no longer stops startup:
job1 is admitted at fast cycle934, configuration/reset progression occurs, and
the run reaches the first input record at cycle939/time5362857411fs.

XSim then reports an unrecoverable kernel exception in `/tb/actual_word`.
Its crash stack includes `iki_vlogfile_fwrite` and string ostream formatting.
The log has one job admission and no completed-job markers; no results.json
exists. The strict result checker rejects the incomplete marker inventory.

The CSV contains512 complete `source` rows from literal-string task calls,
followed by a partial `0,` line. The first crashing call uses the conditional
string expression `actual_inverse ? "inputI" : "inputF"` as the automatic
task's string argument. This makes conditional-string formatting a specific
lead, not yet a proven simulator bug mechanism. Next: a tiny literal-versus-
conditional reproducer with the same formatter, before any logging-only
workaround or another full campaign. Do not weaken data/timing comparisons,
replace the FFT, or modify the receiver runtime to accommodate logging.

Passing startup is observed improvement, not completion of FFT numerical,
throughput, physical-timing or60MS/s receiver qualification. No radio/PPU
operation or production HDL gitlink promotion occurred.

## Preserved evidence

- `20260910-retained-declaration-parent.tgz`, SHA256
  `94bb45d95550ea41ec09ed9d218950735ef4d1a0786427c659a864424fe2e2a5`:
  parent155 source snapshot, pins/delta, cases, logs, XML and terminal receipt.
- `20260910-retained-declaration-actual-parent.tgz`, SHA256
  `fc1b862b62760e73e23f70cddb095eb60907f5c4257796e6a78ac4f463b45884`:
  parent-owned actual command/process/terminal, input copies, complete project,
  generated FFT receipts, compiler/simulation/crash logs and partial CSV.

Both tar comparisons exit0. Tool `.Xil` scratch, Python bytecode and test
convenience `*current` links are excluded where applicable. Recovery directories
`retained-declaration-parent.nu4VLvyG` and `retained-actual-declaration-parent.ksMYG4bC`
under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
