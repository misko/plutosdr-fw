# Arithmetic bank: one authorized OOC synthesis

The source-specific R1/B1/O1 synthesis completed successfully. This is **not a
timing pass**. No placement, route, receiver build, runtime edit, or new actual
simulation was performed.

Original owner handle **59427**, exit 0; Vivado exit 0; before/after audits 0;
completion verified with no errors. Started 2026-09-10 10:08:01.972 UTC, ended
10:09:40.715 UTC, 98.743 s. No restart or retry occurred.

Sources: FW `a17b6656f8e48be562063d0adcc8c2d791128a1f` /
HDL `5b68bb8b488a886c3861537eaf9643ec940003e0`, prepared inventory
`c249a13a4e34aa393513fa955199407eef0a569484025d1e5cdb5fc83cb185ce`.
The reviewed frozen runner was used unchanged. Actual synthesis logs confirm
REGISTERED_SCHEDULING=1, BOUNDARY_ROUND_SAT=1, REGISTER_OPERANDS=1, DATA_WIDTH=18,
and PRIVATE_PAYLOAD_BUBBLES=1. Both IP and top retain AreaOptimized_high,
control-set threshold 4, OOC, xc7z010clg400-1, and two-thread settings.

Owner directory (relative to HDL):
`library/starlink_pss_acquisition/build/arithmetic-ooc-R1B1O1-175-owned-v1`.
It retains original invocation, launch log, Vivado log/journal, phase audits,
terminal receipt, copied sources, generated IP, project and checkpoints.

## Actual synthesized resources

| Hierarchy | LUTs | FFs | DSP48E1 | RAMB18E1 |
|---|---:|---:|---:|---:|
| Whole three-bank arithmetic island | 1,944 | 4,547 | 21 | 15 |
| Generated FFT | 1,205 | 2,989 | 17 | 11 |
| Product wrapper + arithmetic | 55 | 357 | 4 | 0 |
| Product bank | 243 | 175 | 0 | 1 |
| Source bank | 62 | 165 | 0 | 1 |
| Output bank | 67 | 187 | 0 | 1 |
| Joiner + kernel ROM | 73 | 224 | 0 | 1 |
| Result guard | 139 | 180 | 0 | 0 |
| Input guard | 54 | 85 | 0 | 0 |

Whole-island LUTs comprise 1,756 logic LUTs and 188 LUTs used as shift registers;
there is no distributed RAM. Fifteen RAMB18E1 equal 7.5 BRAM tiles. There are zero
RAMB36E1, latches, and black boxes. Product hierarchy attributes 80 FFs to the
wrapper and 277 FFs to the arithmetic core. Cross-hierarchy combining prevents
treating row sums/differences as exact savings. These are synthesized—not placed
or routed—counts, and do not establish full-receiver area savings or DSP input
register mapping. No additional netlist query or physical run was launched.

## Clocks, constraints and warnings

The inherited XDC requests source_100=10.000 ns and island_175=5.714285714 ns;
Vivado reports 10.000000000 and 5.714000225 ns respectively. Both are propagated
input-port clocks. No new exceptions or IO delays were added.

`check_timing` reports 114 input ports without input delays and 124 output ports
without output delays. It reports zero unconstrained internal endpoints, no-clock
pins, multiple-clock pins and combinational loops. This does not certify external
timing. Both clk and fft_clk lack HD.CLK_SRC, so OOC clock-delay/skew estimates
are not qualified.

CDC reports six CDC-3 informational synchronized-bit structures and **139 CDC-15
warnings** for clock-enable-controlled crossings. No CDC waiver or signoff is
claimed. The report itself warns that input ports without input delays are
skipped. The generated FFT synthesis reports 116 warnings / 0 critical warnings /
0 errors; the bank synthesis reports 33 / 0 / 0. The original full logs retain
the individual warnings. There is no setup/hold slack or achieved-clock claim.

## Checkpoint and source integrity

Final linked checkpoint `synthesis/fft_bank_owned_synth.dcp`, 2,128,454 bytes:
`de5b7ca6849c8111ccfce29ca39bbf8899276c0dea309abb576e70546daf06bf`.

The source-scope pre-synthesis hashes match all thirteen live copied inputs
(twelve synthesis inputs plus the adapted recipe) after synthesis. The generated
VHDL is unchanged before/after and matches the earlier actual-core source:
`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.
The factory remains
`0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d`.
All eight runtime files remain byte-identical to the original v3 candidate.

The preparation's original actual-run admission was repeated before and after
synthesis: eleven functional terminals, 76 original service records and 345
recorded WDB values. Its original simulation automation remains FAIL solely for
the known diagnostic-log source issue; no original results.json was created.

The synthesis archive includes every regular file from the owner and preparation
directories, with ordered path/hash inventory, checkpoint hashes and independent
archive-member verification. Generated symbolic links, if any, are explicitly
listed as references rather than fabricated regular-file copies.

Routing remains separately unapproved. Full-receiver timing, CDC qualification,
continuous canonical coarse/native fine/pilot integration, .18-before-.17 RF work,
and the eventual eight-target / 120 ms / 300 s objective remain separate gates.
