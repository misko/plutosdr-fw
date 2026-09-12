# Product-local framing verified; aggregate timing regresses — no promotion

Native 60 MS/s fine search and the independent 2.5 MS/s inspection stream remain
required. This experiment changes only the product publication framing boundary,
not RF arithmetic, clocks, PPU, the primary HDL gitlink or any radio.

## Implemented and verified

All 41 private-replay parent runtime modules remain unchanged. Two derived
modules (43 runtime files) introduce a product-specific permission excluding
only its own current framing fault and require known-good framing locally
before actual publication. Original global diagnostics/public eligibility and
every other fault veto remain. This explicitly preserves unknown-value rejection;
a naive removal of the shared check would not.

- Final regression: **2,232 passing tests**.
- Actual-bank comparison: 4,096 four-state small-bank cases and 2,304 native-width
  cases; all original controls/registers compared and fresh reads/ACKs verified.
  Both unknown-framing and other-permission bypass mutations are caught.
- Healthy actual FFT: **64,512 identical numerical words**, unchanged **4,178
  service clocks** and 18 product publications.
- Complete actual campaign: **88 cases pass** in 349.566 s. The independent
  original-publication observer checks 906,329 edges, 134 actual publications,
  and seven local framing rejections. All inherited fault/reset/stall,
  quarantine, arithmetic and recovery checks pass.
- A failed initial auxiliary run is retained: the inherited delay test forced
  only the old permission, leaving the new permission undelayed. Its ownership
  assertion correctly failed. Version 2 mirrors exactly one force/release pair,
  leaving RTL/assertions unchanged. The focused seven-case rerun passes
  150,694 checks, 25 publications and six local rejections before the full run.
- Initial component harness construction failures and their corrected coverage
  are also retained; see the source proof document.

## Physical outcome

The unchanged 100/175 MHz OOC recipe routes all 8,550 nets in 49.272 s without
routing errors. **Timing fails and aggregate results worsen.**

| Metric | Private-replay parent | Local framing |
|---|---:|---:|
| Overall WNS / TNS | -1.182 / -349.709 ns | **-1.482 / -682.285 ns** |
| Failing setup endpoints | 930 / 14,496 | 1,420 / 14,495 |
| Same-domain 175 MHz WNS | -0.970 ns | -1.482 ns |
| Product publication | -0.970 ns | -0.905 ns |
| Output publication | -0.618 ns | -1.015 ns |
| Kernel next-start CE | -0.364 ns | -0.806 ns |
| Kernel history | +0.375 ns | -0.337 ns |
| LUT / FF | 2,756 / 5,908 | 2,743 / 5,908 |

The product publication endpoint improves only 0.065 ns and still fails; its
new worst source is a registered result-guard reason, through nine LUT levels
and 6.567 ns of data delay. A changed worst source does not establish that every
path from the earlier framing source passes.

The overall worst is now **fast reset release → product-bank READY → product
identity refill capacity → kernel capacity/READY → forward replay read enable →
output-position CE**. Seven logic levels, 6.943 ns data delay, **80.039% routing**;
the fast-running net has 2,299 loads. This is a real same-clock path, not merely
an unqualified cross-clock metadata report.

Other endpoint slacks: kernel index +3.143 ns, descriptor CE/data +0.625/+2.849 ns,
product occupancy/identity +0.543/+0.869 ns, output occupancy +0.214 ns.
All physical publication replicas and 64 kernel next-start CE pins are included.
RAMB18/DSP stay 16/21. Hold +0.046 ns, pulse +1.830 ns; no hold/pulse failures or
loops. Nine CDC-3 / 208 CDC-15 / no CDC-10; the scalar fault still directly feeds
its synchronizer. 114 inputs / 124 outputs remain unqualified.

**Retain as a tested alternative, not a receiver promotion.** Do not accumulate
this aggregate regression into the deployment baseline merely because it is newer.

## Next engineering step

Evaluate a small registered-capacity/skid-buffer boundary on the replay-to-kernel
path, starting from a preserved baseline. Its purpose is to stop downstream
READY/reset capacity from propagating backward through multiple stages in one
clock; this is not permission to register READY without storage.

Before integration, prove accepted-word conservation, bounded occupancy, stable
data under stalls, refill behavior, descriptor/exponent/LAST consistency, both
reset inputs, fault-edge cancellation and no premature bank reuse. Retain
same-edge final publication vetoes. Budget any extra registers and latency, and
measure sustained service rather than assuming the old cycle count.

Then integrate the actual FFT and buffers and route the entire changed subsystem.
Compare all previous failing destinations plus the new buffer's paths and the
aggregate result. Native fine search and the inspection stream stay in scope.

Full board timing remains a separate gate at the actual 100/200 MHz clocks.
The 200 MHz IDELAY reference must not be lowered casually. Earlier lower-clock
full pipelines failed throughput; this short island benchmark does not supersede
continuous receiver, CDC/reset, 60 MS/s calibration or Ethernet/IIO qualification.

## Pins and deployment protection

Branch **codex/starlink-rx-only-do-not-merge-product-local-framing**:

- Source FW c8cd81e6dbcdb2025c10ec2e0ca02bc96699e4d2.
- Harness/evidence tooling FW cc55dd11b5c20d79d508f3942e96d90df5d88135.
- HDL 37b485b5b8e25d14e468ec222b16f64b7e71c8cb.
- Main inventory 4ec0871824ac7f60583ee184be0c886611be508661e81143c2ef5ee2baa9ce24.
- Accepted auxiliary inventory 84f9bea889dbbbaf2cb8abca67bf7f3d2794da48f6e575397a37e0babd97581f.
- Synthesis DCP 9325b0e7a8711756c5b6106ae225ca21c1e707cf4fce16e4829a4109d5dbd47e.
- Routed DCP 8480d32f1f582f0738718762351cce687a709d65efaeeb1f751bc94a2b36a597.

Primary HDL remains 0b4bf2f0fd8c58c79852266b07f9e95770f75f36.
No radios, PPU or main branch were modified. Deployment remains reversible PPU
to **.18 canary first, then Ethernet-only .17** after all release gates.
**.14/.20/.21 remain excluded.**
