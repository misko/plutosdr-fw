# Minimal logger compatibility reproducer proposal

Preparation only, no vendor launch. Parent actual 43908 passed repaired startup,
admitted its first F at cycle 934 and released core reset at 936, then terminated
with a simulator kernel exceptional condition at cycle 939 (5362857411 fs),
process `/tb/actual_word`. The unchanged logger wrote 512 literal `"source"`
rows; its next partial line was `0,`. The failing call supplied
`actual_inverse?"inputI":"inputF"` to an automatic task's `input string stream`.
This localizes the crash but does not yet prove a conditional-string bug.

The additive minimal bench is
`hdl/library/starlink_pss_acquisition/retained_output_actual/logger_repro/tb_retained_logger_repro.sv`.
It contains no DUT, FFT, runtime, clocks, guards or hardware. The automatic
task and identical `$fdisplay` format are copied byte-for-byte from the frozen
witness. Each independent CASE first writes/flushed a literal source row at
2 ns, then attempts exactly one selected stream row at 3 ns. It preserves both
input/raw stream families, both phase values, and all numeric formatting.

| CASE | Stream | Call construction |
| --- | --- | --- |
| 0, 1 | inputF, inputI | literal constant-phase control |
| 2, 3 | inputF, inputI | original conditional-string expression |
| 4, 5 | inputF, inputI | proposed explicit-if/else literal calls |
| 6, 7 | rawF, rawI | literal constant-phase control |
| 8, 9 | rawF, rawI | original conditional-string expression |
| 10, 11 | rawF, rawI | proposed explicit-if/else literal calls |

Proposed parent-owned vendor experiment: compile this one file as SystemVerilog
with Vivado 2022.2 `xvlog --sv`, elaborate separate `tb` CASE overrides with
`xelab --debug typical --relax --mt 2`, and run each in its own absent directory,
with separate original logs and CSV bytes. No shared output filename may be
overwritten. Record tool exits and terminal markers: a kernel crash can return
unexpected status and a partial CSV is not completion. Preserve all 12 cases,
including any outcome contrary to the hypothesis. No FFT factory or numerical
campaign is involved. Parent reviews/owns exact commands before launch.

The proposed full-harness workaround, if this reproducer supports it, changes
only the two conditional-string call sites into explicit `if(actual_inverse)` /
`else` calls with literal strings. The task, arguments, format/schema, sampling
location, numeric checks and every runtime source remain unchanged. It must
have a strict two-site inverse and identical complete scripted CSV proof before
any fresh full campaign. No such full-harness change is made by this proposal.

The accompanying offline test checks the exact task body plus all 12 expected
two-row byte strings with Icarus. Success there establishes fixture expectations,
not reproduction or repair of the XSim kernel failure. All 73 v3 campaign
sources and external bundle `cb3bfc9af54809f67c95e20fd642019c1b953f3a51f40bf3a75e3a502eabd583`
remain unchanged during this preparation.
