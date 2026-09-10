# Product-local publication trial: timing failure, not promoted

The one diagnostic route completed but **timing fails**. Parent independently
verified the completed15-product inventory, source hashes, unique marker and
reported timing/resource tables. No retry, new timing exception, radio operation
or runtime promotion followed.

| Scope | Setup WNS ns | TNS ns | Failing endpoints | Hold WNS ns |
| --- | ---: | ---: | ---: | ---: |
| Global | -1.492 | -441.681 | 591 | +0.058 |
| 175MHz internal | -1.492 | -334.498 | 448 | +0.058 |
| 100MHz internal | +2.246 | 0 | 0 | +0.100 |
| 100 to175MHz | -0.699 | -14.925 | 54 | +0.138 |
| 175 to100MHz | -1.249 | -92.257 | 89 | +0.107 |

All6916 routable nets complete; zero routing/hold errors. Routed utilization is
2116 LUTs,4692 FFs,1157 slices,58 control sets,21 DSPs and15 RAMB18s. The prior
ROM route was -1.360ns: this trial is0.132ns worse, not a timing improvement.
Crossing values retain the unchanged diagnostic constraints; they do not prove
CDC correctness.114 missing input/124 output delays and CDC review remain open.

## What the measured paths show

Worst path: `product_bank/metadata_in_hold_reg[12]/C` to
`result_guard/active_private_reg/D`, nine LUT levels,7.154ns data delay
(1.572ns logic +5.582ns routing). It passes through full product metadata
comparison, current framing-fault logic and global result-control logic.
Second: product metadata-out[34] to result-guard awaiting-ACK, -1.410ns,
through input identity/current-fault validation. Narrowing the final publication
enable did not remove those long chains. The original numerical/validation
checks were deliberately retained; their removal is not an acceptable fix.

The next bounded design task is staged product validation/certification, using
the already tested sealed-bank checker and explicit private/public ownership.
It must cover both product-write metadata checking and product-read identity
checking, account for remaining paths and added service latency, and preserve
every per-word check and fault-before-publication guarantee. Simply delaying
the shared live-fault signal is not authorized. Inverse-bank actual-core
preparation continues independently; no untested source union is implied.

## Exact evidence

Original63593 exited0, started2026-09-10T15:28:35.593055Z and
ended15:29:36.871652Z,61.278593 seconds. Zero tool exit establishes a recorded
diagnostic only. Source/input/prepared pins are in the
[product-final review](20260910-product-final-fence-review.md).

Input DCP2171713 bytes, SHA-256
`41c756bdc45635b1107d73ad741826e5a8f8fa276dc159468ec2355c16203aa6`.
Routed DCP3531537 bytes, SHA-256
`d15a91f070405f97382096ba5000e8a8a828b540f6939ad60507892c56684ad8`.
Owner5938ff6c and route Tcl0873675f unchanged before/after.
Originals remain at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-route-v1`.

Full evidence/report is published on the ROM-alternative DNM branch at FW
`46fbe940f747cb7a9987d6c2c35acbb909cbe864` / HDL
`c144694706b0582668606b6224462c0e8850148d`. Owner push handles38775/71608
exited0 with matching remote heads reported. Parent independently verified the
committed archive `library/starlink_pss_acquisition/evidence/producer-final-route-v1`:
36 payloads/37 tracked files, manifest
`6e86b29fa1a2e772db0fd1f22347d14e4a557559c25ab2d7398b60afb0b9a6b1`.
This includes the raw reports, owner evidence and failed routed checkpoint;
nothing was discarded or reclassified as passing.
