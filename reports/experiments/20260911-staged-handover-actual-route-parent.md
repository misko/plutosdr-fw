# Staged FFT handover: actual tests pass; timing remains open

The simpler command controller is now integrated with the real generated FFT,
kernel/product buffer and inverse-output mailbox. This revision adds registered
admission/completion handover, writer-validated held reader metadata, and a
private payload selector independent of fault-gated publication valid. It keeps
all numerical checks, actual reader ACK ownership, and forward processing while
an older inverse result remains unread. No radio uses this experimental candidate.

## Verified in this revision

- Six real-FFT numerical/backpressure contexts pass. All **64,512 numerical
  records** independently match the pinned earlier actual-FFT reference.
- Both stopped-reader reset cases pass, including reset from either clock side,
  an unread old result, an aborted next transform, purge and fresh recovery.
- Seven actual RTL fault cases pass, including writer descriptor corruption,
  reader tag corruption and faults at admission, close, COMMIT, replay and final
  reader ACK boundaries. No post-fault publication or descriptor release.
- **290 regression tests** and **12 report-audit controls** pass. These are
  simulation/tool checks, not RF tests or additional physical implementations.
- Normal service remains 3655 fast clocks; the qualifying stalled case is 4927,
  below the unchanged 5215-cycle cap. A deliberately 9000-clock-stalled reader
  is checked separately without a real-time capacity claim.
- Source-matched synthesis and routing complete with the same device,
  diagnostic 100/175 MHz clocks, FFT configuration and route recipe. No new
  timing exceptions or changes to TX were used.

## Timing result and what it tells us

Timing **fails**: WNS **-3.970 ns**, TNS **-2566.980 ns**, 2261 failing setup
endpoints. Hold +0.065 ns and pulse +1.830 ns pass. All 8246 nets are routed
with zero routing errors. Resources: 2716 LUT / 5540 FF / 21 DSP / 15 RAMB18.

The first handover attempt (V2) passed numerics but routed at -5.429 ns because
a live writer-domain descriptor lookup fed reader registers. V4 instead captures
a writer-validated held bundle, then checks its identity locally in the reader
domain. This removes that live crossing, but does **not** establish CDC safety.
V4's WNS is better than V2, while total negative slack and failing endpoints
worsen; it is also worse than the preceding staged-output -2.726 ns baseline.
It is not accepted as an overall timing improvement.

The worst V4 path is now entirely in the fast domain: held phase → input
identity/validation → cutover fault logic → admission receipt. It has 11 logic
levels and 9.587 ns data delay, including 7.767 ns routing. Registering the
receiver of a receipt did not pipeline the wide logic that creates that receipt.
Writer descriptor validation and producer-transfer state also remain among the
top failing paths. Further TX removal does not target these paths.

## Next bounded step

1. Capture bank-local admission/completion facts while holding or reserving the
   relevant payload bank; prevent metadata from changing beneath validation.
2. Pipeline validation into an explicit ownership certificate. Separate private
   scheduling from public publication, keeping current-fault publication fences
   and reset/fault cancellation of every pending certificate.
3. Test faults on each new stage boundary, stale identities, paused readers,
   reset/restart and exact real-FFT numerics. Then route that subsystem again.
4. Only after subsystem timing and CDC/reset qualification, integrate and route
   the complete receiver; verify sustained native **60 MS/s fine search** plus
   the independent **2.5 MS/s CI16 IIO inspection stream** and actual RX calibration.
5. `.18` reversible canary, then `.17` via PPU Ethernet with pinned rollback;
   finish the 300-second scan with 120 ms valid dwells and blind host GLRT comparison.

Five critical CDC findings, 208 warnings and 114/124 unconstrained input/output
ports remain in this diagnostic route. No full-receiver, continuous-rate,
Ethernet or deployment claim follows from the passing simulations.
Production HDL gitlink, PPU, main branches and every radio remain unchanged.

## Preserved evidence

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Final runs: `staged-handover-actual-v4`, `staged-handover-synth-v4`,
`staged-handover-route-v4`. V1/V2 actual runs and failed V2 routing are retained;
V3 was preparation/lint only, not an actual run. All vendor handles are terminal.

Frozen V4 inventory: `e8a7f06591bf4ef518f3368b170123fefbf416dd2c498da505341bf0ba785eb8`.
Numerical CSV: `d2db7ef34c61ed38685f6e30d03cc2296842260b4a828da313d2bca56d02a7ba`.
Synthesis DCP: `fc78905dde068b4ae4b4a82ed2daa3898416068dc6ef827844762c74b4f5b610`.
Routed DCP: `818be35eaa91b228ac05d5c355d070efcfdd24ee65b23404be4a42b3f5e478db`.

[Verified source/results archive](20260911-staged-handover-evidence.tgz):
26,547,548 bytes, 10,430 regular members, each read-back checked by SHA256 and
size. Archive SHA256:
`d4f9ffe34f95272c5320c9fed6d0ed4c8dcae4adcfa876a7af5cd1775dab9113`.
Sources, actual logs/CSV, both physical attempts, audit results and test evidence
are included. Firmware/HDL remain on the separate remote
`codex/starlink-rx-only-do-not-merge-rom-prefetch` lane; no merge into main.
Implementation commits: firmware `9e24e032876fd379ab345b7961923abc452b50bf`,
HDL `ac06d966a0a670588e93411eaf5055d9a4089190`.
