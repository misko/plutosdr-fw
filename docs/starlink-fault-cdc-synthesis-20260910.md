# Exact C1 OOC synthesis measurement

The single authorized C1 OOC synthesis completed successfully. Original owned
handle3292 exited0; the unchanged external owner independently recorded
before-audit0, tool0, after-audit0, overall0, verified completion, no errors,
all eight required nonempty products, and zero black boxes. No route occurred.

Source authorization FW `093f245fd5553a303c11eca05ed187db455a5543`, HDL
`12cfcf67a12bbfaa58ee8026a36d1c82ee91b2e1`. Prepared18-file inventory
`66001eba6a4bd5773f73ea1eaac9b730cd11e620900bbce072b1b0c5d0accb65`,
derived helper `c3e4d4eb…`, adapter `b36ba468…`, unchanged owner `d0f36ce2…`.
The runtime is the exact passing C1 actual candidate, wrapper `e8285f5e…`.
Top generics explicitly record R/D/S/C1111; other registered-mode options
remain unchanged. No source, IP factory, part, clock constraint, synthesis
directive or thread setting changed during the measurement.

Raw output: `/tmp/starlink-completed-input.5EaJuD/fault-cdc-synth-v1`.
Owner start2026-09-10T11:17:10.832780Z, end11:19:07.696160Z,
wall116.863291s. Vivado2022.2 used the reviewed SuSE loader environment,
part xc7z010clg400-1, and two threads. Log and journal precede Tcl arguments.

## Actual resource and structural results

Synthesis reports1986 LUTs,4500 FFs,21 DSP48E1,15 RAMB18E1,0 RAMB36E1:
7.5 BRAM tiles and0 black boxes. Against the exact prior111 OOC synthesis
(1970 LUTs/4478 FFs), the measured change is **+16 LUT/+22 FF**, unchanged
DSP/BRAM. These are isolated synthesis counts, not receiver savings or placed
slice/control-set counts.

Actual clock report:

- `source_100`, source port`clk`, period10.00000000000000000ns.
- `island_175`, source port`fft_clk`, period5.71400022506713867ns.

These are constraint identities, not achieved frequencies. No timing pass is
claimed. The original generated-IP OOC clock was unchanged.

The synthesis CDC report has **0 critical,17 CDC-3 information,139 CDC-15
warnings**. The former CDC-10 combinational-before-synchronizer finding is
absent in this report. All12 individual `cause_sticky`→`cause_sync[0]` paths
are explicitly recognized as depth2 one-bit ASYNC_REG synchronizers. This is
the intended structural result; it does not prove analog metastability,
MTBF, all mailbox CDC constraints, placement or complete CDC qualification.
The139 clock-enable-controlled mailbox crossings remain unwaived.

Timing-coverage caveats are unchanged:114 inputs without input delay,
124 outputs without output delay;0 no-clock and0 unconstrained internal
endpoints. There is no placement/route/setup/hold result for C1 yet. Prior
negative routed111 timing evidence is preserved, not superseded by synthesis.

## Source and checkpoint integrity

The owner verified the full copied12-input closure after synthesis. A separate
read-only audit also rehashed every one of the13 entries recorded before
synthesis in scope.txt, including the generated IP VHDL wrapper; all matched
afterwards. It independently rehashed all eight completion products too.
Receipt: `post-scope-source-check.json`; no file/source was modified by it.

Synthesized checkpoint:
`synthesis/fft_bank_owned_synth.dcp`,2125057 bytes, SHA
`8c87cbd93869a376ca727c601b47dc36ff6bc480e359abca5f12f3988ba426bd`.
Archive: `hdl/library/starlink_pss_acquisition/evidence/fault-cdc-synthesis-v1`.
Its56-member manifest SHA is
`c1b5e9210497458e6524b7abd8d8efb29485e22392613e83dff97d36a428d12f`.
Git-object verification passed all56 members/exactly57 tracked files at HDL
`096ab760b91198e8101614ed8b712f44f74707e2`; raw audit is
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-synthesis-git-audit-v1.log`.
It preserves the original owner invocation/terminal/audits, full logs, all
eight products, copied sources, generated IP configuration/wrapper and run
logs, and the exact prepared package. The original project remains intact.

Route requires separate source-specific approval of this exact checkpoint
and unchanged route script/constraints. No retry, route, physical fix,
promotion, full receiver build or radio action follows automatically.
