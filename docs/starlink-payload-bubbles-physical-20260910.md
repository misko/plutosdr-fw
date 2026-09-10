# Payload bubbles: DSP enables improve, 175 MHz still fails

The single approved synthesis and unchanged 100/175 MHz diagnostic route
completed, but 175 MHz setup is **−1.559 ns**, with 553 failing internal
endpoints. Worst slack improves 0.055 ns against held-preflight-v1, while
internal TNS worsens from −497.942 to −518.092 ns and failing endpoints
increase from 501 to 553. This is not a timing pass or replacement candidate.
There was no retry, RTL change, timing exception or clock relaxation.

Measured FW `c62118a9a8fd5056f3376a526c36157e004842ae`, HDL
`97adf891ee4cece8634c0bf9bc6694a1df58b9aa`; tested RTL
`b7dac8024d5870c9b2909188dfa0a7766c3f7a39`. All seven RTL files byte-match
that pin, the passing `payload-actual-v1/frozen_sources` and current source
before and after synthesis, route and both read-only checkpoint inspections.
Wrapper SHA256 is
`5d2d72fcb8e98fd75f585e719a358b7afdc172214312f9250d97b7702c009677`.
The separate functional report and immutable `payload-bubbles-v1/` retain
both actual-core passes, exact reference CSVs, 36 focused passes, mutation
failures and the expanded 752-pass/10-explicit-skip/seven-missing-Linux-file
regression result. This physical measurement does not replace those claims.

## Unchanged physical gates

Vivado 2022.2 build 3671981, xc7z010clg400-1, maxThreads 2 in each process.
Top synthesis is OOC, rebuilt hierarchy, AreaOptimized_high, control-set
threshold 4; FFT synthesis retains Flow_AreaOptimized_high. Logs confirm
REGISTERED_SCHEDULING=1, input BALANCED_IDENTITY_EQ=1, both joiner/product
PRIVATE_PAYLOAD_BUBBLES=1 and joiner/ROM BALANCED_BLOCK_IDENTITY_EQ=1.
Zero-blackbox, all-seven-source and clock gates passed before route.

The synth/route scripts and resource XDC byte-match held-preflight-v1
(and its previously verified balanced-v1 scripts). Inherited XDC differs
only in its generated output-path comment. The route sequence remains
opt_design, place_design, phys_opt_design, route_design.
`source_100` is 10 ns on `clk`; `island_175` is 5.714000225 ns on `fft_clk`
(175.009 MHz after unchanged 1 ps rounding). Generated FFT IP configuration
targets 200 MHz, but its generated OOC `aclk` constraint remains 10 ns.
Neither IP setting is the assembled fast clock. No generated clocks exist.

## Measured area and timing

| Measurement | Synthesis | Routed |
| --- | ---: | ---: |
| LUT / FF | 1973 / 4467 | 1973 / 4545 |
| Slices / unique control sets | not placed | 1045 / 57 |
| DSP48E1 / RAMB18E1 / RAMB36E1 | 21 / 15 / 0 | 21 / 15 / 0 |
| BRAM tiles | 7.5 | 7.5 |
| 175 MHz internal setup / hold, ns | not routed | −1.559 / +0.071 |
| 100 MHz internal setup / hold, ns | not routed | +1.851 / +0.100 |

Against held-preflight-v1, routed LUT/FF/slices change by −8/−2/−140;
control sets, DSPs and BRAM do not change. These are whole-slice packing
measurements, not separable comparator cost or full-receiver savings.
Global setup TNS is −610.632 ns with 661 failing endpoints; internal
175 MHz TNS is −518.092 ns with 553 failures. Internal 100 MHz setup TNS
and all hold TNS are zero. All 6,668 routable nets are fully routed;
zero routing errors, unrouted nets, partial nets or overlaps remain.

Worst 175 MHz setup: `result_guard/descriptor_reg[51]/C` →
`joiner/kernel_rom/expected_next_block_start_reg[17]/CE`, 6.984 ns data
delay = 1.634 ns logic + 5.350 ns route (76.604% route), nine LUT levels
(one LUT4, two LUT5, six LUT6). It traverses the **output bank's** balanced
75-bit framing comparison, current fault/public-valid logic and kernel
ROM acceptance enable. This is not the ROM's own 64-bit identity comparator.
The archived top-20 paths show repeated endpoints in this cone.

Worst 175 MHz hold: under
`shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/`,
`single_channel.datapath/input_muxes[1].write_data_re_mux/use_lut6_2.latency1.Q_reg[4]/C`
→ `single_channel.datapath/memories[1].blkmem_gen.use_bram_only.dpms/depths_3to9.ram_loop[0].use_RAMB18.SDP_RAMB18E1_36x512/DIADI[4]`;
0.248 ns = 0.141 logic + 0.107 route, zero logic levels, +0.071 ns slack.

Worst 100 MHz setup: `slow_reset_slow_reg[1]/C` →
`source_bank/metadata_in_hold_reg[40]/CE`, 7.860 ns = 1.198 logic +
6.662 route, three LUT levels, +1.851 ns slack.
Worst 100 MHz hold: `slow_reset_slow_reg[0]/C` →
`slow_reset_slow_reg[1]/D`, 0.197 ns = 0.141 logic + 0.056 route,
zero logic levels, +0.100 ns slack.

## Actual DSP registers and enable cones

Separate read-only checkpoint inventories inspect all 21 DSP48E1 primitives,
and every CE pin, driver, complete combinational fan-in startpoint/cell list
and worst path for the four product DSPs. These inspect final DCPs, not
preliminary synthesis inference or parameter-specialized dead RTL.

All four product DSPs have AREG=1 and BREG=0 in both checkpoints.
`product_ii_reg` and `product_iq_reg` have MREG=0/PREG=1. `sum_imag_reg`
and `sum_real_reg` have MREG=1/PREG=1 after synthesis; routed PREG=0,
with physopt explicitly pushing 37+37 result registers into fabric.

All four CEA2 pins are driven by the same LUT5 output
`joiner/kernel_rom/product_ii_reg_i_1/O`. Their complete fan-in now contains
three LUTs and eleven registered startpoints: fast_fault, the two fast-domain
reset synchronizer outputs, kernel output_valid/protocol_fault, product
output_valid/product_valid/sum_valid, product-bank acknowledge_sync[1],
input_fault and request_toggle. **No descriptor/metadata bit or current raw
framing-comparator startpoint remains in these actual CEA2 cones.**

| Product DSP | Routed CEA2 slack, ns | Other active payload CE slack, ns |
| --- | ---: | ---: |
| product_ii_reg | +0.708 | CEP +1.693 |
| product_iq_reg | +1.250 | CEP +1.349 |
| sum_imag_reg | +1.241 | CEM +2.213 |
| sum_real_reg | +0.426 | CEM +2.248 |

Every listed routed CE worst path starts at `fast_reset_fast_reg[1]/C`.
The ii/iq CEP and sum CEM driver is LUT6 `product/product_ii_reg_i_2/O`;
its two-LUT cone has nine registered readiness/reset/sticky startpoints.
CEB2 is constant; ii/iq CEM is constant; routed sum CEP is constant because
its PREG was extracted. This proves the intended DSP-enable cone cut in
this mapping, not timing closure of the surrounding arithmetic pipeline.
No power measurement was made; invalid-cycle payload switching can increase.

The inventory helper never optimizes, places, routes, changes design or
constraint properties, or writes a DCP. SHA checks pass before/after both
inspections. Dumping all primitive properties emits retained Vivado warnings
for inapplicable HD.ISOLATED/HD.ISOLATED_EXEMPT/HD.RECONFIGURABLE/HD.TANDEM
queries; both inventories still complete successfully. No warnings are hidden.

## Interface caveats and reproducible evidence

CDC remains 139 CDC-15 warnings and six CDC-3 synchronized structures;
114 missing input delays, 124 missing output delays, zero unconstrained
internal endpoints. Missing HD.CLK_SRC warnings remain for both OOC ports.
Unqualified source→island setup/hold is −0.481/+0.074 ns, TNS −7.752,
30 failing endpoints; island→source is −1.307/+0.117 ns, TNS −84.788,
78 failures. No crossing or interface waiver was added. There is no
integrated normalizer, pilot export, full detector/receiver, board-I/O or RF
qualification. Successful tool exits do not imply a physical release pass.

Original sessions, all terminal exit 0 on 2026-09-10 UTC:

- Synthesis 70333, 04:32:40, `payload-bubbles-synth-v1`.
- Route 53502, 04:34:36, `payload-bubbles-route-v1`.
- Read-only synthesis inventory 87489, 04:33:40, `payload-bubbles-dsp-synth-v1`.
- Read-only routed inventory 37187, 04:37:34, `payload-bubbles-dsp-route-v1`.

All paths above are under `/tmp/starlink-completed-input.5EaJuD/`; raw main
logs are sibling `.log` files. Source DCP SHA256:
`5165b1c7f2e641c6c747334cfcdc47c7244f9e8335d4174b622ec23f561c60c1`.
Routed DCP SHA256:
`aa8ec6210d3e495ca39567bb3dd74eb276c06dbca247e13ac45f60fae060b955`.
Both remain unchanged after all authorized observations.

Archive `hdl/library/starlink_pss_acquisition/evidence/payload-bubbles-physical-v1/`
contains raw reports/logs, exact scripts, seven-source freeze, generated IP
XCI/VHDL/OOC clock, both DSP inventories and all five checkpoint path hashes.
`SHA256SUMS` covers the archive; binary DCPs remain in their original paths.
Earlier negative evidence is untouched. No full receiver, radio, PPU,
production BD, main, remote push or promotion action was taken.
