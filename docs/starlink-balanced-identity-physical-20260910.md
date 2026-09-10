# Held-phase/balanced identity physical result: still fails175MHz

The single approved OOC synthesis and unchanged100/175 diagnostic route
completed, but175MHz setup is **−1.596ns**. This improves0.842ns over the
preceding−2.438ns measurement;497 internal175 endpoints still fail. Hold is
positive in both domains. No retry, source/constraint change, clock relaxation,
whole receiver build or radio action occurred.

Measured FW `eb9e008e7e0b600979070976d75e9a832b1f3258`, HDL
`9f598dd11bf7949923b3a3701ea34123d0508651`; tested design RTL
`447183b84250595be5324556f65145d130aca453`. All seven synthesis RTL files
byte-match that tested pin and the passing `balanced-actual-v1` freeze, both
before and after the measurement. The258-pass/eight-explicit-skip regression
and both actual-core receipts remain separately frozen in `balanced-identity-v1/`.

## Scope, clocks and gates

Vivado2022.2 build3671981, xc7z010clg400-1, maxThreads2 in each process.
Actual synthesis logs confirm REGISTERED_SCHEDULING=1 and BALANCED_IDENTITY_EQ=1.
Top synthesis uses rebuilt hierarchy, AreaOptimized_high, control-set threshold4
and out-of-context mode. FFT synthesis retains Flow_AreaOptimized_high,
target-clock IP configuration200MHz and generated OOC `aclk`=10ns/100MHz.
The assembled clocks are source_100=10ns/100MHz on`clk` and island_175=5.714ns/
175.009MHz on`fft_clk`, retaining the original1ps rounding. No generated clocks.

All source, parameter, clock and zero-blackbox gates passed before routing.
The synthesis/route scripts and resource XDC byte-match the prior preflight
measurement. Inherited XDC differs only in its generated output-path comment.
The route runs the unchanged opt_design, place_design, phys_opt_design and
route_design sequence, with no new exceptions or I/O delays.

## Measured cost and timing

| Measurement | Synthesis | Routed |
| --- | ---: | ---: |
| LUT / FF |2005 / 4467|2023 / 4556|
| Slices / unique control sets |not placed|1055 / 57|
| DSP48E1 / RAMB18E1 / RAMB36E1 |21 / 15 / 0|21 / 15 / 0|
| BRAM tiles |7.5|7.5|
|175 internal setup / hold,ns |not routed|−1.596 / +0.070|
|100 internal setup / hold,ns |not routed|+2.426 / +0.100|

Overall routed cost is32LUT/13FF/17slices above the previous preflight result;
synthesis is40LUT higher with unchanged FF. Cross-hierarchy optimization moves
logic between checker/mailbox/result hierarchies, so their individual changes
are not an isolated comparator price or a whole-receiver saving estimate.

All6,664routable nets are fully routed: zero unrouted, partially routed or
routing-error nets. Overall setup TNS−611.309ns/621failing endpoints;
internal175 TNS−522.209ns/497failing endpoints. Overall hold TNS is0 with no
failing endpoints. Successful tool exit is not a physical timing pass.

## Exact worst paths

175 setup: `registered_scheduling.state_reg[0]_replica/C` →
`registered_scheduling.descriptor_certified_reg/D`,7.255ns
(2.443logic/4.812route),12levels including5CARRY4. The path is state →
selected_phase (fanout83) → discovery source/product metadata mux → full
preflight metadata comparison (`epoch_preflight_reasons[3]` carry chain) →
any_fast_fault → descriptor certificate. The prior active-input identity cone
is no longer the worst path. Discovery/preflight selection was deliberately
unchanged by the held-phase input-only experiment. No fault veto was removed.

175 hold: source
`shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/single_channel.datapath/pe/scaler_gen.scaler_0i/scale_mux/four_inputs.use_lut6.no_lut_sclr.four_to_one_mux[13].latency1.reg/C`
to destination
`shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/single_channel.datapath/pe/rounder_inst.with_mults.rounder_0i/reg_gate.delay_d_2/no_sclr_lut.real_shift_ram.use_baseblock.use_hlutnm_srls.srl_loop[4].i_srl16e0/D`;
0.209ns (0.141logic/0.068route),zero logic levels,slack+0.070ns.

100 setup: `source_bank/metadata_in_hold_reg[44]/C` →
`source_bank/write_position_reg[0]/CE`,7.113ns
(2.215logic/4.898route),six levels including3CARRY4,slack+2.426ns.
100 hold: `fast_reset_slow_reg[0]/C` → `fast_reset_slow_reg[1]/D`,0.197ns
(0.141logic/0.056route),zero logic levels,slack+0.100ns.

## Unqualified interfaces and preserved evidence

CDC still reports139CDC-15 warnings and six CDC-3 synchronized structures.
There are114missing input delays,124missing output delays, and zero internal
unconstrained endpoints; missing HD.CLK_SRC properties remain. Inter-clock
source→island setup/hold is−0.839/+0.129ns; island→source is−1.365/+0.072ns.
These unqualified bundled-data/interface crossings are not waived or silently
treated as ordinary valid physical interfaces. There is no integrated score
normalizer, pilot export, full detector/receiver or board-I/O qualification.

Original synthesis session12228 exited0 at2026-09-10 03:08:07UTC; route96525
exited0 at03:09:57UTC. Complete runs and checkpoints remain at
`/tmp/starlink-completed-input.5EaJuD/balanced-synth-v1` and `balanced-route-v1`.
Synthesized route-input DCP SHA256:
`fbeb7245dec062e80ebf9c25cc10fdbf1c1a7fcd22b1fe3640168e552bff01c2`.
Routed DCP SHA256:
`8b3cc503e91be9ecabd1f6da76284cc18f0703220138700e512224d39987e165`.
The source DCP hash was rechecked after routing and is unchanged.

Archive `hdl/library/starlink_pss_acquisition/evidence/balanced-identity-physical-v1/`
contains all measurement reports, scripts, source inventories, frozen RTL,
generated IP wrapper/XCI/OOC clock, synthesis subrun and terminal logs.
`SHA256SUMS` covers the archive; binary DCPs remain in the original run paths.
Previous negative physical evidence is untouched. This source remains
unpromoted and ineligible for replacement; no further route is authorized.
