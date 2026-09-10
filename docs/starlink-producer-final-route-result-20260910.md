# P1 diagnostic route: failed, not promoted

The one authorized route completed, but timing failed: **WNS−1.492ns,
TNS−441.681ns,591 failing endpoints**. This is0.132ns worse than the prior
ROM K1/M1 route (−1.360ns). No retry, constraint change, waiver, runtime promotion,
or inverse-adapter composition followed. Tool success is not timing success.

Original handle63593 exited0; tool0, errors[], exactly one completion marker;
start2026-09-10T15:28:35.593055Z, end15:29:36.871652Z,61.2786s.
All15 expected products are nonempty and independently rehashed. Original inputs
match before and after; all19 prepared files and15 synthesis source/IP/log rows
also rehashed after route. No source or physical-script changes occurred.

## Exact measured scope

| Path class | Setup WNS ns | TNS ns | Failing endpoints | Hold WNS ns | Hold failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Whole diagnostic | −1.492 | −441.681 | 591 | +0.058 | 0 |
| 175MHz internal | −1.492 | −334.498 | 448 | +0.058 | 0 |
| 100MHz internal | +2.246 | 0 | 0 | +0.100 | 0 |
| 100→175MHz | −0.699 | −14.925 | 54 | +0.138 | 0 |
| 175→100MHz | −1.249 | −92.257 | 89 | +0.107 | 0 |

Crossing rows remain reported under the unchanged diagnostic constraints; they
are neither waived nor an assertion of synchronous CDC correctness. Small TNS
rounding differences between sum and global row are retained as emitted.

Routed area:2116 LUT,4692 FF,1157 slices,58 control sets,15 RAMB18,21 DSP.
Prior ROM route:2111 LUT,4689 FF,1131 slices,59 control sets, same BRAM/DSP.
All6916 routable nets fully routed, zero routing errors (9316 logical nets;
2400 do not need routing). Pulse-width slack+1.877ns, no pulse-width failures.

## Exact remaining cones

Worst175MHz setup:
`product_bank/metadata_in_hold_reg[12]/C` →
`result_guard/active_private_reg/D`,−1.492ns. Data delay7.154ns:
1.572ns logic,5.582ns routing (78.026%), nine LUT levels.
The emitted path passes product-bank balanced metadata equality, current framing
fault, and unchanged global result completion/active control. The next path is
`product_bank/metadata_out_hold_reg[34]/C` →
`result_guard/awaiting_ack_reg/D`,−1.410ns;7.069ns=1.572logic+5.497route,
nine levels through input identity/current fault and result control.

The former worst producer request-toggle endpoint is not among the new top20;
that observation alone is not a full cone-removal or endpoint-closure proof.
Full completion/reason/input validation dependencies were deliberately retained.
Remaining ROM metadata-selector→expected/output-index enables also appear in
top20 at−1.221/−1.213ns. P1 has not solved these paths.

100MHz setup: `source_bank/metadata_in_hold_reg[6]/C` →
`source_bank/write_position_reg[0]/CE`,+2.246ns;
7.465ns=2.565logic+4.900route, nine levels (six CARRY4 plus three LUTs).
100MHz hold: `fast_reset_slow_reg[0]/C` → `fast_reset_slow_reg[1]/D`,
+0.100ns;0.197ns=0.141logic+0.056route, zero logic levels.
Worst175 hold is the vendor FFT four-to-one mux[4] latency1 register→
pipeline_balancer_im srl_loop[2] input,+0.058ns;0.197ns with the same breakdown.
The full exact vendor endpoints, all80 internal top20 records, and four crossing
worst setup/hold endpoint strings are retained in `path-summary.json` and raw
timing reports; no endpoint names are silently substituted.

100→175 worst setup source-bank metadata[44] hold→hold−0.699ns;
175→100 output-bank request_toggle→request_sync[0]−1.249ns.
Worst crossing holds are source-bank metadata[60] hold→hold+0.138ns and
output-bank metadata[56] hold→hold+0.107ns.

## Identity, caveats, and archive

Partxc7z010clg400-1/Vivado2022.2/two threads, unchanged opt/place/phys_opt/route
strategy; actual inherited source100MHz period10ns and island175MHz period5.714ns
clocks remain. CDC17Info CDC-3/139Warning CDC-15/zero reported Critical,
114 missing input and124 missing output delays, no unclocked or unconstrained
internal endpoints. Clock-source/OOC/interface/reset/paused-slow-clock caveats
remain open. No RF or full receiver result is inferred.

Runtime source is the tested R/D/S/C/K/M/P1111111 eight-RTL closure from passing
actual50316, FW3bdaaf06440f969520acaa8828b6c39bc60dc820 /
HDL6923f5352951f8e03b9c29b6d4ef3c091a3cac90. Synthesis archive pins:
FW25737696ccd008270e0b109d71ad96d694716c1f /
HDL57322987e9e188dcd20a6cc2cac0a3f6b6404a93.

Input DCP2171713bytes:
`41c756bdc45635b1107d73ad741826e5a8f8fa276dc159468ec2355c16203aa6`.
Routed DCP3531537bytes:
`d15a91f070405f97382096ba5000e8a8a828b540f6939ad60507892c56684ad8`.
Owner5938ff6c7141676e3629547196e1d5aec57f5bd77c8df2fbe76edbc01e6873de,
unchanged Tcl0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a.

Originals: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-route-v1`.
Portable archive: `hdl/library/starlink_pss_acquisition/evidence/producer-final-route-v1`.
All raw products, owner receipts/logs, input DCP/Tcl, exact source manifest,
independent audit/path summaries, and bounded prior ROM comparison reports are
included. This concludes the bounded P1 trial; no further physical run is made.
