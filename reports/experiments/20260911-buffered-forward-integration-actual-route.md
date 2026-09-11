# Buffered FFT integration: functional pass, routed timing fail

2026-09-11. DO NOT MERGE firmware/HDL into main. No deployment authorized by
this evidence. No radio was accessed; `.14`, `.20` and `.21` remain excluded.
The canary remains `.18`, followed by Ethernet/PPU deployment to `.17` only
after receiver qualification. Native 60 MS/s fine search and the independent
2.5 MS/s inspection stream remain requirements and have not been removed.

## Implemented and tested

The previously qualified forward-return RAM is now connected to the actual
generated FFT and real kernel/product/inverse pipeline in a separate
experimental top. All 22 reference runtime modules remain unchanged. The
added top is an exact invertible derivation: reserve storage before admission,
capture all raw returns, seal with the existing guard, replay elastically,
and hold phase ownership until actual product-bank acknowledgment.

The first main and auxiliary actual-FFT runs both pass. All 64,512 numerical
words across seven streams match the frozen actual-FFT reference; output
timestamps include three bases with high-bit patterns. Forward RAM replay is
also checked word-by-word. Service is 4,177 clocks, up from 3,663: 23.87 us at
175 MHz, below the 5,215-clock / 29.8 us canonical15 block budget. This does
not establish continuous receiver throughput.

The auxiliary run also passes six current-fault injections, eight reset
boundaries (each reset input, partial capture/unsealed/mid-replay/final-held),
delayed status and 128 clocks of replay backpressure. All rejected work is
quarantined and each case recovers with 512 fresh correct output words.

1,130 regression/source-boundary tests and 29 evidence tests pass: **1,159
distinct tests**. Of these, 1,115 are inherited reference/component tests, not
claims that every historical fault campaign ran on the new integrated top.

## Physical gate remains failed

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no exceptions:

| Result | Scalar-fault reference | Buffered integration |
|---|---:|---:|
| Worst setup slack | -1.283 ns | **-1.559 ns** |
| Total negative slack | -255.361 ns | **-348.591 ns** |
| Failing endpoints | 607 | **742 / 14,202** |
| LUT / FF | 2,759 / 5,795 | 2,735 / 5,800 |
| RAMB18 / DSP | 15 / 21 | 16 / 21 |

8,434 nets routed with zero routing errors; hold +0.058 ns and pulse +1.830 ns,
zero hold/pulse failures. Nine CDC-3 structures, 208 CDC-15 warnings; 114 inputs
and 124 outputs remain OOC-unqualified. No full receiver/CDC/board signoff.

Worst path is `engine_metadata_reg[42]` to completion snapshot bit 29:
7.149 ns data delay, six LUT levels, 83.214% routing. Buffering is functionally
correct in the tested cases, but does not close the remaining control paths.
The next reported violation involves inverse-tag checks into the inverse guard.

Next: prove phase-specific completion facts. Snapshot bit 29 carries the
descriptor/header preflight event, active in VERIFY_LEASE/ARM_JOB; completion
requests require ACK_DRAIN. Test removing this redundant private-snapshot
path and redundant invalid-snapshot control, while preserving every current
public fault veto, quarantine, product identity and ownership/reuse check.
Then rerun actual FFT faults/numerics and route. Do not relax clocks, discard
validation globally, add features, or flash this failing candidate.

## Pinned experiment and retained evidence

Branch: `codex/starlink-rx-only-do-not-merge-buffered-forward-integration`.

- Firmware commit: `46db23d6aaed3e012341c43b1b9d25fba6809603`.
- HDL commit: `2dce66a13ec3a556e5cea99ae154f981a5b27b64`.
- Main inventory: `f4b18fe4f9a10f4b1ebd69e4546d81b064863ea4894694838e1d912e52f5b860`.
- Auxiliary inventory: `3c99f0896db17caf863f323dec9de6d33533556ce621d4f32c83be493e4fc3f0`.
- Routed DCP: `c1c4774538511b8549f64a51c8f9de81e95241e88a730cb2d62d3ecb6f833f9c`.
- [Evidence archive](20260911-buffered-forward-integration-evidence.tgz):
  15,378,947 bytes, 6,655 members, every member read-back verified;
  SHA256 `513a061c010c69c73623f92c98231d538275c06a2be565f46ee61fe5de805652`.
- [Archive receipt](20260911-buffered-forward-integration-evidence.json).

Sources, full actual numerical CSVs, generated FFT wrapper, synthesis/routed
checkpoints, raw reports/logs, tests and detailed experiment documentation are
archived. Historical regression CSV/DCP duplicates remain locally with a
hashed omission inventory; they were not deleted.

The primary HDL pointer remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. No PPU/main change or radio access.
