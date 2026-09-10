# Held-preflight physical result: still fails 175 MHz

The single approved OOC synthesis and unchanged 100/175 MHz diagnostic route
completed, but internal 175 MHz setup is **−1.614 ns**, 0.018 ns worse than
balanced-v1. There are 501 failing internal endpoints. The worst path moved
from preflight certification to product-bank current-fault checks feeding
arithmetic readiness; the next path is only 0.001 ns better. This is not a
timing pass or replacement candidate. No retry or source/constraint change
occurred.

Measured FW `dddcdc4543317ac99cc151e402b06d7b56b073ba`, HDL
`1780040f60be2a123f9affd66325c020eeb0907e`; tested design RTL
`7ee87258be4cde11a6092d22ad76a085cfaecc76`. All seven RTL files byte-match
that tested pin and the passing `held-preflight-actual-v1` freeze before and
after measurement. Wrapper SHA256:
`d6491e46caa7419679e50f72a9d7f568a9f2f6ce567a94ddfdff02894c74df60`.
The 264-pass/eight-explicit-physical-skip regression and both actual-core
terminal receipts remain separately frozen in `held-preflight-v1/`.
Its documented raw-readiness stimulus/private-counter differences remain;
this physical study makes no unchanged-full-trace claim.

## Unchanged gates and clocks

Vivado 2022.2 build 3671981, xc7z010clg400-1, maxThreads 2 in every process.
Synthesis logs confirm REGISTERED_SCHEDULING=1 and BALANCED_IDENTITY_EQ=1.
Top synthesis uses OOC mode, rebuilt hierarchy, AreaOptimized_high and
control-set threshold 4; FFT synthesis retains Flow_AreaOptimized_high.
The FFT IP target-clock configuration is 200 MHz; its generated OOC `aclk`
constraint remains 10 ns/100 MHz. Neither is the assembled fast clock:
source_100 is 10 ns on `clk`, island_175 is 5.714000225 ns on `fft_clk`
(175.009 MHz after the unchanged 1 ps rounding). There are no generated clocks.

All seven source hashes, parameters, clocks and zero-blackbox gates passed
before routing. Synthesis/route scripts and resource XDC byte-match
balanced-v1. Inherited XDC differs only in the generated output-path comment.
The unchanged route sequence is opt_design, place_design, phys_opt_design,
route_design, with no timing exceptions, new I/O delays or clock relaxation.

## Area and timing

| Measurement | Synthesis | Routed |
| --- | ---: | ---: |
| LUT / FF | 1959 / 4467 | 1981 / 4547 |
| Slices / unique control sets | not placed | 1185 / 57 |
| DSP48E1 / RAMB18E1 / RAMB36E1 | 21 / 15 / 0 | 21 / 15 / 0 |
| BRAM tiles | 7.5 | 7.5 |
| 175 MHz internal setup / hold, ns | not routed | −1.614 / +0.071 |
| 100 MHz internal setup / hold, ns | not routed | +3.052 / +0.110 |

Compared with balanced-v1, routed LUT/FF decrease by 42/9, but occupied slices
increase by 130. Control sets, DSPs and BRAM are unchanged. This is a placement
and packing result for the whole isolated slice, not an isolated comparator
cost or full-receiver resource saving. Hierarchical reports are archived;
cross-hierarchy logic combining prevents additive replacement estimates.

All 6,624 routable nets are fully routed, with zero routing errors or remaining
unrouted/partially routed nets. Global setup TNS is −584.640 ns over 592 failing
endpoints; internal 175 MHz TNS is −497.942 ns over 501 failing endpoints.
Internal 100 MHz TNS is zero. Hold TNS is zero with no failing endpoints in
either domain or either crossing direction. Successful Vivado exit is not a
physical timing pass.

## Exact worst cones

175 MHz setup: `product/output_block_start_index_reg[6]/C` →
`product/sum_imag_reg/CEA2`, 6.747 ns data delay (1.462 logic / 5.285 route),
seven LUT levels, slack −1.614 ns. The path traverses the product bank's
balanced metadata leaves/groups, current framing/fault logic and result-guard
readiness to `product/input_accept`, then the DSP clock enable. Routing is
78.330% of data delay. The DSP enable setup requirement is 0.497 ns.

Near-tie setup: `result_guard/descriptor_reg[43]/C` →
`joiner/kernel_rom/expected_next_block_start_reg[0]/CE`, slack −1.613 ns,
7.038 ns (2.084 logic / 4.954 route), eight levels including three CARRY4.
This traverses the kernel ROM metadata comparison, current fault/valid logic
and its acceptance enables. These two active data/control cones, not the
previous scheduler-state/preflight comparator, dominate the reported top 20
paths. Their current-beat fault checks were not removed or delayed.

175 MHz hold: `product/output_q_reg[8]/C` →
`product_bank/payload_memory_reg/DIBDI[10]`, 0.248 ns
(0.141 logic / 0.107 route), zero logic levels, slack +0.071 ns.

100 MHz setup: `source_bank/input_fault_reg/C` →
`output_bank/read_address_reg[2]/CE`, 6.659 ns
(0.952 logic / 5.707 route), four LUT levels, slack +3.052 ns.
100 MHz hold: `fast_reset_slow_reg[0]/C` → `fast_reset_slow_reg[1]/D`,
0.206 ns (0.141 logic / 0.065 route), zero levels, slack +0.110 ns.

## Unqualified interfaces and evidence

CDC reports 139 CDC-15 warnings and six CDC-3 synchronized structures.
There are 114 missing input delays, 124 missing output delays and zero
unconstrained internal endpoints. Missing HD.CLK_SRC properties remain.
Unqualified inter-clock source→island setup/hold is −0.465/+0.120 ns
(setup TNS −2.071 ns, 13 failing endpoints); island→source is −1.381/+0.119 ns
(setup TNS −84.627 ns, 78 failing endpoints). These crossings are neither
waived nor claimed physically qualified. There is no integrated score
normalizer, pilot export, full detector/receiver, board-I/O or RF qualification.

Original synthesis session 68943 exited 0 at 2026-09-10 03:39:35 UTC;
original route session 11344 exited 0 at 03:43:14 UTC. Complete runs and all
binary checkpoints remain at `/tmp/starlink-completed-input.5EaJuD/held-preflight-synth-v1`
and `/tmp/starlink-completed-input.5EaJuD/held-preflight-route-v1`.
Synthesized route-input DCP SHA256:
`5ed836b4e640a36657244cf5b0c6ff26abea6788901e4b9cb978198a06c4f15c`.
Routed DCP SHA256:
`20d347c8790bdc260edfe6b72e6fa980a7f7d0f178dddeb61fda2a59035799bb`.
The source DCP hash was unchanged after routing.

Archive `hdl/library/starlink_pss_acquisition/evidence/held-preflight-physical-v1/`
contains the full reports, frozen source inventories, exact scripts, generated
IP wrapper/XCI/OOC clock, synthesis subrun logs, raw terminal logs and all
checkpoint hashes. `SHA256SUMS` covers the archive; binary DCPs remain in their
original paths. Earlier negative evidence is untouched. No full receiver,
radio, PPU, production BD, main, remote push or promotion action was taken.
No further physical run is authorized.
