# Forward retirement: intended cone removed, timing still fails

The one approved unchanged 100/175 MHz synthesis/diagnostic route completed.
Internal 175 MHz setup is **−1.907 ns**, TNS **−663.483 ns**, with **664**
failing endpoints: not a timing pass or replacement candidate. Compared with
payload-bubbles-v1, WNS worsens 0.348 ns and failing endpoints increase 111.
The actual netlists nevertheless confirm the specific output-bank
held-metadata/framing tree no longer feeds the kernel expected-next CE.
No retry, source/constraint change, timing waiver or clock relaxation occurred.

Measured FW `2d8e24fe57fae7468611a7118338537cfa2a061d`, HDL
`b978ebc86d6784c902af67e7ec4fb7024d748a85`; tested RTL
`ae42e59cb4198d1e2c7321dea04f0240acda1f12`. All seven RTL files byte-match
that pin, both passing actual-core freezes, current source and synthesis
freeze before/after this measurement. Wrapper SHA256:
`363e4315fcc2df75fabd116ffced055bc569ba3dfd9bbcd92c7dd7be8713eee8`.
The separate functional report/archive retain exact CSVs and the corrected
769-pass/10-explicit-physical-skip/seven-missing-Linux-file regression,
including its preceding 745/10/30 failure snapshot. Actual inverse-current
and sticky-forward fault counters remain zero; fast real-mailbox snapshots,
not actual-core post-guard corruption, cover those predicate cases.

## Fixed measurement scope

Vivado 2022.2 build 3671981; xc7z010clg400-1; maxThreads 2 in every process.
OOC synthesis: rebuilt hierarchy, AreaOptimized_high, control-set threshold
4; FFT retains Flow_AreaOptimized_high. Logs confirm REGISTERED_SCHEDULING=1,
USE_FORWARD_RETIREMENT=1, input BALANCED_IDENTITY_EQ=1, joiner/product
PRIVATE_PAYLOAD_BUBBLES=1 and joiner/ROM BALANCED_BLOCK_IDENTITY_EQ=1.
Seven-source, parameter, actual-clock and zero-blackbox gates passed before
route. Synthesis/route/resource-XDC/thread-hook/original-DSP-helper bytes
still equal `ce6a885e`; inherited XDC differs from the previous run only in
its output-path comment. Sequence: opt_design, place_design, phys_opt_design,
route_design. No physical script was edited.

Actual `source_100` is 10 ns on `clk`; `island_175` is 5.714000225 ns on
`fft_clk` (175.009 MHz after unchanged 1 ps rounding). FFT IP configuration
targets 200 MHz while its generated OOC `aclk` remains 10 ns; neither is
the assembled fast clock. There are no generated clocks.

| Measurement | Synthesis | Routed |
| --- | ---: | ---: |
| LUT / FF | 1976 / 4467 | 2013 / 4547 |
| Slices / unique control sets | not placed | 1094 / 57 |
| DSP48E1 / RAMB18E1 / RAMB36E1 | 21 / 15 / 0 | 21 / 15 / 0 |
| BRAM tiles | 7.5 | 7.5 |
| 175 MHz internal setup / hold, ns | not routed | −1.907 / +0.071 |
| 100 MHz internal setup / hold, ns | not routed | +2.400 / +0.100 |

Versus payload-bubbles-v1: routed +40 LUT, +2 FF, +49 slices; controls,
DSPs and BRAM unchanged. These are whole-island measurements, not exact
incremental logic cost or full-receiver savings. Global setup TNS is
−748.828 ns with 805 failing endpoints of 10,366; internal 175 MHz has
664/9,699 failures. Internal 100 MHz has zero TNS/failures over 257 endpoints.
All hold TNS/failing counts are zero. All 6,729 routable nets are fully
routed, with zero unrouted/partial/overlapping nets or routing errors.

## Exact critical paths

Worst 175 MHz setup: `registered_scheduling.held_phase_reg_replica_1/C`
→ `fast_fault_reg/D`; **7.568 ns = 1.572 logic + 5.996 route** (79.228%
route), nine LUT levels (one LUT2, two LUT3, six LUT6). It traverses the
source/product tuple mux, input guard's balanced 70-bit equality, current
input fault and aggregate external/any-fast-fault logic. It is not the old
output-bank framing → kernel CE path.

The next path is **−1.868 ns**:
`joiner/kernel_rom/output_kernel_word_reg/CLKARDCLK`
→ `product/product_ii_reg/B[16]`; 3.962 ns data delay = 2.454 BRAM
clock-to-output + 1.508 route, zero LUT levels. DSP BREG=0 and B[16] setup
is 3.536 ns. Cutting an enable cone does not solve this operand path.
The third path also fails: −1.852 ns, product/i__carry_i_5__1_psdsp_5/C
→ product/output_overflow_reg/D, 7.559 ns = 3.339 logic + 4.220 route,
13 levels (eight CARRY4 plus five LUTs) through rounding/saturation.

Worst 175 MHz hold, under
`shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/`:
`single_channel.datapath/pe/scaler_gen.scaler_2i/scale_mux/four_inputs.use_lut6.no_lut_sclr.four_to_one_mux[17].latency1.reg/C`
→ `single_channel.datapath/pe/rounder_inst.with_mults.rounder_2i/reg_gate.delay_d_2/no_sclr_lut.real_shift_ram.use_baseblock.use_hlutnm_srls.srl_loop[6].i_srl16e0/D`;
0.209 ns = 0.141 logic + 0.068 route, zero levels, +0.071 ns slack.

Worst 100 MHz setup: `fast_reset_slow_reg[1]/C`
→ `source_bank/metadata_in_hold_reg[13]/CE`; 7.311 ns = 1.254 logic +
6.057 route, three LUT levels, +2.400 ns slack. Worst 100 MHz hold:
`fast_fault_slow_reg[0]/C` → `fast_fault_slow_reg[1]/D`; 0.197 ns =
0.141 logic + 0.056 route, zero levels, +0.100 ns slack.

## Actual kernel-enable and DSP inventories

Read-only inspections reopen the final synthesis and routed DCPs; all DCP
SHA checks pass before/after. The additive helper leaves the original DSP
helper unchanged and never optimizes, places, routes, mutates constraints
or design properties, or writes a checkpoint. Inapplicable primitive
HD.ISOLATED/HD.ISOLATED_EXEMPT/HD.RECONFIGURABLE/HD.TANDEM property warnings
remain in raw logs; both inspections finish successfully.

Both checkpoints have all 64 expected-next block-start CEs on one LUT6
driver, `joiner/kernel_rom/expected_next_block_start[63]_i_1`.
Their complete combinational fan-in contains **zero output-bank held
metadata startpoints and zero output-bank balanced-metadata cells**.
It still includes 64 result descriptor startpoints, 52 kernel-owned
identity cells and 27 product-bank metadata cells. Five other output-bank
cells remain: acknowledge_sync[1], input_fault, request_toggle, and the
admission_receipt_i_3/completion_receipt_i_5 logic. This establishes the
intended specific cut, not elimination of all descriptor, sticky-fault,
ownership or output-bank dependencies.

Routed kernel-CE worst slack is **−1.719 ns**:
`result_guard/fault_reasons_reg[1]/C`
→ `joiner/kernel_rom/expected_next_block_start_reg[12]/CE`;
7.180 ns = 1.696 logic + 5.484 route (76.380% route), ten LUT levels
(one LUT3, three each LUT4/LUT5/LUT6). The remaining path traverses sticky
reason/protocol/quarantine, emitted-start/duplicate-input and other current
fault/forward-valid predicates. The full top-20 report is retained.
The corresponding synthesis-only estimated worst slack is −2.908 ns
from product/output_block_exponent_reg[0]; it is not achieved timing.

All four product DSPs retain AREG=1/BREG=0 in both checkpoints.
product_ii_reg/product_iq_reg have MREG=0/PREG=1; sum_imag_reg/sum_real_reg
have MREG=1/PREG=1 after synthesis and PREG=0 after routing, with physopt
explicitly extracting 37+37 FF. Their common CEA2 LUT5 has three LUTs and
eleven registered readiness/reset/sticky startpoints, no current wide
metadata-comparator inputs. Routed CEA2 slacks are +1.231/+1.052/+0.865/
+1.512 ns for ii/iq/imag/real; ii/iq CEP is +1.557/+1.472 and sum CEM
+1.870/+2.146. All listed worst starts are fast_reset_fast_reg[1]/C.
CEB2, ii/iq CEM and routed sum CEP are constant. The earlier payload CE
cut remains physically realized; no power or invalid-switching measurement
was made.

## Unqualified interfaces and evidence

CDC remains 139 CDC-15 warnings and six CDC-3 structures. There are 114
missing input delays, 124 missing output delays, zero unconstrained internal
endpoints and missing HD.CLK_SRC warnings on both ports. Unqualified
source→island setup/hold is −0.629/+0.152 ns, TNS −11.573, 63/67 failures;
island→source is −1.117/+0.102 ns, TNS −73.771, 78/78 failures. No interface
or CDC waiver was added. Normalization, pilot export, full detector/receiver,
board-I/O and RF performance remain outside this isolated measurement.

Original sessions, each collected terminal exit 0 on 2026-09-10 UTC:

- Synthesis 19575, 05:11:25, `forward-retirement-synth-v1`.
- Route 3571, 05:13:14, `forward-retirement-route-v1`.
- Read-only synthesis inventory 17575, 05:12:33, `forward-retirement-inventory-synth-v1`.
- Read-only routed inventory 49092, 05:14:13, `forward-retirement-inventory-route-v1`.

All run paths are under `/tmp/starlink-completed-input.5EaJuD/`; main logs
are sibling `.log` files. Source DCP SHA256:
`9a141a44350da32e3ca2609b7e9911b2c41e5e9f4377c5edf3021ac459841941`.
Routed DCP SHA256:
`b8e20f1bebd96dcf375f81c14e96adee2f6ad9d7dc8802ff035525e9676b872c`.
The route input matched the successful synthesis checkpoint; both hashes
remain unchanged after all observations.

Archive `hdl/library/starlink_pss_acquisition/evidence/forward-retirement-physical-v1/`
contains raw reports/logs, exact physical scripts, seven-source freeze,
kernel coefficients/generator, generated IP XCI/VHDL/OOC clock, both DSP
and kernel-CE inventories, source gates and five checkpoint path hashes.
SHA256SUMS covers the archive; DCP binaries remain in original run paths.
Earlier evidence is untouched. No further physical trial, RTL edit, full
receiver, radio, PPU, production BD, main, push or promotion was performed.
