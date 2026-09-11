# Product identity integration: numerical pass, READY-path timing regression

Branch `codex/starlink-rx-only-do-not-merge-product-validation-stage`:
FW `967db3daa1f69e9ac17960c33d1533c7afb0cb03`,
HDL `0705316ad41b7f056d6acaae82e28a4c9a4e8a13`.
**Do not promote or deploy. Functional tests pass, but routing is worse.**

## Integration and the rejected first attempt

The private product stage and identity-certificate mailbox are now wired to the
real FFT and buffers: 21 compiled runtime modules. Producer READY means actual
private-slot acceptance. LAST remains held until publication is authorized;
private RAM rewrites are not slot retirement or reader ACK. Stage faults feed
all existing product-fault summaries. Full top/bench inverses constrain changes.

V1's one-clock first-reference pause overflowed the real FFT return slot at
12.751429209 us (cycle 2232, forward guard reason 0x40). This exposes a fixed-rate
FFT coupling that the standalone buffer tests and 569 regressions did not catch.
Both simulations were rejected by the auditor; V1 was never routed.

V2 restores the component-tested first-metadata bypass, allowing continuous
one-word-per-clock capture while registering the wide comparison before the
buffer's publication/fault checks. Failed V1 and succeeding V2 evidence are both
preserved; the current source is V2, not the pause implementation.

## Functional evidence

**584 regression + 16 new evidence tests pass** (600 distinct cases).
Main actual FFT completes in 200.03 s with all **64512 indexed numerical results**
matching. Service is **3662/3662/4929/11729/3662/3662 clocks**, one clock longer
than the parent. The deliberate 9000-clock reader stall remains excluded from
the unchanged 5215-clock gate. Both 3,000,000 ns campaign deadlines are unchanged.

The main product witness checks 50863 captures / 50859 retirements / 50859
retained slots / 102 metadata-reference updates. The original forward-receipt
witness checks 500730 cycles with 98 pending windows. Full-width timestamps,
original ACK phase, numerical payload, reset and fault cases pass.

Auxiliary actual FFT completes in 112.59 s. It retains the six ACK and 12 forward-
receipt cases, then adds **12 product-stage cases**: known/X second/final metadata,
both reset sides at reference transfer and held LAST, healthy continuation,
vendor fault and unknown producer VALID. Each finishes with fresh 512 correct
reads and one actual release. The product witness checks 25055 captures / 25036
retirements / 25167 slots / 51 reference updates / 131 held-slot observations.
Capture/retirement differences are cancelled private words in fault/reset tests.
These counts are not RF frames or continuous receiver qualification.

Routing requires both successful, source-matched, freshly re-audited campaigns.
Missing or altered product-stage evidence cannot be hidden by removing an audit
field. Synthesis completes in 104.67 s with unchanged source receipts.

## Physical result and cause

Route completes in 47.52 s under unchanged constraints. All 8498 nets route
without errors, but setup regresses:

| Metric | Forward-receipt parent | Integrated product stage |
| --- | ---: | ---: |
| WNS (ns) | -1.567 | -4.115 |
| TNS (ns) | -497.191 | -3456.457 |
| Failing setup endpoints | 681 | 2297 |
| LUTs | 2716 | 2810 |
| Flip-flops | 5665 | 5781 |

21 DSPs / 15 RAMB18s; hold +0.058 ns and pulse +1.830 ns, no failures.
114 unconstrained inputs and 124 outputs remain; this OOC build is not board
or full-receiver signoff.

Worst path: reset release -> input fault checks -> final product-publication
authorization -> staged-product READY -> producer/arithmetic/joiner READY ->
forward guard/ROM control -> kernel-ROM protocol-fault register. It spans
**16 levels / 9.824 ns data delay / 7.322 ns routing (74.5%)**. Holding LAST
until authorized publication inadvertently fed that global authorization
backward into upstream flow control.

## Next bounded correction

Test **no simultaneous refill while the private slot holds LAST**, independently
of whether publication succeeds on the current edge. Keep actual LAST retirement
publication-qualified; the emptied slot becomes available on the next clock.
This should remove the publication decision from upstream capacity without
pausing the middle of the continuous 512-word FFT stream.

Prove subsequent product blocks cannot arrive before actual ownership return;
retain continuous nonfinal refill, metadata write-through and current fault/reset
veto. Exercise final retirement with queued offers, unknown/rejected authorization,
held-LAST faults/resets, back-to-back valid blocks and actual FFT service. Then
route again. No such correction is implemented in this checkpoint.

Native 60 MS/s fine search and 2.5 MS/s inspection are untouched. No radios,
PPU/main or primary production HDL changed. Full receiver timing/CDC/reset/board
clocks, real 60 MS/s calibration and sustained Ethernet/IIO still precede `.18`
canary and `.17` PPU Ethernet-only deployment with rollback. Final acceptance
remains 300-second scans, 120 ms valid dwells and blind host GLRT.

## Evidence and housekeeping

[Verified archive](20260911-staged-productidentity-evidence.tgz) and
[receipt](20260911-staged-productidentity-evidence.json): **21708528 bytes,
10105 members**, all read-back SHA-verified. SHA256:
`3fba1792846ac692727c2896e6637dad85571d999aeb2e905b39de04804672e5`.
Includes rejected V1, V2 actual campaigns, sources, synthesis/route checkpoints,
reports and test sources/logs/XML. Historical fixtures remain explicitly pinned
dependencies on the prior forward-receipt and component packets.

- V1 inventory: `c0dba8f66c700e5f8eec4a97689f404888c0e86e5b5d3407dfabb7870c80b126`.
- V2 inventory: `b84f82584aa9adfd144efb9a1e82ca1731af4cb00425d82e9cb491e577969e84`.
- CSV: `210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44`.
- Synthesis: `2a4378225b3468c9e7a89b2d67afcbe882458d052d9cebc60c5f620d7170da67`.
- Route: `765fe51161dfb0aa7f9f3250e54a0c77f3b58e4a3d2a7d1538b1a3993612fade`.

Worktree: `RECOVERY/product-validation-stage-worktree-v1`.
Artifacts: `/dev/shm/starlink-product-integrated.1FSkuP`; no live build remains.
Primary production HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

At 15 MB disk free, a completed synthesis scratch project was fully archived,
byte-compared, temporarily relocated, then restored and rechecked. All original
paths are present. The clean older guard-facts HDL checkout was made sparse,
excluding about 1.3 GB of tracked evidence copies recoverable from Git. Its
local/remote HEAD stays `82be254db13c20eb5aed72cd2010138cf334dfe2`; no user edits,
unique evidence or active build was removed. Final regressions pass afterward.
