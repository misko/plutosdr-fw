# Retained-output overlap: independently checked scheduling study

**A credible architectural option, not implemented RTL or timing closure.**
Parent fully read the frozen recipe, 354-line ledger and complete test file.
Original parent83965 exited0: **111 passed in2.70 seconds**, with all three
source hashes unchanged before/after. Source FW
`db4945dd4b13dfa9e40325b72620f3543bf5664b` in the separate high-rate60-paired
DO-NOT-MERGE tree; HDL remains `ecbb3712965ff39b144b5adf84a2a262c6c53dff`.
The measured source is the immutable accepted L1 actual trace, not that tree's
native60 runtime and not the newer inverse-sealed candidate.

## What was reconstructed

The ledger reproduces all38 blocks/76 jobs in the accepted175/100 MHz trace:
core input/output/status/config timing, eager source capture/READY/full
visibility, forward/product/inverse publication, slow output read endpoints
and synchronized real reader ACK. A separate old-state/NBA reader recurrence
checks34 publication phases under both READY profiles. Trace/log and four
runtime/bench sources are pinned. Mutating their event/identity/CDC coordinates
is rejected; the CLI freezes its nine dependencies and refuses overwrite.

There are36 next-block opportunities. In every one, the next source is full
at inverse publication and the product input is drained. Nevertheless the
single result guard waits another904–905 fast cycles for nominal output ACK,
or1177–1178 under the bounded stalled profile. The original next-forward
dispatch is seven clocks after ACK. This is genuine measured serialization,
not evidence that a second FFT or sample bank is necessary.

## Conditional architecture and rate arithmetic

The proposed schedule transfers the published inverse result's consumer
obligation into a retained context, resets/prepares the current core context,
and runs the next forward while the old output drains. It retains the actual
final-read ACK; the next inverse waits for the old output bank and context to
be released. It does not use a fabricated reader ACK or overwrite old data.

The recipe froze a hypothetical8-cycle publication-to-forward dispatch and
one-cycle real-ACK-to-context-clear before evaluation. The unchanged observed
FFT service is1810 cycles per transform, with17 cycles between forward
publication and inverse admission. Thus the conditional full pair is3645
cycles, or3669 with the separately declared+24-cycle sensitivity. All512
next-forward input beats lie within the prior output's ownership interval
in every tested bounded profile/rate. This is a model result, not an observed
new core/guard implementation.

Canonical15 MS/s needs447 scores every29.8us even when the original receiver
stream is60 MS/s. Keeping3669 conditional cycles gives this planning comparison:

| Hypothetical compute clock | Pair time | Margin before29.8us |
| --- | --- | --- |
| 175 MHz | 20.966us | 8.834us |
| 140 MHz | 26.207us | 3.593us |
| 130 MHz | 28.223us | 1.577us /205 clocks |
| 125 MHz | 29.352us | 0.448us /56 clocks |
| 120 MHz | 30.575us | FAIL by0.775us |

The conditional floor is about123.12 MHz including the sensitivity, compared
with152.65 MHz from the original4549-cycle nominal pair. **125 MHz is not a
deployment recommendation**: it has little modeled margin.130–140 MHz is worth
evaluating after the RTL schedule is demonstrated. No clock, timing exception,
vendor configuration or acceptance threshold has been changed by this study.
The old measured routed delay cannot simply be compared against a slower period
to claim a new route pass; changed clocks, crossings and implementation need
fresh physical and full-receiver qualification.

## Safety and implementation gates

Parent checked the actual result-guard/scheduler source. Its ACK wait also
monitors late status/orphan events. The abstract model's `producer_closed`
Boolean does **not** prove safe raw-event cutover: a late old transform event
must never become a legal first event of the next forward. Required design
work is an explicit transfer receipt, reset/drain/cutover evidence, current
core versus retained consumer fault attribution, and retained lease/descriptor
and watchdog anchors. Per-transform reset must not clear old ownership or
common-epoch poison; common reset must require fresh reader purge before rearm.

Simply changing next_inverse fails the current sealed issuer's phase_lost and
raw_orphan checks; tying old release to the new guard_busy also stalls release.
Those contexts must be explicitly separated, not masked. A source-specific
default-off design comparing dual guards with a lightweight retained context is
the next authorized task; there is no runtime or vendor authorization yet.

The model uses the original eager producer, finite13/17 READY and ideal clocks.
It is not a continuous-native-source, arbitrary-stall, CDC/metastability or
RF/accuracy proof. Its per-publication25,000-fast-cycle reader cap is a
defensive offline bound, not the original bench's differently anchored
await_results deadline. The two-bit lease remains conditional on drained
references and a fresh reset epoch, not unconditional stale-ACK protection.

## Exact parent evidence

- Ledger SHA `f01cac350351235895a6a667d4230c5703d2022dfdeeff9e27cdb970cee1ee4b`.
- Recipe SHA `1fb118404547d0a3eb13f72d969a5ee80687aec5a388c285839106d1e7fcc688`.
- Test SHA `31ca2f8c1f163110789823761b52080cfd7b812b7f2e2395255af2b5e9acb879`.
- Parent log SHA `f038490afff97eafa4ac1d9548ac02323aaa1fd00bce6140d497ff2235efc5b4`;
  JUnit SHA `b2a8b67b02ee650c632ef86cdb7f62ab4ddfc191ef6fff09968aa068a6eadf39`.

Complete parent directory `output-overlap-parent.mi8Jsngm`, including CLI
ledger and frozen dependency snapshot, is preserved in
`20260910-output-overlap-parent.tgz`:90,690 bytes, SHA
`a10dc7644c4302da92ea853ffe86b0dc7a5f2052ca971d75fa2640bf5e380598`.
`tar -d` against recovery originals exited0. The35.7MB original trace remains
an external pinned dependency, explicitly not duplicated inside that snapshot.
No radio, PPU, production HDL gitlink or firmware-main change occurred.
