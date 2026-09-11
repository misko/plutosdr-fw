# Current product-publication fence — 2026-09-11

Branch `codex/starlink-rx-only-do-not-merge-product-current-fence`.
DO NOT MERGE firmware/HDL into main. No full-receiver or deployment approval.
**Functional campaign passes; routed timing still fails. Do not deploy.**

## Implemented fix

Derive one top from the rejected local-fault pipeline. All 28 parent runtime
modules remain byte-identical. The sole behavioral change adds
`guard_offered_local_fault === 2'b00` to `product_commit_authorized`, retaining
the original forward-committed/current-external/latched-guard conditions.
The equality requires both current guard-local views to be explicitly clear;
X/Z does not authorize publication. This is tested in the selected offered-fault
summary profile; unselected legacy profiles are not newly qualified.

The original parent could transfer internal product ownership on an unexpected
FFT status edge before the guard fault latched. The new veto prevents that
transfer on the current edge. Private RAM may still accept/write the unpublished
final word; that is not permission to publish or reuse the bank.

The inherited 33-bit private fault capture and scalar global register remain.
New current events can reach the global indication one cycle later, while
already-latched guard faults keep their immediate route. The scalar register
still directly drives its two-stage CDC synchronizer; no combinational OR was
inserted before that crossing. Public output and completion expressions and
native-fine/inspection receiver sources are unchanged.

## Verification

**1,347 distinct tests pass:** 1,324 regression (1,306 inherited + 18 new)
and 23 route-evidence unit tests. The new gate test exercises 128 combinations
of known committed/external/latched-fault values and 0/1/X/Z on each guard-local
bit. A mutant removing the added veto is rejected. This table tests the actual
gate expression, not the full integrated CDC behavior. Route unit tests isolate
receipt/source admission; actual arithmetic is verified separately.

Both actual generated FFT campaigns match all **64,512 numerical words**
against the frozen original reference. All six healthy contexts retain
**4,178 service clocks**, 23.874 us at 175 MHz, below 5,215 clocks / 29.8 us.
The CSV hash remains unchanged. This is not continuous native RX proof.

The auxiliary campaign passes all **43 fault/reset/delay cases**: six original
forward faults, eight resets, two delays, nine output-identity boundaries,
six direct guard faults, all six previously incomplete local-fault boundaries,
and six additional current-product-fence cases. The formerly failing status
publication test now prevents new internal ownership.

Additional cases cover a duplicate status with otherwise valid payload,
unexpected raw output, frame start and duplicate input-job start at final
product publication; either reset is also asserted while a fault is pending.
Every case recovers with 512 correct fresh reads and one actual reader release.
Tests distinguish private writes, real product/output ownership, slow CDC
propagation and previously published good data with the reader held.

The auxiliary observers cover 501,624 fast cycles, 23 delayed global-fault
edges, 2,852 pending-fault checks and 2,858 latched-guard fault edges. They
observe one extra private forward capture and five private output writes,
without new ownership on the checked cancellation edges. The output identity
observer checks 37,680 auxiliary bank words, 73 finals and 76 first-word refills.
Main observations remain 88,545 cycles, 9,216 words, 18 finals and 18 refills.

Synthesis completed on the exact healthy source. The normal experiment runner
uses the corrected local-fault witness and all inherited auditors; it does not
use the frozen predecessor's defective parser. No simulation or regression
failures occurred in this campaign.

## Identities and remaining scope

Evidence root: `/dev/shm/starlink-product-fence.1PzVkOAM`.

- Main inventory `8ad0828780100466b1b384d97b8b18beb42e5ad59e37d18be9d639dd81673bea`.
- Auxiliary inventory `83a31ece8df45b3bb5a7815b915f00907346393cfd4680859274b42cdf8bee8c`.
- Actual CSV `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
- Synthesized DCP `e8381f799129ed4cd75ed10555351c448e1f4697ee5d419e66ab8d19fede5565`.

Use `product_current_fence_experiment.py`, `route_product_current_fence.py`,
`audit_staged_fft_route.py` and `record_product_current_fence_evidence.py`.
Native 60 MS/s fine and independent 2.5 MS/s inspection remain mandatory.
Full receiver timing/CDC/reset with real clocks, 60 MS/s calibration,
continuous RX and sustained IIO/Ethernet must pass before pinned reversible
PPU deployment: `.18` canary, then `.17` over Ethernet. No radios or PPU/main
were touched. `.14/.20/.21` remain excluded; primary HDL is not promoted.

## Routed result and next engineering gate

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no added timing
exceptions or clock relaxation. Source-matched complete actual evidence is
re-audited before and after routing the exact synthesized checkpoint.

| Metric | Last routed registered-abort reference | Pipeline + current product fence |
|---|---:|---:|
| All-path WNS | -1.414 ns | -1.224 ns |
| All-path TNS | -321.485 ns | -519.788 ns |
| Setup failing endpoints | 653 / 14,439 | 1,217 / 14,494 |
| 175 MHz same-domain WNS | -1.357 ns | -1.174 ns |
| LUT / FF | 2,705 / 5,878 | 2,780 / 5,907 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Worst slack improves, but total negative slack and failing endpoint count
worsen. This is not an overall closure claim. The rejected intermediate local
pipeline was not routed, so this comparison cannot isolate either change's
individual timing effect. The publication fix must not be removed for timing.

All 8,591 nets route without errors. Hold +0.052 ns and pulse +1.830 ns have no
failures. 114 inputs / 124 outputs remain OOC-unqualified. CDC reports nine
CDC-3 and 208 CDC-15 warnings, no CDC-10; the scalar fault register is verified
as the direct synchronizer source. Bundled-data/real-board qualification is
still required.

All-path worst crosses output descriptor bit 52 into the slow reader:
zero logic levels, 1.102 ns data delay. The genuine same-clock worst starts
at `registered_scheduling.engine_metadata_reg[2]/C` and ends at forward guard
`active_private_reg/D`: 13 logic levels (six carry stages), 6.883 ns data delay,
63.910% routing. It traverses forward-bank descriptor validation/readiness and
guard control. The underlying current/fault dependency remains too long.

Next isolate that private forward-bank identity/fault boundary. Prove which
facts can be captured locally before reaching guard/control without allowing
bad final capture, seal, publication, ACK or stale reuse. Preserve the current
product veto and exact numerical/service tests. Any delayed private checking
needs explicit fault-edge and reset proof, then a fresh actual campaign and
same-recipe route. In parallel with that engineering work, the held metadata
crossings need ownership-based qualification, not blanket false-path masking.

Routed DCP: `9b59cb8cf1ec14ddf110bd962f46a41d02e6117dbc5f508a9ddea184cc356505`.
