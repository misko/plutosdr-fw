# Isolated operand A/B: DSP input registers inferred; all-path hold fails

Both original v2 runs completed, and option 1 inferred **AREG=1/BREG=1 on all
four DSP48E1 cells**, retained through routing. Option 0 retained AREG=0/BREG=0.
This establishes the intended isolated mapping. It is **not a timing pass**:
both designs report all-path hold slack −0.685 ns under the unchanged OOC
constraints. Register-to-register setup and hold are positive in both isolated
designs, but neither the actual bank BRAM path nor receiver timing is qualified.

Source pins: FW `881a8385703e15aebd6529be79207c7b8f24d862` /
HDL `f7345ab655a21374f46d2bda89854f40295fca24`. All six reviewed source hashes
were checked before launch, frozen independently by each arm, rechecked after
completion and matched across arms and against the preparation inventory.
No source, parameter, constraint or flow edit occurred between or during runs.

| Arm | Original handle | Terminal UTC, 2026-09-10 | Exit |
| --- | --- | --- | --- |
| REGISTER_OPERANDS=0 | 2548 | 07:23:10 | 0 |
| REGISTER_OPERANDS=1 | 30333 | 07:23:11 | 0 |

Both original handles were polled to terminal; no restart or retry occurred.
Each result has `tool_error=0 source_integrity_error=0` and exactly one
`OPERAND_BOUNDARY_PHYSICAL_MEASURED` terminal marker, explicitly not a timing
or bank qualification. The earlier v1 dependency failures remain failures in
their separate unchanged archive.

## Actual parameter and mapping evidence

Both Icarus probes completed with the exact selected option, width 18,
wrapper/child rounding 1 and zero product clocks. The Vivado synthesis logs
also record actual wrapper DATA_WIDTH=18, REGISTER_OPERANDS=0 or 1,
BOUNDARY_ROUND_SAT=1, and child DATA_WIDTH=18/BOUNDARY_ROUND_SAT=1. Synthesized
bus/scalar port-width checks passed. The measurement fixes Vivado 2022.2,
xc7z010clg400-1, 5.714 ns, two threads, input max/min 1.000/0.500 ns and output
max/min 0.500/0.000 ns. Only the operand option differs; no path exception or
timing budget change was made.

Synthesized and routed DSP register inventories agree exactly in each arm:

| DSP cells under `arithmetic/` | Option 0 A/B/M/P/C | Option 1 A/B/M/P/C |
| --- | --- | --- |
| `product_ii_reg`, `product_iq_reg` | 0 / 0 / 0 / 1 / 0 | 1 / 1 / 0 / 1 / 0 |
| `sum_imag_reg`, `sum_real_reg` | 0 / 0 / 1 / 1 / 1 | 1 / 1 / 1 / 1 / 1 |

ACASCREG/BCASCREG are 0/0 in option 0 and 1/1 in option 1 for every DSP.
Each stage/arm contains all 52 CE-pin records with nets and driver pins.
In option 0, all CEA1/CEA2/CEB1/CEB2 inputs are tied to GND. In option 1,
CEA1/CEB1 remain tied low and every CEA2/CEB2 uses the captured-payload enable
net `arithmetic/registered_operands.payload`, with leaf driver
`arithmetic/product_ii_reg_i_1/O`. The inventory also prints a hierarchical
boundary alias on that net; it is not asserted to be a second physical driver.

The product-pair CEP and sum-pair CEM retain product-stage enables; sum-pair
CEP retains its sum-stage enable. Their routed option-0 leaf drivers are
`arithmetic/starlink_pss_sp1_LUT4_5/O` and
`arithmetic/starlink_pss_sp1_LUT3_36/O`; option-1 drivers are
`arithmetic/product_ii_reg_i_2/O` and `arithmetic/sum_real_reg_i_1/O`.
Product-pair CEM is tied low. The complete synthesized and routed CE tables
are archived rather than inferred from RTL names alone.

## Resources and timing

| Stage | Option 0 LUT / FF / DSP | Option 1 LUT / FF / DSP |
| --- | --- | --- |
| Synthesized | 56 / 278 / 4 | 58 / 358 / 4 |
| Optimized | 64 / 278 / 4 | 58 / 358 / 4 |
| Routed | 62 / 278 / 4 | 59 / 358 / 4 |

Both arms use zero LUTRAM, SRL, RAMB18 and RAMB36. The logical extra stage has
72 operand bits plus 79 metadata bits and one valid bit. This mapped design
adds 80 fabric FFs, with operand storage inferred into DSP input registers.
Routed LUT differences reflect these isolated optimization/place runs, not a
bank or receiver area-saving estimate.

| Timing metric, ns unless count | Synth 0 | Synth 1 | Routed 0 | Routed 1 |
| --- | --- | --- | --- | --- |
| All-path setup WNS | +0.908 | +0.811 | +0.207 | +0.085 |
| Register-to-register setup | +1.168 | +0.811 | +0.964 | +0.441 |
| All-path hold WHS | +0.276 | +0.238 | **−0.685** | **−0.685** |
| Register-to-register hold | +0.276 | +0.284 | +0.103 | +0.152 |
| Setup failing endpoints / TNS | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Hold failing endpoints / THS | 0 / 0 | 0 / 0 | 176 / −49.536 | 272 / −137.903 |

All 176/272 routed hold-failing endpoints start at top-level ports, spanning
134/152 distinct start ports. There are no failing register-to-register paths
in these reports. The worst all-path setup is resetn to a result metadata FF
in option 0 and resetn to DSP RSTB in option 1. Worst internal setup remains
DSP sum to rounded output: option 0 `sum_real_reg` to `output_i_reg[16]`
(4.464 ns data path); option 1 `sum_imag_reg` to `output_q_reg[17]`
(5.083 ns). This A/B does not show improved worst internal setup slack.

The routable nets are fully routed: 398/398 for option 0 and 494/494 for
option 1, both zero routing errors. Verbose timing checks report zero missing
clocks, unconstrained internal endpoints, missing/partial IO delays or loops;
methodology reports zero violations. Those facts do not erase the failed hold
checks or establish complete external-route accuracy.

Each log has 103 printed warnings: one Synth 8-7080, 100 Route 35-198 messages
about missing HD.PARTPIN_LOCS, one Route 35-426 explaining the router cannot
repair hold on unroutable pins, and one Route 35-328 for unmet timing. There
are zero critical warnings and zero tool errors. Top-port routes lack the
partition-pin placement information needed for accurate external timing;
their negative hold numbers remain reported, not waived or treated as a
receiver result. No IO budget or exception was changed to hide them.

## Immutable artifacts

Raw output roots are
`hdl/library/starlink_pss_acquisition/build/operand-route-{0,1}-v2`; outer
stdout/logs/journals are in sibling `operand-physical-launch-{0,1}-v2`.

| Checkpoint | SHA256 |
| --- | --- |
| `operand0_synth.dcp` | `53a844c63eaee71311116ebf91232ffb5b7a6a785348ff104ebb216be175603a` |
| `operand0_opt.dcp` | `153e1e999ff127457c3ae91628b0e5f2df5b789e6125a975075db40ad2248db7` |
| `operand0_route.dcp` | `f1288c1f9d439614840f94df9bd2d5306dee7fa7ea1b8e78d48538b51272c5b1` |
| `operand1_synth.dcp` | `c62a81571cd3022ca0eed9fcf45be7f12fdda3b1063e0d40bb5281cbfa156207` |
| `operand1_opt.dcp` | `291039675b4c14f1c2b428db22f42ef8b477f428327d05120e3d8818dddb851b` |
| `operand1_route.dcp` | `f5e6ecba7d57d5ea6963a90e8f1ec3fa353ccca924dc0086c854db5fffd893e2` |

Archive: `reports/experiments/20260910-operand-physical-v2-evidence.tgz`;
SHA256 `573b139c5a1739e653edb90730b6f1333cc365ddb705f4d3222f8d77e015b50c`;
1,395,699 bytes, 90 safe unique regular files. Every archive member, all six
DCPs and both six-source inventories were independently hashed during
collection. It contains the checkpoints, sources, all reports/CE inventories,
failure-endpoint tables, terminal receipts and outer logs. Generated `.vvp`
executables and `.Xil` scratch are omitted. The JSON results contain every
artifact hash and structured resource/timing/mapping values; setup and hold
top-port counts are kept separate.

## Scope limit

The wrapper adds exactly one no-stall token cycle. Its overflow pulse remains
an insertion-time event, while output_overflow stays attached to a stalled
output. Current/late fault qualification and publication timing are not
established by this physical run. The tested bank additionally has private
payload-bubble semantics absent from this older standalone core interface;
any bank integration must preserve them, not overwrite the bank product with
this version. No bank integration, actual FFT, receiver, radio/PPU, primary
edit or push occurred here. The complete canonical/source15/30/60, native
original-rate fine, pilot and deployment objectives remain separate.
