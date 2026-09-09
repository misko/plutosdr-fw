**GLRT implementation and Ethernet deployment — all five source rates commissioned, 9 September 2026**

The 2.5, 5, 10, 25 and 60 MS/s images have passed bounded Ethernet commissioning, including
RX PN calibration, continuous IQ, scored-event transport and finite GLX1 closure.
Exact original persistent v0.47 rollback also passed. The 60 MS/s image is
currently deployed and idle after short, ten-second and thirty-second captures;
the final U-Boot comparison matches the original baseline. Each 60 MS/s long
run retained two busy rejections, both expired candidates. Complete transport
does not imply loss-free detector scheduling or live-detector qualification.
The 25 MS/s interruption/stall controls and normal recovery remain preserved.

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
| `glrt-eth-r10000000-v1` | `ec87261da8d0ec0dda58b0ce6a5e9adeb2097bb6` | `93a343f2971762f7c8c3d0dba0d9a5934b9e3986` | +0.055 / +0.035 ns | Deployment/PN passed; short 34-event and ten-second 100 MB/2,549-event captures passed |
| `glrt-eth-r25000000-v1` | `4cd97a03315a518ff258c54381d4034391da668f` | `93a343f2971762f7c8c3d0dba0d9a5934b9e3986` | +0.004 / +0.025 ns | PN/short, 100 MB ten-second and 300 MB thirty-second captures passed; intentional errors retained, normal restart and idle checks passed |
| `glrt-eth-r60000000-v1` | `5e28d175d58d7aad73a714017624c74e2bf34e93` | `93a343f2971762f7c8c3d0dba0d9a5934b9e3986` | +0.075 / +0.017 ns | PN/short, 100 MB ten-second and 300 MB thirty-second captures passed; two candidate expirations in each long run retained; final idle/U-Boot verified |

All source rates export fixed 2.5 MS/s CI16 IQ through the dedicated GLRT DMA.
GLR1 stays immutable; additive GLX1 attests native endpoints, staged complete
vectors and finite closure. Public source geometry is checked before RF writes.
The frozen normal detector profile remains `glrt-upper-candidate-v1` with FPGA
gates 13107/19661/9831 and host gates 0.175/0.025.

The new [hardware evidence index v4](/srv/bulk/leo/glrt-deployment-20260909/hardware-evidence-index-20260909-v4/REPORT.md)
links all twenty-three completed capture attempts across five source rates,
thirteen independent host comparisons, deployment/rollback/current-state
receipts and 409 verified source hashes. It preserves eighteen complete captures,
three ordinary failures, two intentional failures and the unchanged earlier
v1/v2/v3 indexes. The two corrected 2.5 MS/s long runs
saved 100 MB in 10.069882 and 10.068877 seconds. The 5 MS/s short run saved
1.2 MB and nine normal-profile score records; its long run saved 100 MB in
10.065150 seconds with all 1,560 score records and clean IQ/event/closure checks.
These records are scores, not claims of pilot detections.

The 10 and 25 MS/s ten-second captures each saved 100 MB in 10.061013 and
10.068624 seconds respectively, with all 2,549 and 3,497 scored events, clean
IQ/event/closure accounting, and zero recorded faults, DDC clipping, busy
rejections or pending work. Their short captures each saved 1.2 MB with 34 and
50 scored events after a passing rate-specific RX PN eye.

The 25 MS/s thirty-second capture saved all 300 MB and 10,381 events in
30.181149 seconds, with clean IQ/event/closure accounting and output FIFO high
water one. Intentional controls then exercised the frozen normal gates with a
three-second request. Operator interruption after 2 MB caused a graceful child
SIGINT exit without kill escalation; its incomplete 4 MB capture remains failed.
A measured 150.129545 ms consumer pause preserved all 30 MB and 1,002 events.
A measured 700.112501 ms pause overflowed the output FIFO: 1,500,256 words
reached AXIS but 1,500,000 were saved. Its 6 MB capture correctly failed IQ
attestation while all 197 events and detector closure drained. Each operator
retained its outcome and verified idle buffers, exact FIT and TX safety afterward.
The following normal one-second restart saved all 10 MB and 335 events in
1.042284 seconds with clean accounting, without a reboot. These specific pause
outcomes do not establish a general latency tolerance or throughput headroom.

At 60 MS/s, the RX PN eye passed at 174 points with selected delay 0x08. The
short capture saved all 1.2 MB and 44 events in 0.144471 seconds. The ten-second
and thirty-second captures saved 100 MB/3,635 events and 300 MB/10,824 events
in 10.064262 and 30.199252 seconds respectively. Both long runs recorded two
busy rejections, all attributed to expired candidates. They still satisfy exact
IQ, scored-event and finite-closure accounting, with no pending work, incomplete
tails or DDC clipping. These recorded scheduling losses remain a limitation.

The separate 120 ms decisions-off control used acquisition zero and exact/margin
65536, with an explicit transport-only purpose. All 320 hardware event records
matched the frozen integer oracle's energies, peaks, bins, shift, flags and Q16
scores exactly; none lacked saved native support. This is conditional arithmetic
at recorded epochs, separate from blind acquisition. See the
[arithmetic report](/srv/bulk/leo/glrt-deployment-20260909/hardware-2500000-event-control-v2-oracle-v1/REPORT.md).
The [blind 2.5 MS/s host run](/srv/bulk/leo/glrt-deployment-20260909/host-live-v2-2500000-10sec-v1/summary.json)
completed all 1,000 overlapping windows without multi-frame positives; the
[5 MS/s short host run](/srv/bulk/leo/glrt-deployment-20260909/host-live-5000000-120ms-v1/summary.json)
completed twelve windows without multi-frame positives. The completed 10 and
25 MS/s host analyses each cover twelve short-capture windows and 1,000 long-run
windows. All eight normal-profile comparisons report no multi-frame host
positives, no comparable FPGA positive events and `agreement_observed=false`.
They still retain unmatched individual-frame engineering supports: the long
runs have 1,392 / 1,493 / 1,478 / 1,512 at 2.5 / 5 / 10 / 25 MS/s respectively.
Those overlapping hypotheses are not independent trials or calibrated RF truth.
The [25 MS/s long comparison](/srv/bulk/leo/glrt-deployment-20260909/compare-live-25000000-10sec-v1.json)
preserves that distinction; live pilot agreement remains unproven.
The new thirty-second and restart replays add 3,000 and 100 windows, still with
zero multi-frame host or comparable FPGA positives and `agreement_observed=false`.
They retain all 4,602 and 147 unmatched individual-frame supports respectively.
The final [60 MS/s blind analysis](/srv/bulk/leo/glrt-deployment-20260909/analysis-live-60000000-all-v1/REPORT.md)
covers 12 / 1,000 / 3,000 windows for the short / ten-second / thirty-second
captures. None contains a multi-frame host or comparable FPGA positive, and
all comparisons retain `agreement_observed=false`. They preserve 21 / 1,641 /
4,641 unmatched in-band individual-frame supports and 3 / 578 / 1,859 excluded
out-of-band supports. Candidate expiry epochs are absent from the scored-event
stream, so the two losses in each long run cannot be assigned to specific host
hypotheses. Exported 2.5 MS/s IQ cannot reconstruct exact native 60 MS/s arithmetic.

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
`896190f` includes exact 60 MS/s profiles and the `c539bd0` timeout cleanup:
bounded SIGINT, kill only if needed, then read-only post-run idle/identity under
the held lock, retaining both process and cleanup failures. Its 225 deployment/
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

The [final read-only idle attestation](/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/device-tool-glrt-ethernet/artifacts/ethernet-canary-14/current-60000000-idle-state-v1.json)
completed at 07:17:37 UTC under the shared lock. It verifies exact 60 MS/s
firmware/FIT, serial and local USB 5-1, GLR1+GLX1, both buffers disabled, gigabit
full-duplex Ethernet, 60 MS/s / 2.4 GHz / 2 MHz / manual 30 dB / A_BALANCED /
ENSM RX, TXLO down and TX gain −80 dB. All eight requested U-Boot fields match the original
hash-verified baseline, with attr_name/attr_val absent. Pinned SSH trust remained
unchanged. Reading the public snapshot refreshes counters through the observational
GLR_LATCH; the check changed no RF, firmware, U-Boot or SSH-trust configuration.
The receipt SHA-256 is
`8514ff3a638309991e37f0725196f140d125a95e765678d347b9c67fd674de17`.
The radio lock was released after the check; no further radio operation was used
to produce the final local reports.

The [25 MS/s package review](/srv/bulk/leo/glrt-deployment-20260909/package-25000000-4cd97a03-v1/result.json)
binds the exact FIT/DFU/FRM and acknowledges the small setup margin. Internal
timing does not qualify the external RX interface: existing reset/Gray/ADI CDC
warnings, clock exceptions and unmeasured input/output-delay boundaries remain.
Each deployed rate has its own measured RX PN eye and bounded transport checks.
The final [60 MS/s package review](/srv/bulk/leo/glrt-deployment-20260909/package-60000000-5e28d175-v1/result.json)
binds assembly `e61b8f5457851ec9e1c091026dd6b1b4d881aef6` to the exact HDL/Linux
above and FIT SHA-256
`02c5dae000e7d0549eb52e757cff52d24d56a51f58d9cd00206840a99d011009`.
All 4,400 slices are occupied. Earlier 60 MS/s setup failures remain recorded:
`4cd97a03` at −0.199 ns and `6099b304` at −0.223 ns. No timing constraint was
relaxed to call the final implementation a pass.

The final HDL's [numerical attestation](/srv/bulk/leo/glrt-deployment-20260909/saved-upper-5e28d175-batch-v1/numerical-current-source-attestation.json)
binds the fifty-case matrix actually executed on `6099b304` through exact
elaborated-source identity, with current-source AXI/closure checks and all
twenty-four saved native 2.5 MS/s observations reproduced. This distinguishes
reused exact source evidence from rerunning a matrix on a different label.

The exact `4cd97a03` [five-rate synthetic matrix](/srv/bulk/leo/glrt-deployment-20260909/host-synthetic-five-rate-4cd97a03-seed29343-v1/summary.json)
passes the strong-frame and quiet-control gates. Weak/short cases remain
reported limits; diagnostic short-32 cases retain six FPGA positive events
without independent host matches.
Rolled pilots retain cyclic timing ambiguity and are not a certified negative
control or spacecraft/frame identity. Those limits are not erased by passing
transport or arithmetic. All captures use the observed post-boot 2.4 GHz LO,
2 MHz bandwidth, A_BALANCED and manual 30 dB gain with TXLO down; actual
antenna/LNB connection and IF remain unknown. Sensitivity, field false-alarm
rate and live pilot agreement remain unqualified; hardware-qualified flags
remain false.

Remaining detector and release qualification is separate from completed bounded
deployment: characterize or correct the observed 60 MS/s candidate expirations,
establish the connected RF feed/IF and use bounded, explicitly interpreted pilot
evidence to evaluate live agreement and sensitivity. External interface timing,
inherited CDC/reset limitations, weak/short/rolled diagnostics and field
false-alarm calibration remain explicit. Keep the current verified GLRT image
and exact registered return paths available while addressing those limits.
