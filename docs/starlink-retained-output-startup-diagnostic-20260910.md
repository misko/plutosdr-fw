# Proposed targeted startup diagnostic

Preparation only; no new vendor invocation. Parent-owned corrected actual run
74560 stopped at fast cycle 31, time 174285723 fs, before any admission, with
cutover reason `01` and both result-guard current faults `01`. Its full source
and generated-IP checks passed. It is a behavioral failure, not the preceding
49345 compile-language failure. Neither attempt is relabeled.

Parent read-only WDB discovery found the escaped island scope
`/tb/dut/\retained.island ` (the trailing space terminates the escaped name).
Literal returned object handles exposed no saved values: 37 controls/counters
at eight times were all `<Blank>`. That read-only attempt is retained separately;
it did not advance simulation or change the original WDB.

The additive script `tools/diagnostics/retained_output_startup.tcl` resolves
exactly 66 named controls/counters by literal string equality against the
enumerated object handles. Each must occur once before any run command.
Only those handles are logged; there is no recursive waveform logging, force,
hierarchy assignment, clock/reset edit or checker masking. It records initial
and final text values and caps the otherwise unchanged run at 250 ns. The
expected outcome is the same original cycle-31 assertion, not a qualification
marker. Missing objects, another failure or reaching the cap do not count as
successful reproduction.

The selected signals cover fast/slow clocks and common resets, epoch release,
scheduler state/core reset, both top-level `completion_accept` and the actual
cutover `producer_closed` port, every cutover protocol input/known predicate,
reset-flush/ownership state, raw vendor controls, and shadow counters whose
declaration initializers generated compiler warnings. Invalid payload lanes and
large arithmetic buses are deliberately absent.

Minimal proposed invocation is a single fresh XSim simulation of a COPY of the
already-elaborated `tb_behav` snapshot, in a new exclusive non-`/tmp` owner
directory. Copy `xsim.dir`, `xsim.ini` and all eight exact memory files from the
parent's terminal run; retain a complete SHA/length inventory before and after.
Do not execute in the original simulation directory. The original compiled
snapshot, original/corrected bundles and their live 71-source closure must
remain unchanged. Keep original generated-IP hashes as a separate premise.
The parent must review executable copy/owner details before this invocation;
the script alone does not authorize it.

Proposed command shape (new explicit paths supplied by the owner):

```text
env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/xsim tb_behav \
  -key {Behavioral:sim_1:Functional:tb} \
  -tclbatch /ABSOLUTE/FROZEN/retained_output_startup.tcl \
  -log /ABSOLUTE/NEW_OWNER/startup.log \
  -wdb /ABSOLUTE/NEW_OWNER/startup.wdb
```

Use only the installed Vivado 2022.2 simulator and original compiled snapshot;
no IP regeneration, re-elaboration, relaxed debug/optimization or alternate
snapshot is included in this proposal. If copying the original snapshot cannot
be used faithfully, stop for a new source-specific review. Owner records the
original exit even if XSim returns zero after HDL `$fatal`, complete text/WDB
artifacts and after-integrity checks; no automatic retry or deletion.

The unchanged source bundle remains
`retained-output-actual-prelaunch-language-v2`, external manifest SHA256
`3a0eb7872722b65764178c813ec96946e61ce0ac226c0202ea0a70d24e559eeb`,
source signature `a7e6016bdc950b8324ad2c12c6e95dc708ee0a668a7351d814dd5178f388a91b`.
This diagnostic is not a new numerical campaign and cannot qualify retained
throughput, any RF/native source rate, or physical timing.
