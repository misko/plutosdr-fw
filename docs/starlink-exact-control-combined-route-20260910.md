# Exact111 diagnostic route — timing fails; CDC remains open

Original route handle **98808** exited 0, 2026-09-10 09:50:36.806497–09:51:23.762585
UTC (46.9561 seconds). The terminal recording marker appears exactly once.
This is tool completion, not timing or release success. One route, no retry,
exception, clock change, receiver build or RF operation.

Input synthesis/source evidence is pinned by FW
`55d7fbba5b8f32798f99ae568c51cb0be2c837c5` / HDL
`fbb6ba6de76e4750ea6f04e87cbf1edb4078c96a`. Runtime remains ae50 R1/D1/S1.
The unchanged route Tcl SHA is
`0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.
Input DCP SHA `00cd669cee367f2ff9b3852d7fd05827ba64027ccd526f1f269cde5ddff630d9`
and script both verify after execution. Vivado2022.2/SuSE, maxThreads2,
source100/island175 constraints and opt/place/phys_opt/route directives unchanged.

| Path group | Worst setup/recovery ns | TNS ns | Failing endpoints | Worst hold/removal ns |
|---|---:|---:|---:|---:|
| island175 internal | −1.761 | −517.240 | 523 | +0.071 |
| source100 internal | +2.217 | 0 | 0 | +0.100 |
| source100 → island175 | −0.711 | −13.705 | 61 | +0.142 |
| island175 → source100 | −1.862 | −84.241 | 78 | +0.100 |
| async recovery | −0.038 | −0.225 | 6 | +0.633 |
| Global | −1.862 | −615.411 | 668 | +0.071 |

All hold/removal TNS and failing counts are zero. Global pulse-width slack is
+1.830 ns, zero failing endpoints. No crossings or recovery failures are omitted.

Worst island setup: `product/output_block_start_index_reg[10]/C` →
`joiner/kernel_rom/output_kernel_word_reg/ENARDEN` (ENBWREN ties).
The 9-level path traverses product-bank balanced full framing/commit checks and
result validity/input acceptance before the ROM enable. Data delay 6.948 ns =
1.572 logic + 5.376 route. A subsequent held_phase → input_guard descriptor CE
path is −1.563 ns, 7.024 ns = 1.448 logic + 5.576 route, 8 levels. These current
validation cones remain; private scratch/distributed faults did not close timing.

Worst source100 setup: `source_bank/metadata_in_hold_reg[6]/C` →
`source_bank/write_position_reg[0]/CE`, 7.290 ns = 2.548 logic + 4.742 route,
9 levels (six CARRY4). Its worst hold is `fast_fault_slow_reg[0]/C` →
`fast_fault_slow_reg[1]/D`, 0.197 ns = 0.141 logic + 0.056 route, zero levels.

Global/island worst hold: `shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/single_channel.datapath/input_muxes[0].write_data_im_mux/use_lut6_2.latency1.Q_reg[10]/C`
→ `shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/single_channel.datapath/memories[0].blkmem_gen.use_bram_only.dpms/depths_3to9.ram_loop[0].use_RAMB18.SDP_RAMB18E1_36x512/DIBDI[9]`,
0.248 ns = 0.141 logic + 0.107 route, zero levels.

Global worst setup is a crossing:
`distributed_fast_fault.causes[5].cause_sticky_reg[5]/C` →
`fast_fault_slow_reg[0]/D`, 1.809 ns = 0.704 logic + 1.105 route, two levels,
with the unchanged 0.002 ns inter-clock edge requirement. Opposite-direction
worst crossing is source-bank metadata bit18 hold-register → receive-register,
1.699 ns = 0.518 logic + 1.181 route. Worst recovery is
`slow_reset_fast_reg[1]/C` → `result_guard/descriptor_reg[41]/CLR`,
5.263 ns = 0.580 logic + 4.683 route, one level. None is waived.

Routed area: **1975 LUT, 4552 FF, 1077 slices, 58 unique control sets, 21 DSP,
15 RAMB18 (7.5 tiles)**. All 6630 routable nets are fully routed; zero routing
errors. Actual clocks remain source100 10 ns and island175 5.714 ns. CDC still
reports one CDC-10 Critical, 139 CDC-15 warnings and five CDC-3 informational
crossings. 114 input/124 output delays are unspecified; no-clock and unconstrained
internal-endpoint counts are zero. No complete-receiver or CDC/IO timing claim.

Read-only CDC review identifies the new OR of twelve epoch-sticky fast Q bits
feeding the first slow synchronizer. A destination OR of twelve independent
two-stage synchronizers preserves the nominal shift/reset recurrence and costs
up to 22 additional sync FF versus the current pair, plus slow-domain OR logic.
A source-domain export FF costs one FF but adds a fast cycle before the pair and
can permit an additional slow output transfer on late fault; it is not exact
public timing equivalence. Computing that export directly from current causes
instead restores the wide fast D cone. All immediate fast-domain fences must
remain unchanged. This review is not CDC closure or a claim of analog equivalence.

Raw outputs: `/tmp/starlink-completed-input.5EaJuD/exact-control-combined-route-v1`,
outer original-process receipts in sibling `exact-control-combined-route-owner-v1`.
Archive: `hdl/library/starlink_pss_acquisition/evidence/exact-control-combined-route-v1/`.
Routed DCP SHA `c45ac64b6731d8709cbab9fe57fdcd96c517e9d0f265017d958d2ca110537349`.
The immutable current result remains ineligible; any CDC candidate is a separate
source/test checkpoint and receives no actual or physical authorization here.
