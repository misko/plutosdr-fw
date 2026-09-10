# Inverse-only sealed-bank actual v2 — automation PASS

The separately authorized, original vendor evaluation **77697 exited 0**.
All HDL numerical/control/fault checks, the corrected source-frozen collector,
and after-run source/IP integrity checks passed. The earlier original **21014
remains an automation FAIL** with its own preserved archive and separate
post-hoc assessment; v2 does not rewrite that history.

This is a 175 MHz functional simulation of an isolated processing slice, not
physical timing, a continuous receiver/source stream, energy/scorer integration,
native fine/pilot concurrency, RF accuracy or deployment qualification.

## Execution and exact source

- Start `2026-09-10T16:16:12.061356Z`; end `16:20:12.853212Z`; elapsed 240.792 s.
- Original process exit 0; `run_status=0`, `after_status=0`; no launch or integrity
  exceptions. There was no timeout restart or retry of this process.
- FW source `fb186470204f314681a37c7fe2962d024e876e04`, preparation evidence
  `adfaa08bdb8455877a7bbce0175a2ea640fc64f9`; HDL unchanged
  `b26f56dd32106c8e91290d075255ac4a6b9ff72d`.
- Manifest `39b1c731eb6f001983d5e842b1861d059c6f1f7a9ad986c26cde2a341ed74853`;
  owner `46ecfe1c67c7c480be86bb7b27c7e698a11c485f62fcefe3da90c8dbce27e59f`;
  unchanged runner `23e9e9b989e35f013113bd6356288952bf05d58c57d7803c8baa1d74b8239972`.
- All 64 frozen inputs and their inventory match before/after. v2 differs from
  v1 only in the reviewed timing-parser source and its manifest hash; the same
  10 runtime modules, 21 compiled sources, 8 vectors, clocks and bounds apply.
- Generated FFT wrapper before/after/live SHA
  `a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`;
  unchanged factory `0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d`.
- Original successful `results.json` SHA
  `a597c7ed82f419454d86d2840066bc8277191a292b4fa777454ac52c7e042c18`.

## Observed result

All 11 old functional terminal markers plus local-admission and inverse-sealed
terminals passed. All 76 healthy jobs retain the immutable generated FFT timing:
config +3; input +5/+7…+517; raw output +1298…+1809; status +1300 (third raw
word). Forward commit stays +1810; inverse qualification/final private take is
+1810, certificate +1811, seal +1812, public commit +1813.

The event oracle verified **19,456 ordered words per forward/product/inverse
stream** and **16,986 output-derived sample scores** (oracle-only, no scorer RTL).
The ownership ledger verified all **38 inverse lifetimes / 19,760 events**,
once-only final take, full data/metadata/lease/ordinal and independent fast/slow
time ledgers. ACK-to-release is one fast edge; reusable follows one edge later.
The monitor recorded 7,765 current-veto and 186 held-final witnesses, and 76
owned-reservation edges. All old fault/reset assertions remain active.

Measured complete forward-pair intervals:

| Profile | Observed fast clocks | Maximum time | Original gate |
|---|---:|---:|---:|
| Nominal, 31 intervals | 4554–4555 | 26.029 us | <=4557 nominal; <=5215 absolute |
| Stalled, 5 intervals | 4827, 4827, 4835, 4827, 4828 | 27.629 us | <=5215 absolute |

These finite observations do not prove an unbounded throughput guarantee.
The nominal <=8 added-clock allocation is not a blanket stalled-history delta.
The existing 8192 guard, 25000 drain, 1500000 whole-bench, 24 fault-observation,
and 128–132 provisional-prefix gates were unchanged; observed prefix was 130.

The 155-bit old/default/active input-guard observer retained all unconditional
state/output checks: 1,180,858 pre checks, 1,180,857 post checks, 256 reset checks.
The final one-count difference is the existing same-slot final-receipt boundary,
not discarded comparison coverage. Recorded WDB history inspection for this
specific run is still pending; inventory selection alone is not that evidence.

Parent independently repeated the source-specific success-only audit: original
92874, exit 0. All frozen-result output, unique terminal, owner/source/IP and
before/after checks passed. All three CSV files are byte-identical to v1:

- Trace `b824b9cffa9cd28c7572f5a906efe92e589fa2775d59fef88b5d345274f682b4`.
- Arithmetic events `777d36224edd47910271b8ac6e1b74171a9ef72e7b3ae8fae615b6bd568bb16f`.
- Ownership protocol `7b96ace09355c6f11ba24e4a4717a4d561c9a00f3c5185ecbc7f5311f80fde87`.

## Preserved evidence

Raw root:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/inverse-actual-prepared-v2.g5UoQ9Ag/`.
Owner logs are in `inverse-sealed-L1E1-175-actual-owned-v2`; the complete project,
CSV, IP and WDB are under the prepared bundle. The unmodified WDB is 133,627,003
bytes, SHA `96418352ac9d6b2b9849bcad5a6d0dd3829ede343b0625dccb5d5bb86592171c`.

Archive: **210 safe unique regular members**, all hashes verified;
**140,855,181 bytes**, whole SHA
`236cedcd7f2c7fb29fb3f17e4f3e974b375335e13b6849380d3b6b5dc96ce11e`.
The original monolith is retained outside `/tmp` under recovery directory
`inverse-actual-v2-archive.mpXf42lD`. Four tracked <=40 MiB parts reconstruct
exactly using `20260910-inverse-sealed-actual-v2.parts.json` and the existing
`tools/starlink_reconstruct_archive_parts.py`. No oversized Git blob is added.

No additional vendor execution, synthesis, route, receiver integration,
radio/PPU write or automatic promotion is part of this result.
