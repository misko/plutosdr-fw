# Preflight split physical measurement: still fails175MHz

One OOC synthesis and one unchanged100/175 diagnostic route completed. Final
175MHz setup is **−2.438ns**, hold+0.071ns. This is still a failed timing gate;
the previous registered-only result was−2.461ns. No retry, source change,
constraint change, full receiver build, deployment or radio test occurred.

Measured FW `4eeda57e3f7f646ee14cdeab57b7074ca479d585`, HDL
`fb820d3908ac75e29e604a9895d482c2edf4146a`; design RTL is the tested
`cee639e43db062b8618b8d66fb26c2078ed0d2b3`. All seven synthesis RTL files match
the passing `preflight-actual-v1` snapshot. Numerical/boundary and247/8regression
evidence remains separately frozen in `preflight-reason-split-v1/`.

New physical archive:
`hdl/library/starlink_pss_acquisition/evidence/preflight-reason-physical-v1/`.
Complete runs remain `/tmp/starlink-completed-input.5EaJuD/preflight-synth-v1`
and `preflight-route-v1`, including checkpoints. Original process sessions82856
and71288 both exited0; successful tool execution is not successful timing.
Synthesis terminated2026-09-10 02:34:40UTC, route02:36:10UTC.

## Exact scope/options and cost

Vivado2022.2 build3671981, xc7z010clg400-1, maxThreads2. Top synthesis uses
REGISTERED_SCHEDULING=1, rebuilt hierarchy, AreaOptimized_high, control-set
threshold4 and out-of-context mode. Generated FFT uses its unchanged
Flow_AreaOptimized_high synthesis strategy, target-clock configuration200MHz
and generated OOC `aclk` constraint10ns (100MHz). These different IP-generation
and integration clock settings are retained, not silently reconciled.

The assembled diagnostic clocks are source_100=10ns/100MHz and
island_175=5.714ns/175.009MHz after Vivado's original1ps rounding. The unchanged
route script runs opt_design, place_design, phys_opt_design and route_design.
Inherited XDC differs from prior registered-route-v1 only in its output-path
comment. No false paths, clock groups, I/O delays or timing exceptions added.

| Measurement | Synthesis | Routed |
| --- | ---: | ---: |
| LUT / FF |1965 / 4467|1991 / 4543|
| Slices / unique control sets |not placed|1038 / 57|
| DSP48 / BRAM tiles |21 / 7.5|21 / 7.5|
|175MHz internal setup / hold,ns |not routed|−2.438 / +0.071|
|100MHz internal setup / hold,ns |not routed|+2.062 / +0.100|

Zero black boxes. All6,590routable nets fully routed; zero unrouted, partially
routed or routing-error nets. Overall setup TNS−1019.460ns/805failing endpoints;
internal175 TNS−921.683ns/688failing endpoints. This is not a narrow single-path
pass with only an isolated outlier.

## Exact worst paths and remaining qualification limits

175 setup: `registered_scheduling.state_reg[2]/C` →
`registered_scheduling.admission_receipt_reg/D`,8.028ns
(2.860logic/5.168route),16levels including6CARRY4. The cone is scheduler state →
selected_phase (fanout133) → source/product metadata mux → input_guard's full
metadata_valid equality carry chain → input_fault_now → guard admission.
The previous preflight comparison is no longer the worst cone; the active input
checker remains in the path. Per-beat identity checks were not weakened.

175 hold: `product/output_i_reg[4]/C` →
`product_bank/payload_memory_reg/DIADI[4]`,0.248ns
(0.141logic/0.107route),slack+0.071ns.

100 setup: `source_bank/metadata_in_hold_reg[7]/C` →
`source_bank/write_position_reg[8]/CE`,7.649ns
(2.595logic/5.054route),nine levels including6CARRY4,slack+2.062ns.
100 hold: `fast_fault_slow_reg[0]/C` → `fast_fault_slow_reg[1]/D`,
0.197ns(0.141logic/0.056route),slack+0.100ns. Full20-path reports are archived.

The139CDC-15 warnings,114missing input delays,124missing output delays and
missing HD.CLK_SRC properties remain unqualified. The unchanged inter-clock
reports also show source→island setup−0.717ns and island→source−1.550ns; no
exception or waiver was introduced. External OOC port routing is not a valid
physical interface qualification. No exact normalization/scoring, pilot export,
detector-stage integration or whole-receiver saving/timing claim follows.

Synthesized DCP SHA256:
`6258aaa95f804a652a4fd3aef6fa5ec1f2afd1477d7adbf266198517535e6a74`.
Routed DCP SHA256:
`944bfe1eb6e572357da67e0d0bd45312af078d58b0d9fe59e558f2f5f646c4ba`.
Scripts, all frozen source hashes, raw logs, clocks, constraints, reports and
provenance are preserved. No further physical attempt is authorized by this report.
