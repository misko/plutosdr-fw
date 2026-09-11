# Integrated product identity boundary — DO NOT MERGE experiment

Branch: `codex/starlink-rx-only-do-not-merge-product-validation-stage`.
Component parent FW `7d8550738e441df30078d5b87a1d3d3f3939fe40`, HDL
`1a9841dd868e4477f9928554fe07cda065af94dd`. Actual FFT runtime parent is the
forward-receipt candidate, FW `0e40f84933f942df232da9c01ff9420889579530`, HDL
`48d3dd376693b8c0e3adb9bfb451e01ee7dc58a1`.

## Integrated runtime and rejected pause

The product stage and staged-identity mailbox now connect to the actual FFT,
joiner/arithmetic and buffers. There are 21 compiled runtime modules, versus 19
in the parent. Arithmetic READY means private-slot acceptance. The slot holds
data/metadata/identity evidence together; a held LAST retires only on actual
authorized publication, not a private RAM rewrite. Source/output mailboxes,
reader ownership, original final framing/status checks and reset domains remain.

Stage faults join the existing `product_bank_fault` abstraction, so all its
current/sticky admission and guard consumers retain a complete product fault
view. Stage abort uses the RAM's own fault, not the combined alias, avoiding
self-feedback. Unknown raw RAM readiness fails closed; known-only slot readiness
avoids an unknown-control feedback loop through current publication vetoes.

**V1's first-reference pause failed with the real FFT.** Both simulations stop
at 12.751429209 us, main cycle 2232, with forward guard reason `0x40` (return-slot
overflow). The one-clock consumer pause backs up a fixed-rate FFT result stream.
The standalone mailbox tests and 569 regressions did not expose that coupling.
The evidence auditor rejects these simulations despite Vivado's zero process
exit status; this variant was never routed. Its prepared sources, logs and
synthesis checkpoint are retained as rejected evidence.

V2 restores the previously component-tested first-word metadata write-through:
when the first word enters RAM, the next private capture compares against that
word's metadata; otherwise it compares against the RAM's held metadata. This
preserves one-word-per-clock acceptance. The wide comparator still terminates
at a registered identity bit before buffer/publication fault logic. The cost
of the bypass and new registers must be measured, not assumed negligible.

## Verified results

V2 **584 regression tests pass in 79.61 s**, including 15 component tests and
the inherited receipt/evidence tests. **16 new evidence tests pass in 0.61 s**:
600 distinct cases across those two suites. Focused V1/V2 invocations pass
39 / 32 tests respectively; they overlap those suites and are not extra counts.
Complete top and bench inverses retain original checks/cases; numerical monitors
now count real product/forward acceptance rather than unaccepted valid offers.

Main actual FFT: **200.03 s**, all **64512 indexed numerical results** match.
Full-width timestamp contexts, original guard/receipt witnesses, reset, fault,
input-stage and preflight/publication cases all pass. Service is now
**3662/3662/4929/11729/3662/3662 clocks**, one clock longer than the parent.
The intentional 9000-clock reader stall is excluded from the unchanged
5215-clock coarse-service gate. Neither 3,000,000 ns campaign deadline changed.

Main product witness: **50863 private captures / 50859 retirements / 50859
checked slots / 102 first-reference updates**. No product-slot stalls occur
in the main campaign. Differences between captures and retirements are cancelled
private words at tested fault/reset boundaries, not publications or RF frames.
The actual registered certificate is compared against the original wide
metadata predicate at real RAM acceptance. The original forward receipt witness
checks 500730 cycles with 98 pending receipt windows; public ACK phase remains
exact and publication authority does not expand.

Auxiliary actual FFT: **112.59 s**. It retains six original ACK cases and 12
forward-receipt cases, then adds **12 product-stage cases**: known/X metadata at
second/final producer acceptance, both reset sides at first-reference transfer
and held LAST, healthy first-reference and held-LAST continuation, current vendor
fault and unknown producer VALID. Every case finishes with fresh 512 correct
reads and one actual release. The held-LAST cases exercise a 32-clock RAM-ready
stall before cancellation or healthy continuation.

Auxiliary product witness: **25055 captures / 25036 retirements / 25167 slot
checks / 51 reference updates / 131 held-slot checks**. Both runs prove private
slot conservation and original identity correspondence, with epoch cancellation.
These finite subsystem observations do not prove continuous native RX or RF
accuracy. Both source-matched outcomes and fresh re-audits are required for route;
missing or altered product-stage evidence cannot be bypassed by deleting a field.

Synthesis V2 completes in **104.67 s**, unchanged source receipts. Routing takes
**47.52 s** and all 8498 nets route without errors, but setup regresses sharply:
**-4.115 ns WNS / -3456.457 ns TNS / 2297 of 14138 failing endpoints**. Parent:
-1.567 / -497.191 / 681. Do not promote or deploy this implementation.

Resources: 2810 LUTs, 5781 flip-flops, 21 DSPs, 15 RAMB18s, no RAMB36s. Hold is
+0.058 ns and pulse width +1.830 ns, with no failures. There are still 114
unconstrained inputs and 124 outputs in this diagnostic OOC build. No clocks
were relaxed or new timing exceptions added; this is not board signoff.

The actual worst path starts at `epoch_barrier/fast_release_reg` and crosses
input fault qualification, final product-publication authorization, the new
`staged_product_ready`, producer READY, arithmetic/joiner READY and forward
guard/ROM control, ending at `joiner/kernel_rom/protocol_fault_reg/D`. It has
**16 logic levels / 9.824 ns data delay / 7.322 ns routing (74.5%)**. The new
final-slot retirement gate unintentionally puts the global publication veto
on upstream flow control, even though a held LAST has no next word in its block.

## Next bounded correction

Investigate **no same-edge refill of a held LAST**, while retaining its existing
publication-qualified retirement. Upstream capacity can remain zero throughout
the final-slot hold, independently of whether publication is authorized on this
edge. After actual retirement, the now-empty slot is available on the following
clock. This is different from the failed first-word pause: it must not insert
a gap into the continuous 512-word FFT output stream.

Prove that no subsequent product block is permitted before the actual bank's
ownership return, preserve simultaneous nonfinal refill and first-reference
write-through, and retain current fault/reset publication vetoes. Test final
retire with a queued offer, rejected/unknown authorization, held-LAST fault/reset,
back-to-back valid blocks and the actual FFT service deadline. Then route again.
No such correction is implemented in this checkpoint; the timing result above
must remain attached to the current source, not reinterpreted as a success.

## Deployment scope

Native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection remain
untouched. Full receiver timing/CDC/reset/board clocks, actual 60 MS/s RX
calibration and sustained Ethernet/IIO checks remain before reversible `.18`
canary and `.17` PPU Ethernet-only deployment with pinned rollback. Final
acceptance remains 300-second scans, 120 ms valid dwells and blind host GLRT.
No radios, PPU/main or primary production HDL changes in this experiment.

## Evidence and workspace recovery

RAM-backed artifact root: `/dev/shm/starlink-product-integrated.1FSkuP`.
V1 rejected inventory:
`c0dba8f66c700e5f8eec4a97689f404888c0e86e5b5d3407dfabb7870c80b126`.
V2 inventory:
`b84f82584aa9adfd144efb9a1e82ca1731af4cb00425d82e9cb491e577969e84`.
V2 numerical CSV:
`210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44`.
V2 synthesis DCP:
`2a4378225b3468c9e7a89b2d67afcbe882458d052d9cebc60c5f620d7170da67`.
V2 routed DCP:
`765fe51161dfb0aa7f9f3250e54a0c77f3b58e4a3d2a7d1538b1a3993612fade`.

`tools/package_forward_receipt_evidence.py --campaign productstage ARTIFACT_ROOT
OUTPUT.tgz` preserves both versions' sources, both simulations, synthesis and
the final route reports/checkpoint, tests and this document. Historical fixture
dependencies remain explicitly pinned to the prior forward-receipt and component
packets; this is not a standalone reconstruction of all historical fixtures.

The workspace reached 15 MB free. The finished ACK-combination synthesis project
was completely archived and byte-compared, temporarily moved to RAM, and then
restored and byte-compared again after recovering space elsewhere. Its extra
durable archive is `RECOVERY/ackcombined-synth-project-complete.tgz`, 22104265
bytes, SHA256 `e8fcdbccb47c277505b326055fbf183dedbf75e8975a1362ce9bb3099d334bcf`.
All original synthesis paths are present again.

The clean older guard-facts HDL worktree, local/remote HEAD
`82be254db13c20eb5aed72cd2010138cf334dfe2`, was changed to a sparse checkout retaining
the acquisition sources but excluding tracked evidence copies. This recovered
about 1.3 GB without changing any commit or deleting unique evidence. Excluded
files remain recoverable from Git; current regressions pass after the change.
No user edits or active builds were removed.
