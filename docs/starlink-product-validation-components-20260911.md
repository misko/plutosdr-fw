# Product-buffer validation boundary — component checkpoint, DO NOT MERGE

Historical component checkpoint. The integrated FFT rejected its one-clock
refill pause; see [actual integration and replacement](starlink-product-identity-integrated-20260911.md)
for the current write-through implementation and measurements.

Branch `codex/starlink-rx-only-do-not-merge-product-validation-stage`.
Parent FW `0e40f84933f942df232da9c01ff9420889579530`, HDL
`48d3dd376693b8c0e3adb9bfb451e01ee7dc58a1`.

**15 component tests pass. Not integrated into the actual FFT, synthesized or
routed. All 19 existing compiled runtime modules remain unchanged.**

## Why this boundary

The parent route's worst path starts in product block-start metadata, crosses
the product buffer's 70-bit identity/framing comparison and shared fault logic,
and ends in forward ACK state. It is -1.567 ns WNS / -497.191 ns TNS / 681 failing
endpoints. The next worst path crosses the same validation into kernel-output
control. Moving only the completion token did not close this feedback path.

The new private stage captures one product word, its metadata, ordinal/LAST and
a known-good identity bit together. The mailbox variant consumes this checked
bit instead of repeating a wide metadata comparison on the publication/fault
path. Original position, LAST, reset, RAM ownership, explicit final publication
and real reader ACK logic are preserved by a complete source inverse.

The certificate is an interface contract: it must belong to the same retained
word and reference epoch. It is not permission to trust a separate live bit or
to ignore corruption before capture. Unknown metadata yields no known-good
certificate; unknown nonfirst/final certificates fail closed in the mailbox.
The first word retains the original position/LAST-based metadata-load rule.

## One-clock reference update pause

The first word loads the mailbox's held metadata. Accepting the second word on
that same edge would compare it against stale metadata. V1/V2 proved a wide
write-through solution; the final V3/V4 component uses a **one-clock refill
pause on the first-word metadata load** instead. No 70-bit bypass mux is needed.
Subsequent words can retire/refill simultaneously. The consumer exposes its
actual `metadata_load` and held metadata; the stage adds no frame controller.

This trades a small, bounded scheduling delay for a simpler comparison path.
The complete FFT service-time cost must be measured after integration; no
unchanged-latency or physical improvement claim is made here. The stage declares
119 state bits (including the retained 70-bit metadata); mapped LUT/FF usage
and full-receiver resource fit are not yet measured. It adds no DSP or RAM
declaration and no clock domain.

## Final-word ownership

An explicit-commit mailbox may rewrite its unpublished last RAM word while
publication is not authorized. Such a rewrite must **not** consume the private
stage's final slot. The component harness retires a nonfinal word on actual
bank readiness, but retains LAST until final publication is authorized. A
bad final word remains held/unpublished until quarantine or reset cancels it.
The global fault bit is not simply delayed past publication.

## Component evidence

Final V4: **15 tests pass in 3.07 s**. Earlier V1/V2/V3 invocations each passed
10 tests; these are successive refinements, not an additional unique test count.
Their generated sources/logs and XML remain in the packet.

The actual mailbox and an independent original-comparator mailbox receive the
same staged words. For known traffic, controls and published payload match over
**57454 checked cycles**. Unknown identity cases deliberately require fail-closed
behavior, not general four-state equality with the old mailbox.

- 12 correct 512-word blocks: **6144 exact published reads** and ownership return.
- Continuous retire/refill, deterministic writer stalls and source gaps.
- **200-clock unpublished-final hold**, with no early request or read visibility.
- **420 bad metadata cases**: all 70 bits, at both second and final word, with
  known-bit corruption, X and Z injection.
- Six wrong ordinal/LAST cases at first, middle and final word.
- Eight held-final cancellation/recovery cases: reset, known/X/Z abort,
  X/Z producer valid and X/Z consumer readiness. Each is followed by a fresh
  correct block with no stale publication.
- Three direct actual-mailbox tests reject 0/X/Z final certificates.
- Two actual-mailbox startup tests reject non-explicit publication or an
  unsupported reset-release contract.
- Seven unsafe variants are rejected: unchecked identity, corrupted retained
  metadata, lost reset, lost abort, missing reference pause, dropped unpublished
  LAST, and bypassed consumer certificate.

Across the mixed positive/negative campaign: 118802 simultaneous refills,
297 held-word checks and 444 first-reference pauses. These counts include
negative test prefixes; they are not complete RF frames or receiver throughput.

## Integration gate

1. Insert the private stage between spectrum-product arithmetic and the product
   mailbox only. Keep original mailbox instances for source and inverse output.
   Feed arithmetic READY from actual stage capture capacity, not RAM readiness.
2. Connect the stage reference directly to the product mailbox's held metadata,
   and inhibit same-edge refill using its actual first-word metadata-load pulse.
   Preserve word/certificate coherence and common-epoch reset cancellation.
3. Keep bank input valid separate from private-slot retirement. Hold LAST until
   actual qualified publication; private repeated writes must not become extra
   arithmetic accepts, reader ACKs or buffer-reuse permission.
4. Include stage faults in the existing current/sticky fault and admission
   summaries consistently. Preserve all actual-bank framing and forward-handoff
   checks. Do not replace these with a delayed aggregate fault bit.
5. Update producer-side numerical logging to use the new actual acceptance edge.
   Add source inverses and live conservation/reference checks. Exercise first-
   reference stalls, bad/unknown metadata at stage acceptance, held-LAST faults,
   current vendor faults, fast/slow reset and fresh recovery with the real FFT.
6. Re-run both bounded actual FFT campaigns, indexed 64512-word numerical
   comparison and unchanged 5215-clock coarse-service gate. Measure any service
   change; do not extend the existing main deadline to hide it. Then synthesize
   and route under the same constraints before adding any features.

The one-word stage's input capture can precede a RAM write. Its validity is
private, not a product ownership certificate. The original 60 MS/s fine-search
and 2.5 MS/s inspection paths must remain intact during integration.

## Full deployment remains open

No radio, PPU/main or primary production HDL change. The actual FFT parent
remains the unpromoted timing-failing reference. Full receiver timing/CDC/reset/
board clocks, actual 60 MS/s RX calibration and sustained Ethernet/IIO checks
are still required before reversible `.18` canary, then `.17` PPU Ethernet-only
deployment with pinned rollback. Final acceptance remains 300-second scanning,
120 ms valid dwells and blind host GLRT comparison.

## Evidence locations

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-validation-stage-worktree-v1`.
Test root: `/dev/shm/starlink-product-stage.vi9yss`.
The component packet includes all four versions' generated sources/logs/XML,
current RTL/test source, the pinned original mailbox and the full prepared
19-module parent runtime. It makes no actual FFT or physical/deployment claim.
