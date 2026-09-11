# Product current-fault fence: functional pass, timing failure

**The reproduced internal-publication gap is fixed in this experimental top.
Routed timing still fails; no deployment or primary HDL promotion.**

The separately derived top requires both current guard-local fault views to be
explicitly clear before the final product write can transfer ownership. All
28 parent runtime modules stay byte-identical. The selected offered-fault
summary profile is tested; legacy profiles are not newly qualified.
The private fault pipeline and scalar registered CDC source remain intact.

## Functional evidence

**1,347 distinct tests pass:** 1,324 regression plus 23 route-admission tests.
The new actual gate-expression test covers 128 combinations including X/Z on
both guard-local bits, and rejects a mutant with the new veto removed. Route
unit tests check evidence admission, not physical or arithmetic correctness.

Both actual generated FFT campaigns independently match **64,512 numerical
words** against the frozen reference. Service is unchanged at **4,178 clocks /
23.874 us at 175 MHz**, below 5,215 clocks. This is not continuous native RX.

All **43 auxiliary fault/reset/delay cases** pass, including the previously
failing late-status product-publication edge and the remainder of the rejected
pipeline's six-case campaign. Six additional cases cover unexpected status,
raw output, frame start, duplicate input-job start and either reset with a
pending fault. They prevent new ownership and recover with 512 correct fresh
reads / one actual reader release. Private unpublished RAM writes are not
mistaken for ownership transfers.

The auxiliary observers cover 501,624 fast cycles, 23 delayed-fault edges,
2,852 pending-fault checks and 2,858 latched-guard fault edges. Extra private
work is exercised: one forward capture and five output writes. The independent
output identity observer checks 37,680 auxiliary bank words, including 73
finals and 76 first-word refills. Normal numerical/service behavior is unchanged.

## Route: mixed change, still failed

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, with no new
exceptions or relaxed clock. The exact source-matched synthesis checkpoint
was routed only after the complete functional campaign passed.

| Metric | Last routed registered-abort reference | Pipeline + current product fence |
|---|---:|---:|
| WNS / TNS | -1.414 / -321.485 ns | -1.224 / -519.788 ns |
| Setup failures | 653 / 14,439 | 1,217 / 14,494 |
| Same-domain 175 MHz WNS | -1.357 ns | -1.174 ns |
| LUT / FF | 2,705 / 5,878 | 2,780 / 5,907 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Worst slack improves, but total negative slack and failure count worsen. The
intermediate rejected pipeline was not routed, so these effects cannot be
attributed to the product veto alone. Do not remove that veto for timing.

All 8,591 nets route without errors. Hold +0.052 ns and pulse +1.830 ns have
zero failures. Reports show zero combinational/latch loops. 114 inputs and
124 outputs remain OOC-unqualified. CDC reports nine CDC-3 and 208 CDC-15
warnings, no CDC-10, and retains the scalar fault register as the direct
synchronizer source. Full mailbox/board CDC qualification remains open.

Overall worst is a held descriptor crossing to the slow reader. The genuine
same-clock worst runs from engine metadata bit 2, through forward-bank
descriptor validation/readiness, into forward-guard private-active control:
13 logic levels, six carry stages, 6.883 ns data delay (63.910% routing).
Next isolate that private identity/fault boundary while preserving current
publication vetoes, seal/ACK/reuse and reset proofs. Rerun actual arithmetic,
all fault boundaries and route after any change. Separately qualify the held
metadata crossings with real ownership/clock constraints, not blanket masking.

## Pinned artifacts and remaining deployment gates

Branch `codex/starlink-rx-only-do-not-merge-product-current-fence`:

- FW `919ad3b594468a5824f4303d50722b862c89ab53`.
- HDL `8cf551add4f4f1e0f11d7d6b5b8793d9ea1d3baf`.
- Main inventory `8ad0828780100466b1b384d97b8b18beb42e5ad59e37d18be9d639dd81673bea`.
- Auxiliary inventory `83a31ece8df45b3bb5a7815b915f00907346393cfd4680859274b42cdf8bee8c`.
- Routed DCP `9b59cb8cf1ec14ddf110bd962f46a41d02e6117dbc5f508a9ddea184cc356505`.
- [Read-back verified archive](20260911-product-current-fence-evidence.tgz):
  15,750,312 bytes / 9,547 members; SHA256
  `a76ee82dce92a680e51135ba0eb7c7a87ad2e7a53ec7473fa7a35ddb2b0f5b60`.
- [Archive receipt](20260911-product-current-fence-evidence.json).

Archive retains prepared sources, complete actual streams/logs, generated FFT
wrappers, both checkpoints, raw reports and tests. Primary HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Native 60 MS/s fine and independent
2.5 MS/s inspection remain mandatory. Full receiver timing/CDC/reset,
calibration, continuous RX and IIO/Ethernet must pass before reversible PPU
deployment to `.18` canary and `.17` outdoors over Ethernet.
No radios/PPU/main were touched; `.14/.20/.21` remain excluded.
