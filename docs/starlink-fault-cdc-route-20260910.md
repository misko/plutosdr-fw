# C1 diagnostic route: timing failure retained

The one authorized route completed, but **timing fails**: global WNS
−1.830 ns, TNS −673.636 ns, 653 failing endpoints. No retry, RTL change,
timing exception, clock relaxation, receiver build or radio action occurred.
This is an isolated, externally unqualified 100/175 MHz resource probe,
not a physical release or receiver-closure result.

## Frozen input and execution

Input synthesis archive pin: HDL `096ab760b91198e8101614ed8b712f44f74707e2`,
FW `51b7bceed8a4ca9c42a1d43752fca3e5b00b4431`. The exact passing actual
candidate remains R/D/S/C1111, runtime `02de07cc7a6c241dd6cc8cf5b733037d89eac6bd`;
no runtime source was changed. The earlier qualified-status actual result
is not an original raw217-observer pass.

- Input DCP SHA256: `8c87cbd93869a376ca727c601b47dc36ff6bc480e359abca5f12f3988ba426bd`.
- Unchanged route Tcl SHA256: `0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.
- Routed DCP SHA256: `a208cb43afdeff5cd259f3b783aea846abea6ae828836d327635ae76c9032340`.

Original handle **49744** was consumed to terminal0. Vivado process0 and
post-DCP/Tcl integrity0 are recorded separately from the timing failure.
Start2026-09-10T11:28:13.898185680Z, end11:29:13.193771348Z; elapsed59.27s.
Vivado2022.2, xc7z010clg400-1, SuSE loader environment, maxThreads2;
unchanged opt/place/phys_opt/route directives. The DCP opened with zero black
boxes. Source clocks were checked before placement: `source_100` at `clk`,
10 ns; `island_175` at `fft_clk`, 5.714000225 ns. These are constraints,
not achieved frequencies. Inherited XDC contains only the two resource clocks.

Raw directories remain intact:
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-route-v1` and
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-route-owner-v1`.

## Measured timing and resources

| Path group | Worst setup/recovery ns | TNS ns | Failing/total endpoints | Worst hold/removal ns |
|---|---:|---:|---:|---:|
| Global | −1.830 | −673.636 | 653/10428 | +0.058 |
| island175 | −1.830 | −583.930 | 535/9717 | +0.058 |
| source100 | +2.780 | 0 | 0/290 | +0.104 |
| source100 → island175 | −0.492 | −2.678 | 29/67 | +0.136 |
| island175 → source100 | −1.229 | −87.029 | 89/89 | +0.109 |
| async reset, island175 → island175 | +0.615 | 0 | 0/265 | +0.752 |

Every group has zero hold/removal failures. Pulse-width slack is +1.830 ns,
zero failures/4935 endpoints. Rounded per-group TNS values need not sum to
the printed global rounding. No asynchronous mailbox path was waived.

Routed area: **2015 LUT, 4581 FF, 1087 slices, 58 unique control sets,
21 DSP, 15 RAMB18, 0 RAMB36 (7.5 tiles)**. All6736 routable nets are fully
routed, zero routing errors; 2335 other logical nets need no routing.
Compared with the prior111 route, area changes are +40 LUT/+29 FF/+10 slices,
unchanged control sets/DSP/BRAM. This includes implementation optimization
differences, not just the logical +22 CDC registers. Island setup worsened
from −1.761 to −1.830 ns; this is not a closure improvement claim.

## Exact worst paths

The worst island setup is
`registered_scheduling.held_phase_reg_replica_1/C` →
`input_guard/descriptor_reg[11]/CE` (ties include bit16):
**7.291 ns = 2.083 logic + 5.208 route**, eight levels
(one CARRY4, one LUT3, one LUT4, three LUT5, two LUT6).
Held-phase selection feeds the input metadata/current-fault checker,
`input_fault_now`, then `job_started` and the descriptor CE.
The final job_started net has fanout71 and0.978 ns route delay.

A near-tied, distinct path at **−1.825 ns** starts
`product_bank/write_position_reg[4]/C` and ends
`joiner/kernel_rom/block_start_index_reg[57]/CE`:
**7.286 ns = 1.586 logic + 5.700 route**, eight LUT levels. It traverses
current bank framing/input fault and result-guard commit-valid logic into
kernel block-metadata CE. This is not merely the private coefficient-word
read enable; changing only that word read cannot by itself remove this path.

The worst global/island hold is the FFT internal
`shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/control/processing_address_generator/switch/use_lut6_2.latency1.Q_reg[0]/C`
→ `shared_xfft/U0/i_synth/xfft_inst/non_floating_point.arch_b.xfft_inst/control/delay_line_for_i_sw_control/no_sclr_lut.real_shift_ram.use_baseblock.use_hlutnm_srls.srl_loop[0].i_srl16e0/D`:
+0.058 ns slack,0.197 ns data (0.141 logic/0.056 route), zero logic levels.

Source100 setup: `per_cause_fault_cdc.causes[5].cause_sync_reg[1]/C` →
`source_bank/metadata_in_hold_reg[18]/CE`,6.723 ns
(1.371 logic/5.352 route), four levels. Source100 hold:
`per_cause_fault_cdc.causes[6].cause_sync_reg[0]/C` → its stage1 `/D`,
0.197 ns (0.141/0.056), zero levels.

Worst100→175 setup: `source_bank/metadata_in_hold_reg[22]/C` →
`source_bank/metadata_out_hold_reg[22]/D`,1.492 ns (0.456/1.036), zero levels.
Worst175→100 setup: `output_bank/metadata_in_hold_reg[32]/C` →
`output_bank/metadata_out_hold_reg[32]/D`,1.080 ns (0.456/0.624), zero levels.
Their hold endpoints are respectively source-bank metadata bit28 and
`distributed_fast_fault.causes[2].cause_sticky_reg[2]_replica/C` →
`per_cause_fault_cdc.causes[2].cause_sync_reg[0]/D`; delays0.263 ns
(0.141/0.122) and0.244 ns (0.141/0.103), zero levels.

Worst reset recovery: `fast_reset_fast_reg[1]/C` →
`result_guard/descriptor_reg[12]/CLR`,4.610 ns (0.580/4.030), one LUT2.
Worst removal: `slow_reset_fast_reg[1]/C` →
`result_guard/return_position_reg[6]/CLR`,0.707 ns (0.209/0.498), one LUT2.
These internal results do not qualify external reset-pin timing.

## CDC, coverage and evidence boundary

Routed CDC reports **0 critical,17 CDC-3 information,139 CDC-15 warnings**.
The old CDC-10 combinational-before-synchronizer finding remains absent;
all12 independent cause crossings are recognized as two-stage ASYNC_REG.
This is structural evidence, not analog MTBF/coherency or complete mailbox
CDC qualification. The139 warnings remain open and unwaived.

Timing coverage still reports114 inputs without input delays,124 outputs
without output delays, zero no-clock and zero unconstrained internal
endpoints. External I/O and reset assertions remain unqualified. Both
negative timing and incomplete interface/CDC coverage prohibit promotion.

Portable archive: `hdl/library/starlink_pss_acquisition/evidence/fault-cdc-route-v1`.
It includes every raw route/owner file, the input and routed DCPs, exact
prepared package, source scope and synthesis post-source receipt. Its README
records the invocation and links provenance to the immutable synthesis
archive containing all seven RTL sources and generated-IP closure. No
functional tests were rerun or acceptance conditions changed for packaging.

Manifest SHA256:
`a0465b1b7f73e7a39fffcb2cd10ff75180e1b921812c460a08f0b83cb3b1a262`.
Local and committed Git-object verification passed all 48 members, exactly
49 tracked files, at HDL `d16ff8d36fbc2297711dddc9750b4edb7b000df4`.
Raw publication check:
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-route-git-object-audit-v1.log`.
This proves committed archive closure, not remote publication or test validity.
Raw Vivado whitespace is preserved byte-for-byte, not reformatted for Git's
whitespace checker. The runtime and physical scripts remain unchanged.
