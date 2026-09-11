# Inverse-output identity staging: functional pass, timing still fails

2026-09-11. DO NOT MERGE firmware/HDL into main. No radio/PPU access or
deployment. `.14`, `.20`, `.21` remain excluded. Native 60 MS/s fine search and
independent 2.5 MS/s inspection sources remain unchanged and required.

## Implementation and verification

The buffered forward reference now has a separately derived inverse-output
stage. It reuses the existing product identity stage to capture each output
word and its metadata together, then presents a held validation certificate to
the real output bank. Original RAM, reset receipts and actual reader ACK remain.
All 24 parent runtime modules are unchanged.

Only nonfinal words enter the private live stream. Retained replay supplies the
sole final word, and replay acknowledgment waits for its actual validated bank
write. First-word metadata write-through supports continuous refill. Current
publication vetoes remain; private-offer checking latency intentionally changes.

**1,200 distinct tests pass:** 1,171 regression (1,159 inherited + 12 new) and
29 evidence/mutation tests. The separate component run is not counted twice.
Four broken variants are rejected: early publication, bypassed certificate,
missing first-word write-through and premature final-slot retirement.

Both actual generated FFT runs independently match all **64,512 numerical
words** across seven streams against the frozen reference. Service is
**4,178 clocks / 23.874 us at 175 MHz**, one clock more than the buffered parent
and below the 5,215-clock budget. CSV ordering changes with the extra pipeline
stage, but every numerical field matches. This is not continuous native RX proof.

The actual-word observer checks 9,216 main and 25,800 auxiliary bank writes,
including 18/47 finals and 18/52 first-word refills. The auxiliary run retains
six earlier faults, eight reset boundaries and two positive delay cases, then
passes nine new output-stage cases: bad live/replay metadata, bad ordinal/LAST,
late status at publication, and either reset before or after publication with
the reader stopped. Each recovers with 512 correct fresh words and one release.

## Routed result

Unchanged Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe and FFT IP;
no timing exceptions or relaxed clock. Source-matched actual proofs precede route.

| Metric | Buffered parent | Output identity stage |
|---|---:|---:|
| WNS | -1.559 ns | **-1.406 ns** |
| TNS | -348.591 ns | **-324.725 ns** |
| Failing setup endpoints | 742 | **763 / 14,471** |
| LUT / FF | 2,735 / 5,800 | 2,712 / 5,891 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

WNS/TNS improve, but failing endpoint count increases slightly. All 8,554 nets
route without errors. Hold +0.034 ns and pulse +1.830 ns, no hold/pulse failures.
114 inputs and 124 outputs remain OOC-unqualified. CDC reports nine CDC-3 and
210 CDC-15 warnings; the two additions are source metadata receiver replicas at
bits 20 and 54. These replicas require full bundled-data/CDC qualification;
there is no waiver or full-board timing claim.

Worst path now runs from forward guard `fault_reasons_reg[2]` to `fast_fault_reg`,
through guard/control and output-ledger logic: nine LUT levels, 6.978 ns data
delay, 76.583% routing. **The candidate remains undeployable.**

Next investigate fault propagation through private-stage aborts. Test using the
registered global abort for private work, rather than feeding an already-known
guard fault through downstream fault reporting. Preserve local fault reporting
and immediate current publication vetoes. Prove that any additional private
work cannot publish, ACK/reuse or survive reset; then rerun actual arithmetic,
cancellation and routing. This proposed improvement is not yet established.

## Pinned branch and evidence

Branch `codex/starlink-rx-only-do-not-merge-output-identity-stage`:

- FW `0ad3ae560d5be6b11515da7a9b3b2d3d3b17b961`.
- HDL `61944956c1f95077e2e8235883df064bf3f3ce88`.
- Main inventory `3e808c99ca9f3b68c39d69ff1313af824cdc01b0997958b80e4cd5f88818eeb1`.
- Auxiliary inventory `93fc1df123749381c5add4aeccde5685f4ee8ecd8e6f69a26a47337e5ffcc8ce`.
- Routed DCP `83838aaa913f86bf32487f734042eedf8e6b005f77e8b2db7e8674006a88a36e`.
- [Read-back verified archive](20260911-output-identity-stage-evidence.tgz):
  15,451,421 bytes, 6,748 members;
  SHA256 `897504e58a2b738d2e875eddbd0d82b3ab6b6f43e95ca90d6420d2cda9e55c61`.
- [Archive receipt](20260911-output-identity-stage-evidence.json).

Prepared sources, actual numerical/log evidence, generated wrappers, both DCPs,
raw reports and tests are retained. Historical regression CSV/DCP duplicates
remain locally with a hash inventory. Primary HDL gitlink remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
Full receiver timing/CDC/reset, calibration, continuous RX and Ethernet/IIO must
pass before reversible `.18` canary, then `.17` Ethernet/PPU deployment.
