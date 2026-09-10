# Retained-output actual gate: preparation passes, first vendor compile fails

The first actual vendor invocation, parent original49345, exits1 after18.02s.
It stops during HDL compilation: a `.v` wrapper using SystemVerilog `.*`
connections was classified as Verilog. **No simulation ran and no actual-core
numerical result was produced.** The failure is not a measured timing or RTL
behavior result. Original and copied inputs both verify unchanged after exit;
the generated FFT wrapper's before/after hashes also match.

## Completed preparation gate

Before authorizing that invocation, parent original70316 independently passes
**138 tests in9.04s**:113 scripted harness/parser tests and25 bundle/CLI/runner
tests. All71 source files remain unchanged. The added coherent-clock/wrong-job
counterexample is rejected at the exact raw-output event join. Standalone CLI
verification from `/` succeeds with the pinned resolved Python3.11.16 binary,
without importing NumPy or executing the unchanged package init.

Parent read the complete bundle helper, CLI, runner and test sources, including
the exact interpreter identity/environment gates. Its independent audit joins
all71 input hashes to the prepared manifest, checks74 declared files and138
clean XML records, and examines all three expected Tcl-stub failures. The copied
input mutation is detected after the deliberate launch failure; no fake
results.json appears. These are **offline stubs**, not successful vendor calls.
The parent's first audit misclassified a shortened pytest directory name;
the corrected audit reads the executed Tcl stub instead. Both attempts remain.

Owner's earlier preparation run16891 remains133 PASS/1 test-setup FAIL: its
numeric-type mutation incorrectly looked for a nonexistent zero-length file.
The final test uses a real length's float alias and a separateFalse/0 encoding
control. The final owner's62296 and independent parent's70316 both pass138.

Tested source commits: FW`36338495cedfe8b4579dfa9d02553e64b865cfc7`,
HDL`c095c1dfba7201e7da335fd5d32d9b0cf66ad6e3`.
Prepared manifest SHA256:
`e524c0ba1b3f4ac0135d58a891ee3dc4b7fbe37b338f4797032159072b8311fc`.
Source signature:
`4a2210fe004dba4e20b828eda1f62fe9fe04a8324a3baaf669e95cb5ef870c33`.

## Actual invocation and isolated cause

Parent owned one Vivado2022.2 process group, two threads, fixed source bundle,
exclusive new output, logs/journal outside the output before Tcl arguments,
and a900s wall limit. Only the vendor child received its SuSE library path.
The process terminated normally with failure; it was not killed or restarted.
Parent consumed the original tool handle and independently reverified both
source copies after terminal, including on failure.

The generated `tb_vlog.prj` puts
`starlink_pss_fft_bank_owned_retained_output_probe.v` in the `verilog` section.
Vivado reports `VRFC 10-4982` at line37, `island (.*)`. The offline Icarus runs
used `-g2012`. Thus the launch profile did not match the language mode already
used for the tested source. Generated FFT wrapper SHA256 remains
`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.

Approved next correction: mark only the exact compiled RTL/bench list as
SystemVerilog, leave generated FFT VHDL/IP alone, and add a Tcl-stub regression
for that selection. No RTL, numerical vector, clock, timeout or acceptance
change is authorized by this correction. A distinct frozen bundle and reviewed
one-shot invocation are required before another vendor run. The original
failure and original manifest remain intact.

## Portable evidence

- `20260910-actual-bundle-parent.tgz`:32473972 bytes, SHA256
  `78259770396e9a197206fab9e57b2c86c1173d395ab0d4592f8bf7d27acdea04`.
  Full parent138 source/case/log/CSV/XML/audit evidence, excluding only pytest
  current convenience symlinks. XML SHA256
  `005f1e418859f43268b7367032ce73f27a600c2c788f630ad5529349a1d4190d`.
- `20260910-retained-actual-compile-parent.tgz`:12247769 bytes, SHA256
  `2cd1b698db24a1dd572438d2e420efd65d8caa06c16592beab6dd0831e94a5cc`.
  Complete parent-owned failed run, source copy, project/generated IP, compiler
  logs, owner script/command, before/after and terminal receipts.

Both archive comparisons exit0. Recovery directories `actual-bundle-parent.EvPhMALp`
and `retained-actual-parent.G1rTdLfN` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
No radio, PPU source or production HDL gitlink changed. Actual simulation,
routed timing and complete receiver/deployment qualification remain unproven.
