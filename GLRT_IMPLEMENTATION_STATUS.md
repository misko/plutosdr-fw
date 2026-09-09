**GLRT implementation and Ethernet deployment — active, 9 September 2026, 05:55 UTC snapshot**

The 2.5 and 5 MS/s images have passed bounded Ethernet commissioning, including
RX PN calibration, continuous IQ, scored-event transport and finite GLX1 closure.
Exact original persistent v0.47 rollback also passed. The 10 MS/s deployment,
PN and short capture passed; its ten-second capture is running at this snapshot.
The 25 MS/s image is packaged with frozen transition policies.
The 60 MS/s build still fails timing. Five-rate deployment and live-detector
qualification are not complete.

Implementation branch `codex/glrt-deployment-implementation` is in
`/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review`, based on firmware
`6e49144af`; review checkpoint `7dc653acd`. The persistent goal belongs to task
`01a08439-8ad1-7b41-af10-f6329917f083`. Original workspaces remain references.

The user authorized implementation, testing, deployment and verification using
Ethernet on a locally USB-connected receiver except
`1040007c4a94000211000b009186843ef2`. The selected receiver is
`winbond-db620818a328172c`, Ethernet `192.168.1.14`, local USB `5-1`.
All normal operations use Ethernet; exact serial, local USB recovery presence,
source/target FIT identities, idle buffers, TX safety and a shared ownership lock
guard transitions. The excluded receiver is not operated. Individual operator
captures are bounded to 30 seconds of output; no multi-hour RF campaign is used.

| Image | Exact built HDL | Exact Linux | Internal setup / hold | Current evidence |
| --- | --- | --- | --- | --- |
| `glrt-eth-r2500000-v1` | `625a93e7376727f78286785ef27190eb2dd7a719` | `36c6561f152a1e0ae635a77da2d120c71478e925` | +0.009 / +0.020 ns | Historical canary; exact return reconciled, short/backlog passed; superseded by AD9361-corrected v2 |
| `glrt-eth-r2500000-v2` | `625a93e7376727f78286785ef27190eb2dd7a719` | `93a343f2971762f7c8c3d0dba0d9a5934b9e3986` | +0.009 / +0.020 ns | PN, short capture, two 100 MB ten-second runs, 320-event control and original rollback passed |
| `glrt-eth-r5000000-v1` | `ec87261da8d0ec0dda58b0ce6a5e9adeb2097bb6` | `93a343f2971762f7c8c3d0dba0d9a5934b9e3986` | +0.013 / +0.017 ns | Deployed from restored v0.47; PN/short and 100 MB ten-second capture passed |
| `glrt-eth-r10000000-v1` | `ec87261da8d0ec0dda58b0ce6a5e9adeb2097bb6` | `93a343f2971762f7c8c3d0dba0d9a5934b9e3986` | +0.055 / +0.035 ns | Deployment, PN and 120 ms/34-event capture passed; ten-second run in progress, not yet qualified |
| `glrt-eth-r25000000-v1` | `4cd97a03315a518ff258c54381d4034391da668f` | `93a343f2971762f7c8c3d0dba0d9a5934b9e3986` | +0.004 / +0.025 ns | Independent package/PPU validation passed; 10→25, reverse and 25→2.5 fallback policies frozen |
| 60 MS/s, unqualified build | `4cd97a03315a518ff258c54381d4034391da668f` | Intended `93a343f2971762f7c8c3d0dba0d9a5934b9e3986`; no released package | −0.199 / +0.019 ns | Not eligible for deployment; isolated physical optimization in progress |

All source rates export fixed 2.5 MS/s CI16 IQ through the dedicated GLRT DMA.
GLR1 stays immutable; additive GLX1 attests native endpoints, staged complete
vectors and finite closure. Public source geometry is checked before RF writes.
The frozen normal detector profile remains `glrt-upper-candidate-v1` with FPGA
gates 13107/19661/9831 and host gates 0.175/0.025.

The [hardware evidence index](/srv/bulk/leo/glrt-deployment-20260909/hardware-evidence-index-20260909-v1/REPORT.md)
links all eleven completed capture attempts through 5 MS/s, original deployment
and rollback receipts, and 153 unchanged source hashes. It preserves eight
complete captures and three failed ones. The two corrected 2.5 MS/s long runs
saved 100 MB in 10.069882 and 10.068877 seconds. The 5 MS/s short run saved
1.2 MB and nine normal-profile score records; its long run saved 100 MB in
10.065150 seconds with all 1,560 score records and clean IQ/event/closure checks.
These records are scores, not claims of pilot detections.

After that index's cutoff, the [10 MS/s deployment receipt](/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/device-tool-glrt-ethernet/artifacts/ethernet-canary-14/rate10000000-forward-receipts/90bc2ad7-3b7d-4ae5-a422-ffad32f2bf58.json)
returned success with exact AD9361 firmware identity. Its calibrated
[short capture](/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/device-tool-glrt-ethernet/artifacts/ethernet-canary-14/captures/rate10000000-120ms-v1/summary.json)
saved 1.2 MB and all 34 scored events without failures. Its long-run result is
pending at this status snapshot and is not inferred from the short run.

The separate 120 ms decisions-off control used acquisition zero and exact/margin
65536, with an explicit transport-only purpose. All 320 hardware event records
matched the frozen integer oracle's energies, peaks, bins, shift, flags and Q16
scores exactly; none lacked saved native support. This is conditional arithmetic
at recorded epochs, separate from blind acquisition. See the
[arithmetic report](/srv/bulk/leo/glrt-deployment-20260909/hardware-2500000-event-control-v2-oracle-v1/REPORT.md).
The [blind 2.5 MS/s host run](/srv/bulk/leo/glrt-deployment-20260909/host-live-v2-2500000-10sec-v1/summary.json)
completed all 1,000 overlapping windows without pilot positives; the
[5 MS/s short host run](/srv/bulk/leo/glrt-deployment-20260909/host-live-5000000-120ms-v1/summary.json)
completed twelve windows without multi-frame positives. Live pilot agreement
remains unproven.

Failures remain part of the record. The initial v1 short capture saved its IQ
but failed final evidence with ENODATA before asynchronous IIOD teardown ended.
The initial v1 ten-second run saved 100 MB but failed when its quiet event socket
expired; its historical event-attested flag predates the correction and does not
override the failed status. The v2 ten-second attempt with 25,000-sample chunks
overflowed the 256-word output FIFO: 550,256 words reached AXIS, but only 550,000
were saved. Subsequent long runs use 250,000-sample chunks and four requested
kernel buffers (4 MB), with output FIFO high water one. This identifies the
observed FIFO failure, not a proven host/kernel/DMA root cause or throughput
headroom. See the [buffering comparison](/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/device-tool-glrt-ethernet/docs/glrt-ethernet-commissioning-evidence.md).

Collector checkpoint `cb7734c09` waits for the current visit's final evidence,
sets the quiet-event timeout before OPEN, and preserves unexpected late event
errors during cancellation. Only verified pending-refill cancellation errors
are ignored; 94 collector/binding/ABI tests pass. Device-tool checkpoint
`28b2eaa` includes exact 25 MS/s profiles and the `c539bd0` timeout cleanup:
bounded SIGINT, kill only if needed, then read-only post-run idle/identity under
the held lock, retaining both process and cleanup failures. Its 219 deployment/
operator tests and static checks pass. The
[operator runbook](/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/device-tool-glrt-ethernet/docs/glrt-ethernet-canary-runbook.md)
contains executable transition and capture commands.

The pre-deployment active RAM version was v0.48 direct-async-v3, while the
independently extracted persistent QSPI FIT was v0.47 direct-async-v2:
12,826,107 bytes, SHA-256
`7a198f961cd6765ebd831c21314baac0f962650541af671911c23e76db33cbc2`.
The successful rollback restored those exact persistent bytes and original
2R2T topology; it does not claim the preceding RAM bytes were restored.
Original U-Boot environment remains preserved. Its `/amba` PHY override does
not reach the GLRT kernel's `/axi` PHY; Linux `93a343f2` explicitly compiles
AD9361 in the dedicated DT. The original v1 unknown deployment receipt remains
unchanged alongside its separate successful read-only reconciliation.

The [25 MS/s package review](/srv/bulk/leo/glrt-deployment-20260909/package-25000000-4cd97a03-v1/result.json)
binds the exact FIT/DFU/FRM and acknowledges the small setup margin. Internal
timing does not qualify the external RX interface: existing reset/Gray/ADI CDC
warnings, clock exceptions and unmeasured input/output-delay boundaries remain.
Each new rate still requires its own measured RX PN eye and bounded transport
checks. The [60 MS/s audit](/srv/bulk/leo/glrt-deployment-20260909/board-60000000-4cd97a03-v1/full-audit/audit.tsv)
retains its failure; no timing constraint is relaxed to call it a pass.

The exact `4cd97a03` [five-rate synthetic matrix](/srv/bulk/leo/glrt-deployment-20260909/host-synthetic-five-rate-4cd97a03-seed29343-v1/summary.json)
passes the strong-frame and quiet-control gates. Weak/short cases remain
reported limits; diagnostic short-32 cases retain six unmatched host supports.
Rolled pilots retain cyclic timing ambiguity and are not a certified negative
control or spacecraft/frame identity. Those limits are not erased by passing
transport or arithmetic. All captures use the observed post-boot 2.4 GHz LO,
2 MHz bandwidth, A_BALANCED and manual 30 dB gain with TXLO down; actual
antenna/LNB connection and IF remain unknown. Sensitivity, field false-alarm
rate and live pilot agreement remain unqualified; hardware-qualified flags
remain false.

Remaining work is ordered: finish 10 MS/s long-run validation, then
25 MS/s with the same gates; close and independently audit 60 MS/s timing before
packaging or deploying it; preserve each rate's failures and successful receipts;
leave a verified GLRT image deployed. Live detector qualification additionally
requires a known RF feed and bounded, explicitly interpreted pilot evidence.
