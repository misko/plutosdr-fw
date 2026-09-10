# C1 plus K1/M1: diagnostic route still fails timing

The single authorized route completes, but **WNS is−1.360ns**, TNS−412.105ns
with575 failing endpoints. This improves0.470ns over the exact earlier C1
route (−1.830ns), not a closure or promotion. No retry or physical rewrite.

Original87839/tool both exit0, one terminal marker, no owner errors,
70.1423s from2026-09-10 13:45:49.908096 to13:47:00.050372 UTC.
All15 expected products are independently nonempty/hash-matched. Both input
DCP/Tcl hashes match before/after; all18 prepared files and13 synthesis
input/IP rows plus accepted simulation log remain exact. These process and
integrity successes do not override the timing failure.

| Reported path group | Setup WNS ns | TNS ns | Failing endpoints | Hold WHS ns |
| --- | ---: | ---: | ---: | ---: |
| island175 internal | −1.360 | −316.134 | 441 | +0.058 |
| source100 internal | +2.391 | 0 | 0 | +0.100 |
| source100→island175 | −0.507 | −7.995 | 45 | +0.146 |
| island175→source100 | −1.280 | −87.976 | 89 | +0.074 |

No hold failures across10603 checked endpoints; pulse-width worst+1.877ns,
zero failures. Async reset group reports setup/recovery+0.958ns and
hold/removal+0.877ns,267 endpoints. Empty user-ignored-path table; no new
exceptions. Source100 remains10ns, island175 remains5.714ns (175.009MHz due
to the inherited rounded period). No achieved-frequency claim.

All6911 routable nets are fully routed,0 errors;9316 logical nets include2405
not requiring routing. Routed area2111 LUT (1923 logic/188 SRL),4689 FF,
1131 slices,59 control sets,15 RAMB18/7.5 BRAM tiles,21 DSP,2 F7 and0 F8.
Against old routed C1: +96 LUT,+108 FF,+44 slices,+1 control set; BRAM/DSP
unchanged. These are isolated counts, not full-receiver savings.

## Exact measured paths

Worst175 setup is `product_bank/metadata_out_hold_reg[57]/C` →
`product_bank/request_toggle_reg/D`:7.021ns data delay,1.586ns logic and
5.435ns route (77.41%),8 levels (2 LUT3,2 LUT5,4 LUT6). Measured nodes pass
through balanced input-identity leaves/group, input-guard current-fault logic,
core-release/completion logic and product publication. Second path from the
same source to `result_guard/active_private_reg/D` is−1.338ns,7.047ns
(1.586 logic/5.461 route),8 levels. Third is completion_receipt/D at−1.331ns.
No kernel endpoint appears in the reported20 worst internal setup paths;
this limited list does not prove all ROM dependencies disappeared.

Worst100 setup is `per_cause_fault_cdc.causes[7].cause_sync_reg[1]/C` →
`source_bank/metadata_in_hold_reg[57]/CE`:7.112ns (1.241 logic/5.871 route),
4 levels. Worst100 hold is slow_reset_slow_reg[0]/C→[1]/D:
0.197ns (0.141 logic/0.056 route),0 levels. Worst175 hold starts at FFT
processing_address_generator/mux_addr1/use_lut6_2.latency1.Q_reg[6]/C and
ends at memory_control[1] delay-line SRL `[22][6]_srl23/D`:
0.262ns (0.141 logic/0.121 route),0 levels. Full unabridged endpoints for
all80 internal paths and all four worst crossing paths are preserved in
`path-summary.json` and the raw timing reports.

Cross100→175 setup is output_bank/acknowledge_toggle_reg/C→
acknowledge_sync_reg[0]/D,1.525ns (0.518 logic/1.007 route),0 levels.
Cross175→100 setup is output_bank/metadata_in_hold_reg[66]/C→
metadata_out_hold_reg[66]/D,1.140ns (0.518 logic/0.622 route),0 levels.
The corresponding worst hold paths are source-bank metadata[57] and
output-bank metadata[68], respectively; all exact details remain archived.

CDC remains17 informational two-stage ASYNC_REG findings and139 warnings,
0 critical. Mailbox protocol/CDC qualification is not waived. check_timing
still has114 missing input and124 missing output delays,0 unconstrained
internal endpoints/no-clock/loops. External I/O, reset integration, full
receiver and radio behavior remain outside this diagnostic result.

## Immutable evidence and source

Original owner/run:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-k1m1-route-v1`.
Owner e9b7ca13900d5b04e807bed408aab87022d05cab81c18cec33e79305f700c3b0
has only the reviewed four path/SHA changes. Exact Tcl0873675f retains
100/175 constraints,part,2 threads,opt/place/phys_opt/route and no exceptions.

Input DCP264b7dbb89ccef59b1b41dbaee2e01d4138b8d9a368f64ebc6532efd04f5405e,
2181849bytes. Routed DCP
`2a79b297bc2102c1e26c18be718f144e087f93d09d9c52c669b9afddac94c834`,3522763bytes.
Runtime remains the accepted10102 R/D/S/C/K/M111111 source, FWe7d8b229 /
HDL54af5727; synthesis sourceFWcae523aa8 / HDL49a133554. No active-fault,
numerical,CSV,qualified-status or ROM observer predicate changed.

Portable HDL directory:
`library/starlink_pss_acquisition/evidence/rom-read-ahead-route-v1`.
It preserves32 original files, all15 outputs, original owner logs/statuses,
input DCP/Tcl and old comparison reports, with full raw identities and
independent post-audit. Full synthesis/source package is adjacent
`rom-read-ahead-synthesis-v1`, HDLcb57e4482329a473d8924412f6c587d1ef549a2a,
manifest074833c6e78a21cad7ecbddca96b217dd9f107a90295b3b02e5b64e8736ac237.
Git-object verification is required for both. Original outputs, earlier
quota failure and all other failed physical snapshots remain intact.

No further actual FFT/synthesis/route, source change or radio action is
authorized by this result. The bounded study is complete and unpromoted.
