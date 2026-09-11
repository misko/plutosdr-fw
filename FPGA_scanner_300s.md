# Paired FPGA PSS / host GLRT scanner — DO NOT MERGE firmware into main

Status: implementation started; hardware qualification is NOT complete.

## Current verified status (2026-09-11)

Update 2026-09-11, publication-specific fault scope: **496 tests** and **64512
actual FFT records** pass with unchanged service. The integrated controller,
actual FFT and buffers route, but setup regresses to **-1.888 ns WNS /
-598.888 ns TNS / 881 failing endpoints**, versus guard facts -1.340 /
-463.636 / 821. Do not promote or deploy. Authorization matches over 479822
checked cycles, with six new retained-fault/recovery cases. Failed V1 test
injection and corrected V2 evidence are both preserved. The critical path still
connects phase-dependent input identity and fault aggregation to publication;
83 fewer LUTs did not solve it. Next specify a registered validation/publication
boundary with explicit fault/reset cancellation, ownership and service cost,
then verify and route before features. Branch:
`codex/starlink-rx-only-do-not-merge-publication-fault-scope`.
Native 60 MS/s fine search and independent 2.5 MS/s inspection remain unchanged.
No radio, PPU/main or production HDL changes; all deployment gates remain open.
See [integrated test and route evidence](reports/experiments/20260911-staged-publicationscope-actual-route-parent.md).

Update 2026-09-11, preflight/publication ordering: **479 tests** and **64512
actual FFT records** pass with unchanged service. All 17 runtime modules are
unchanged from guard facts; no new synthesis/route or timing improvement is
claimed. With the next source block queued, inverse publication pauses for
1025/1024/1024 observed clocks without early preflight or producer reuse.
Across 419084 phase observations, 3122 live replay observations have preflight
events known zero; 62 preflight observations overlap a published/unread bank.
Healthy resume, preflight fault and paused fast reset all recover cleanly.
This is source-bound finite evidence plus an abstract model, not RTL formal
signoff. It supports investigating a publication-specific current fault summary
while retaining registered preflight faults, diagnostics and unread-bank checks.
Branch: `codex/starlink-rx-only-do-not-merge-preflight-publication-proof`.
No radio, PPU/main, production HDL, native 60 MS/s fine-search or 2.5 MS/s
inspection change. Full receiver/deployment gates remain open.
See [ordering evidence and next implementation gate](reports/experiments/20260911-staged-preflightpublication-proof.md).

Update 2026-09-11, bank-local input identity: **480 tests** and **64512 actual
FFT records** pass with unchanged service intervals. The default/enabled real
checker matches in four-state and sequential tests; the live original checker
witness matches for 421667 observations. Both owners pass selected/unselected
metadata-corruption and fresh recovery cases. Routing is not an improvement:
**-1.940 ns WNS / -579.273 ns TNS / 785 failing endpoints**, versus parent
-1.340 / -463.636 / 821. Retain as a tested alternate; do not promote.
Worst path now goes from held source metadata through preflight comparison and
shared faults to output publication. Investigate the complete preflight/
publication ownership boundary before another local refactor; core reuse is
not reader release, so phase-based exemptions need proof. Branch:
`codex/starlink-rx-only-do-not-merge-bank-local-identity`. No radio/PPU/main or
primary production HDL changes. Native 60 MS/s fine search, 2.5 MS/s inspection
and all full receiver/deployment gates remain required.
See [bank-local checker proof and route comparison](reports/experiments/20260911-staged-bankidentity-actual-route-parent.md).

Update 2026-09-11, bounded post-route physical optimization on retained
references: **19 tool/audit tests pass**, both implementation passes complete,
and source/checkpoint/constraint audits pass. No RTL or clock changes. Private
certification improves to **-1.364 ns WNS / -448.933 ns TNS / 704 failures**;
guard facts to **-1.307 ns global WNS / -457.279 ns TNS / 822 failures**.
Guard-facts same-domain 175 MHz slack is **-1.167 ns**, but its global worst is
now a held-metadata clock crossing. Neither closes timing or qualifies for
deployment; crossings and unconstrained I/O remain visible. Keep the physical
pass as a measured finishing step, not a replacement for shorter control paths.
Next investigate bank-local metadata checks followed by one-bit selection,
preserving four-state behavior and current fault/reset vetoes. Branch:
`codex/starlink-rx-only-do-not-merge-postroute-physical`. No radio, PPU/main,
production HDL, native 60 MS/s fine-search or 2.5 MS/s inspection changes.
See [post-route comparison and next boundary](reports/experiments/20260911-staged-postroute-comparison.md).

Update 2026-09-11, private inverse input observations: **533 tests** and
**64,512 actual FFT records** pass with unchanged service intervals. Across
543,731 monitored cycles, all 424 private count/completion differences are
known-quarantined; five malformed/unknown-input cases recover cleanly. Routing
regresses to **-1.645 ns WNS / -607.093 ns TNS / 1011 failing endpoints**.
Do not promote this experiment. Retain private-certification and guard-fact
references. The worst path now reaches output publication through reset-release
and shared input/guard fault logic; inspect that complete registered boundary,
not another isolated private enable. Preserve current-edge reset/fault veto,
real reader release and the existing service budget. Branch:
`codex/starlink-rx-only-do-not-merge-private-input-observations`.
No radio/PPU/main or primary production HDL changes. Native 60 MS/s fine search,
2.5 MS/s inspection and full receiver/deployment gates remain required.
See [private input proof and route regression](reports/experiments/20260911-staged-privateinput-actual-route-parent.md).

Update 2026-09-11, private inverse ACK retirement: **514 tests** and **64,512
actual FFT records** pass with unchanged service latency. Original-guard public
and diagnostic outputs match across 501,911 cycles; 306 private occupancy
differences are known-quarantined. Six new readiness-edge cases recover cleanly.
Route improves over handoff to **-1.617 ns WNS / -488.478 ns TNS / 679 failing
endpoints**. Fewer failures than private certification, but worse WNS/TNS: retain
both, no overall best-reference or deployment promotion. Worst path now feeds
inverse private input accounting through input-identity/delivery qualification.
Investigate that boundary next without replacing certified delivery by a private
offer. Branch: `codex/starlink-rx-only-do-not-merge-private-ack-retirement`.
No radio/PPU/main or primary production HDL change. Native 60 MS/s fine search,
2.5 MS/s inspection and all full-receiver/deployment gates remain required.
See [private ACK proof and physical comparison](reports/experiments/20260911-staged-privateack-actual-route-parent.md).

Update 2026-09-11, whole held bank handoff: **496 tests** and **64,512 actual
FFT records** pass at unchanged service latency. The original-input bank and
441,088 rising-edge ownership/offer checks match; six new late-event, paused
replay and reset cases recover with 512 correct reads and one real release.
Route improves over metadata-only to **-1.868 ns WNS / -565.807 ns TNS / 720
failing endpoints**, but is still worse than private certification on all three
metrics. Do not promote as timing reference or deploy. Worst path now feeds
inverse awaiting-ACK through current input-identity validation; investigate
that exact ACK/reuse contract next, preserving current faults and real release.
Branch: `codex/starlink-rx-only-do-not-merge-held-bank-handoff`. No radio,
PPU/main or primary production HDL changes. Native 60 MS/s fine search,
2.5 MS/s inspection and every full-receiver/deployment gate remain required.
See [held handoff proof and physical comparison](reports/experiments/20260911-staged-heldhandoff-actual-route-parent.md).

Update 2026-09-11, held output-bank metadata: **479 tests** and **64,512 actual
FFT records** pass at unchanged service latency. An original-mux real-bank
witness matches through 385,028 writer-state observations plus reader, stall,
fault and reset checks. The metadata mux is removed in registered scheduling,
but routing **regresses to -2.203 ns WNS / -672.268 ns TNS / 796 failing
endpoints**. Do not promote; retain private-certification and guard-fact
references. The remaining phase -> bank framing -> completion -> phase path
requires examining the complete private-write/replay handoff, not metadata alone.
Branch: `codex/starlink-rx-only-do-not-merge-held-bank-metadata`. No radio,
PPU/main or primary production HDL changes. Native 60 MS/s fine search,
2.5 MS/s inspection and all full receiver/deployment gates remain required.
See [held metadata proof and route regression](reports/experiments/20260911-staged-heldmeta-actual-route-parent.md).

Update 2026-09-11, expanded guard facts: **464 tests** and **64,512 actual FFT
records** pass at unchanged service latency. Original and expanded certificates
agree for 384,922 live cycles; 32 fact-mapping fault injections block stale work.
Route is a **mixed result**, not a promotion: **-1.340 ns WNS / -463.636 ns TNS /
821 failing endpoints**, versus parent -1.452 / -451.168 / 704. Retain both
candidates. Worst path now reaches actual output-bank publication through
phase-dependent metadata selection/comparison and current fault checks. Next
inspect preparing and holding metadata before publication, retaining immediate
fault vetoes and real reader ACK. No added receiver features before closure.
Branch: `codex/starlink-rx-only-do-not-merge-guard-facts`. No radio/PPU/main or
primary production HDL changes. Native 60 MS/s fine search, 2.5 MS/s inspection
and all full-receiver/deployment gates remain required.
See [guard-fact proof and mixed route](reports/experiments/20260911-staged-guardfacts-actual-route-parent.md).

Update 2026-09-11, private descriptor certification: **new best measured
development reference**, with **449 tests** and **64,512 actual FFT records**
passing at unchanged latency. Snapshot/consume cancellation and six fresh-reset
recoveries pass. Route improves to **-1.452 ns WNS / -451.168 ns TNS / 704
failing endpoints** (parent -2.047 / -550.201 / 825). Still NOT timing-closed or
deployment-qualified. Worst path now ends at completion snapshot bit 9 through
output-bank metadata and a compound guard-local fault predicate. Next split
those exact facts and inspect inverse retirement, retaining all public vetoes.
Branch: `codex/starlink-rx-only-do-not-merge-private-certification`. No radio,
PPU/main or primary production HDL changes; native 60 MS/s fine search,
2.5 MS/s inspection and all full-receiver/deployment gates remain required.
See [private certification proof and improved route](reports/experiments/20260911-staged-certification-actual-route-parent.md).

Update 2026-09-11, private kernel sequence on final-capture candidate: **435
tests** and **64,512 actual FFT records** pass with unchanged latency. Hidden
bin/next-block state advances privately; public validation/completion and final
qualification remain. Six new actual fault/late-status/stall cases prove
quarantine, including a rejected final offer. Route has another mixed result:
**-2.047 ns WNS / -550.201 ns TNS / 825 failures**, versus parent -2.005 /
-634.847 / 856. Keep references; physical gate still fails. Worst path now feeds
descriptor certification through shared metadata/fault logic. Next separate
private descriptor preparation from admission permission with exact snapshot/
consume cancellation proof. Branch: `codex/starlink-rx-only-do-not-merge-private-kernel-sequence`.
No radio/PPU/main or primary production HDL changes; all native 60 MS/s fine
search, 2.5 MS/s inspection and full deployment gates remain required.
See [private sequence proof and physical comparison](reports/experiments/20260911-staged-sequence-actual-route-parent.md).

Update 2026-09-11, private adapter final-data capture: **417 tests** and all
**64,512 actual FFT records** pass with unchanged service latency. The private
69-bit bundle tracks only in EMPTY and freezes on original qualified acceptance
through real reader ACK/release. Routing has mixed improvement: **-2.005 ns WNS**
(reference -1.969), **-634.847 ns TNS** (reference -813.676), **856 failures**
(reference 914). Retain both candidates; no timing/deployment pass. Worst paths
now feed kernel ordinal and next-block identity through shared metadata/fault
qualification; inspect that boundary together before composing changes.
Separate branch `codex/starlink-rx-only-do-not-merge-private-final-capture`;
no radio/PPU/main or primary production HDL changes. Native 60 MS/s fine search,
2.5 MS/s inspection and full receiver/deployment gates remain required.
See [private final capture proof and mixed route result](reports/experiments/20260911-staged-finalcapture-actual-route-parent.md).

Update 2026-09-11, exact guard-facing fault summary on private-capture reference:
**64,512 actual FFT records** match, **397 tests** pass, and each guard's full
fault accumulator matches the original for 259,384 cycles. The real checker/
cutover proof covers 524,288 four-state cases. Service latency is unchanged.
Routing nevertheless regresses to **-2.566 ns**, TNS -921.237 ns, 958 failing
endpoints; keep the **-1.969 ns** reference. The worst path now ends at mailbox
final-data capture through bank metadata/fault/completion qualification. Next
inspect that complete local capture/ownership boundary before another route.
Separate DNM branch: `codex/starlink-rx-only-do-not-merge-fault-summary`.
No radio/PPU/main or production HDL changes; native 60 MS/s fine search and
2.5 MS/s inspection remain required. No deployment or physical signoff claim.
See [exact fault summary and routed comparison](reports/experiments/20260911-staged-guardfault-actual-route-parent.md).

Update 2026-09-11, private kernel ordinal on the better private-capture reference:
**64,512 actual FFT records** and the complete CSV match; **397 tests** pass.
Private/public handshake, fault-edge quarantine, late status and held-final
backpressure tests pass with unchanged 3659-clock normal service. Routing still
regresses to **-2.347 ns**, TNS -967.661 ns, 1093 failing endpoints versus the
reference's -1.969 ns / 914. Not promoted. The worst path now feeds guard fault
accumulation through input validation/cutover. Next investigate exact source-
local fault aggregation, preserving diagnostics and current publication/ACK
vetoes. Work is separately preserved on `codex/starlink-rx-only-do-not-merge-kernel-ordinal`;
staged-final work remains on its previous branch. No radio/PPU/main or production
HDL changes. All native 60 MS/s, 2.5 MS/s IIO and deployment gates remain required.
See [private ordinal comparison and next fault-path gate](reports/experiments/20260911-staged-ordinal-actual-route-parent.md).

Update 2026-09-11, clocked inverse-final validation: **64,512 actual FFT records**
match and **397 regression tests** pass. Eight new cases cover final snapshot/
consume faults, resets, late status and completion stalls. Private close is
separate from current-fault publication authorization. Normal service is 3660
clocks, still within 5215. Routing **regresses to -2.379 ns**, TNS -941.022 ns,
1038 failing endpoints versus private capture -1.969 ns / 914. Not promoted.
The worst path now feeds the kernel expected-bin index through shared fault
checks. Next inspect forward/kernel ordinal control with unchanged public
identity/backpressure/fault safeguards; compare against the better reference,
retest and route. No radio/PPU/main or production HDL changes. Native 60 MS/s
fine search, 2.5 MS/s IIO and every receiver/deployment gate remain required.
See [staged-final tests, retained failures and routed result](reports/experiments/20260911-staged-final-actual-route-parent.md).

Update 2026-09-11, private descriptor capture: **64,512 actual FFT records**
match and **382 regression tests** pass. Local ownership permits private payload
loading; accepted completion freezes the bundle through validation/publication/
real reader release. Actual tests cover invalid/X churn and fault-edge capture.
Routing improves from -3.251 ns to **-1.969 ns**, TNS **-813.676 ns**, 914 failing
endpoints, also improving on replay-only V1. Timing still FAILS. The worst path
now ends at a single completion-pending bit, not wide payload enables. Next
stage final validation/ownership transfer and awaiting-ACK controls together,
preserving immediate publication vetoes; retest and route before new features.
Native 60 MS/s fine search, 2.5 MS/s IIO and all receiver/deployment gates remain
required. No radio/PPU/main or production HDL changes.
See [private capture verification and timing result](reports/experiments/20260911-staged-capture-actual-route-parent.md).

Update 2026-09-11, private replay and staged writer validation: both actual-FFT
versions independently match **64,512 numerical records**. **366 regression
tests** pass, including replay-veto and pending-descriptor cancellation checks.
Private replay separation improves the route to **-2.265 ns**, TNS -1021.803 ns,
936 failing endpoints; adding the writer comparison stage regresses to
**-3.251 ns**, TNS -1733.553 ns, 1364 endpoints. Neither passes timing or is
promoted. The new worst path is fault-qualified completion acceptance driving
181 descriptor-register enables. Next separate private data capture from
authorization with explicit held-bundle stability, retest and reroute before
new features. Native 60 MS/s fine search, 2.5 MS/s IIO and every full-receiver/
deployment gate remain required. No radio/PPU/main or production HDL changes.
See [replay/writer verification and routed comparison](reports/experiments/20260911-staged-replay-actual-route-parent.md).

Update 2026-09-11, clocked completion/private ROM loads: all **64,512 actual FFT
records** match, including ten new completion-cancellation cases; **346 tests**
pass. The completion-only route regresses to -3.637 ns. The private ROM revision
routes at **-3.134 ns**, TNS -1304.699 ns, 1398 failing endpoints: mixed versus
the -3.080 ns admission baseline, and still FAILING. The worst path now feeds
publication-controller sequencing through preflight/current faults. Next inspect
private replay versus actual authorization, preserving request/ACK ownership and
current publication fences; retest and reroute before further features. No
radio/PPU/main changes. Native 60 MS/s fine search, 2.5 MS/s inspection and every
full-receiver/deployment gate remain open.
See [completion and private ROM evidence](reports/experiments/20260911-staged-completion-actual-route-parent.md).

Update 2026-09-11, clocked private admission and held lookup: all **64,512 actual
FFT numerical records** and the full reset/fault campaign pass, including six
new admission-cancellation cases. **321 tests** pass. Source-matched routing
improves from -3.970 ns / 2261 failing endpoints through -3.451 ns / 1602 to
**-3.080 ns / 1511**, TNS -1541.860 ns; timing still FAILS. The worst path now
feeds the completion receipt through input identity/fault logic. Next stage
producer-completion validation with explicit ownership/cancellation, then rerun
actual tests and route before further features. No radio/PPU/main changes;
native 60 MS/s fine search, 2.5 MS/s inspection and all deployment gates remain.
See [admission verification, physical comparison and next gate](reports/experiments/20260911-staged-admission-actual-route-parent.md).

Update 2026-09-11, registered FFT handover and held reader metadata: six actual
FFT contexts independently match all **64,512 numerical records**; both
stopped-reader reset cases and seven actual fault cases pass. 290 regression
tests plus 12 route-auditor controls pass. Source-matched routing still fails:
**WNS -3.970 ns**, TNS -2566.980 ns, 2261 setup failures. This is worse than the
preceding staged-output baseline, so no promotion. The live metadata lookup
crossing is removed, but input-validation/cutover logic still feeds admission
through an 11-level path. Next pipeline bank-local validation into explicit
ownership certificates, keeping fault/publication fences, then reroute before
new features. Native 60 MS/s fine search, 2.5 MS/s IIO and `.18`→`.17` deployment
remain open requirements. No radio/PPU/main changes.
See [handover verification and next timing boundary](reports/experiments/20260911-staged-handover-actual-route-parent.md).

Update 2026-09-11, actual staged-output integration: the new command arbiter and
real inverse-output buffer pass four generated-FFT contexts, with all **43,008
numerical records** independently matching the prior actual evidence. 259
combined tests plus nine audit tests pass. Source-matched routing still fails:
**WNS -2.726 ns**, TNS -1156.969 ns, 1110 setup failures. The old inverse-owner
endpoint is gone; the worst path is now metadata/shared-fault validation into
FFT cutover/reset state. Next stage that handover and restore/qualify the
reader-clock descriptor boundary, then rerun full reset/fault tests and routing.
No promotion or radio changes. Native 60 MS/s fine search, independent 2.5 MS/s
IIO and all `.18`→`.17` deployment gates remain required.
See [actual FFT integration and routed result](reports/experiments/20260911-staged-output-actual-route-parent.md).

Update 2026-09-11, staged command controller: implemented registered validation
and next-edge ownership application, with held responses and abort/reset
cancellation. 41 component tests and the full 231-test combined regression pass.
The registered-boundary probe now passes internal timing at 175 MHz:
**WNS +0.765 ns**, hold +0.132 ns, no violations. Controller resources are
182 LUT / 384 FF. This is **not** full-island or board timing closure; real
FFT/payload-bank integration and all 60 MS/s/IIO/deployment gates remain open.
See [staged command timing result and integration path](reports/experiments/20260911-staged-commands-timing-parent.md).

Update 2026-09-11, staged-control work: a separate compact descriptor-ownership
table now passes 36 tests, including stale-tag/abort/reset controls and RTL
mutants. Early registered-boundary routes fail at -0.012 ns and -0.246 ns;
the latter comparison rewrite is reverted. These are component-only probes,
not complete-island improvements. Next split command validation from ownership
application with a registered command/response contract, then integrate the
actual FFT/buffers. Source and failed physical experiments are preserved in a
verified 1859-member evidence archive. No radio or production promotion.
See [staged ownership prototype and next integration gates](reports/experiments/20260911-staged-descriptor-slots-parent.md).

Update 2026-09-11: the independent destination candidate passes actual FFT
simulation (all 77953 rows and previous results identical), 85 preparation
tests, 69 physical-policy tests and source-matched synthesis. Routing completes
but regresses to **WNS -3.106 ns**, 827 failing setup endpoints; hold passes.
It stays default-off. The next implementation is registered validation/control
boundaries with tagged, fault-safe certificates—not further unmeasured
combinational factoring. Full RX/IIO/board and `.18`→`.17` deployment gates remain.
See [destination actual/physical evidence](reports/experiments/20260911-destination-actual-physical-parent.md).

Update2026-09-11: bank-local identity now passes the actual vendor FFT campaign.
All77953 rows and every prior parsed result field match;3230028 full guard-field
comparisons pass. Independent64 actual preparation,80 physical policy and19 real
binding tests pass. Synthesis51543 completes with2354LUT4758FF21DSP15RAMB18,
source/resource/constraint audit PASS. Root route17298 completes but regresses:
**WNS-2.640ns**,TNS-1007.296ns,916 failing setup endpoints versus reference
-2.504ns/679. Hold+.044ns passes;7210 nets fully routed. Bank-local factoring is
not accepted as a timing improvement and stays default-off. Independent39 revised
contextual destination tests pass,144 source files unchanged; its separate actual
and physical qualification is next, with no presumed bank-local union benefit.
See [actual PASS and current physical gate](reports/experiments/20260911-bank-identity-actual-physical-parent.md).

The next default-off bank-local identity candidate passes independent **59 tests**
in18.81s,127 source pins unchanged. Full original guard state/output comparisons,
clocked and X/Z controls, fault/ACK boundaries and the complete seven-context
scripted replay pass in modes0/1: all77953 CSV rows and complete prior results
match. It moves source/product metadata comparisons before phase selection with
exact X/Z fallback. Subsequent actual PASS is recorded above; no new physical result.
See [bank-local candidate checks and remaining gates](reports/experiments/20260910-bank-local-identity-parent.md).

In parallel, independent **15 tests** pass the contextual destination-readiness
proof, including333056 aggregate comparisons and four executed fault/fallback
negative controls. The unrestricted shortcut is rejected by a real X-to-clean0
counterexample. Exact contextual runtime implementation is next, not yet tested
RTL or a timing result. See [contextual proof and limitations](reports/experiments/20260910-destination-context-parent.md).

The offered-summary candidate now completes source-matched synthesis and route,
but timing still FAILS: **WNS-2.504ns**,TNS-829.822ns,679 failing setup endpoints.
This improves from-2.697ns/848 endpoints, without closing timing. Hold+0.049ns
passes;7253 nets route with0 errors. Independent77 physical-preparation tests
pass. Worst paths now start in epoch release or held-phase state and traverse
destination/preflight/fault/admission logic. Source-bound review of that path is
next; no radio deployment is authorized by this result.
See [summary physical result and remaining critical path](reports/experiments/20260910-retained-summary-physical-parent.md).

The next retained offered-input fault-summary candidate passes parent **51 tests**
(6.96s),50 source pins unchanged. It includes the six scripted compositions,
real-input/XZ premises, old guard shadows and bounded current-fault/ACK module
tests. Independent graph replay now passes5347 nodes/69LS,19 retained roots,
11 excluded echoes, nine source mutants and ten parser controls;27 inputs stay
unchanged. Actual vendor FFT replay now PASSES: root84113 exit0 in59.09s,
all77953 CSV rows byte-identical to the preceding accepted actual run, and the
complete old parsed result unchanged apart from the additive summary evidence.
Independent67 preparation tests pass with116 source pins and120 prepared files
unchanged. Independent60 initial physical-preparation tests pass; the subsequent
bound77 and physical result are recorded above. A separate proposed pulse-only
write-side change is rejected by a concrete premature-ACK counterexample.
This is seven-context actual FFT qualification, not continuous RX or timing closure.
See [initial parent checks and explicit coverage limits](reports/experiments/20260910-retained-offer-summary-parent.md).

Latest checked-product candidate PASSES actual vendor FFT verification, but its
completed diagnostic route FAILS at **-8.324 ns**,2309 failing setup endpoints.
The unchanged runtime passes44 healthy numerical blocks,32 nominal and6 stalled
service drains after a bounded bench-only correction; original failure retained.
Independent76 preparation and43 physical-preparation tests pass. Synthesis and
route sources are audited unchanged. See [actual result](reports/experiments/20260910-checked-drain-actual-pass.md)
and [physical comparison](reports/experiments/20260910-checked-product-physical-parent.md).
The checked lane is held; retained fault-summary separation is the next measured
implementation target. Neither candidate is deployable.

Latest combined-refactor route improves WNS to **-2.697 ns**, from -4.068 ns,
but still FAILS: TNS -981.622 ns,848 failing setup endpoints. Hold +0.037 ns
passes; all7233 nets route with0 errors. Same-domain metadata/fault propagation
into retained-result state is now worst; ROM control paths also remain.
Resources:2333LUT4764FF21DSP15RAMB18. Five critical CDC findings and board/I/O
qualification remain open. See [new physical result and next measured target](reports/experiments/20260910-retained-control-physical-parent.md).

The combined private-descriptor/closed-input refactor now also PASSES the actual
vendor FFT seven-context campaign (root61512, exit0,57.31s). Independent73
preparation tests pass; all77953 actual CSV rows and the complete original
parsed results exactly match v5. Both new options and44 ownership/phase receipts
are checked. Fresh synthesis/routing completed as recorded above; no RX or
deployment qualification follows.
See [combined refactor actual qualification](reports/experiments/20260910-retained-control-actual-parent.md).

The earlier checked-product v1 actual campaign completed but was rejected: its
final nominal job lacks a sampled live ready/drain row before the bench starts
reset. The other31 nominal and all6 stalled services meet the unchanged5215
limit; all624233 trace rows and ownership counts agree. The bounded bench-only
drain witness now passes a fresh v2 run, without accepting fewer completed jobs.
See [preserved actual failure and diagnosis](reports/experiments/20260910-checked-actual-drain-boundary.md).

Retained-output actual vendor FFT now PASSES all seven contexts:19 complete
forward/inverse pairs,40 frame events, two interrupted forward jobs and both
reset recoveries. Independent251 preparation tests pass; all77953 actual CSV
rows match the frozen reference byte-for-byte. Runtime, clocks, numerical and
service limits are unchanged. Parallel checked-product controller integration
passes independent3306 tests, including distinct fresh payloads after reset;
that3306-test campaign uses a control actor. The separate actual numerical
campaign now passes as recorded above.

Retained-output synthesis and diagnostic routing have now completed, but
physical timing FAILS: WNS -4.068 ns, TNS -1952.796 ns, 1266 failing setup
endpoints. The worst path is same-domain metadata/fault control into a private
descriptor register enable; other reported paths reach kernel-ROM enables.
This is worse than earlier P1 (-1.492 ns), not a release candidate. Five
critical CDC findings and real 175 MHz board-clock integration remain open.

Next: measured destination/preflight/admission-path restructuring,
then physical closure and full receiver/continuous
acquisition/IIO/board qualification before `.18`→`.17` deployment. No radio
operation or production HDL gitlink promotion. See
[physical failure and targeted next changes](reports/experiments/20260910-retained-physical-parent-review.md)
and [actual PASS and independent3306 evidence](reports/experiments/20260910-retained-actual-pass-and-product3306.md).

The first default-off descriptor-offer candidate passes independent32 offline
tests. Its separately implemented closed-input/combined gate now passes
independent39 tests, with49 source pins unchanged, including all40 private-only
pins. An independent zero-strobe predicate evaluation also passes. The parallel
checked-product actual-harness/observer preparation passes independent93 offline
tests. These are not new actual FFT or routed timing results. See
[combined candidate qualification](reports/experiments/20260910-retained-closed-input-parent-review.md).

## Earlier verification history

Latest actual frame finding (2026-09-10): independent180 preparation tests PASS;
the two-site logger fix preserves all77953 scripted CSV rows exactly. Actual
vendor25461 passes the former logger crash, then stops on a testbench frame
ordinal assumption at cycle942. Physical inputs arrive939/941/942; the event
means internal frame processing, not first AXI acceptance. A documented causal
per-job event ledger is next, retaining all numeric/service/ownership gates.
See [logger verification and frame-contract finding](reports/experiments/20260910-retained-logger-parent.md).

Latest logger isolation (2026-09-10): parent runs12 tiny actual XSim cases.
All four conditional-string calls kernel-crash; all eight literal/explicit-if
cases emit exact expected rows. No FFT/runtime is involved. Parent also proves
the frozen parser misses the underscored FATAL_ERROR marker in an otherwise
complete log; current incomplete actual attempt was still correctly rejected.
Two-site logging-only correction and stricter fatal-marker rejection are next.
See [minimal logger reproduction](reports/experiments/20260910-retained-logger-repro-parent.md).

Latest actual correction (2026-09-10): the two-edit completion declaration fix
passes independent155 preparation tests and actual compilation. Vendor43908
passes startup, admits job1 at cycle934, then suffers an XSim kernel crash in
the actual_word CSV formatter at cycle939. This is not numerical qualification.
All73 source pins and both actual-run source copies remain unchanged. A minimal
logging-only reproducer is next; no runtime/fault relaxation or radio operation.
See [declaration correction and formatter crash](reports/experiments/20260910-retained-declaration-parent.md).

Latest startup diagnosis (2026-09-10): a source-identical copied-snapshot replay
reproduces cycle31 failure with66 explicitly logged controls. The completion
control and cutover producer-closed port are Z at all95 sampled times. Cutover
bit0 latches on the first enabled edge; other raw/known/admission controls are
valid at that boundary. An explicit early declaration/continuous-assignment
split is being prepared; its effect still requires actual re-compilation.
See [targeted diagnostic evidence](reports/experiments/20260910-retained-startup-diagnosis-parent.md).

Latest actual startup result (2026-09-10): the language-only launch correction
passes31 independent preparation tests. Corrected vendor invocation74560 now
compiles/elaborates, but fails at startup cycle31 before any FFT job admission.
Both source copies remain unchanged. Saved-WDB inspection confirms the required
controls exist but have no recorded history; a targeted diagnostic replay is
needed before assigning a cause. No fault waiver, timing success or deployment.
See [startup failure and read-only investigation](reports/experiments/20260910-retained-startup-parent.md).

Latest vendor attempt (2026-09-10): parent138 offline preparation tests PASS
with71 frozen sources, but first real vendor invocation49345 exits1 during
compilation: SystemVerilog wildcard connections in a `.v` wrapper were compiled
as Verilog. No simulation result exists. Both input copies and generated FFT
wrapper verify unchanged. A launch-profile-only language correction and new
frozen bundle are next; no RTL/numerical/timing relaxation or radio operation.
See [first actual attempt and isolated cause](reports/experiments/20260910-retained-actual-first-run.md).

Latest actual-FFT harness gate (2026-09-10): parent independently repeats112
offline tests; all66 source pins unchanged. Fresh77953-row scripted replay
passes inventory and19456 exact raw-row/job-time joins. Both original malformed
timestamp counterexamples and a consistent-clock/wrong-job-cycle mutation are
now rejected. Bundle/standalone-launch tests and source-specific vendor review
remain next; no actual FFT, routing or radio qualification is implied.
See [actual harness parent review](reports/experiments/20260910-actual-harness-parent-review.md).

Latest product integration gate (2026-09-10): independent parent2752 PASS
(1308 additive plus unchanged1444), all154 source pins unchanged. Separate
80-manifest/804-entry audit confirms96 exact reason/read rows and identical
eight-job enabled/disabled timing. Complete3488-node/38LS graph is acyclic;
actual driver-based publication dependencies and three restored cycles check.
Original failed alias-ID graph test is preserved, not relabeled. Additive real
P1 controller integration is now authorized; no vendor/routing/radio promotion.
See [full publication-seams parent review](reports/experiments/20260910-publication-seams-parent-review.md).

Latest actual-FFT preparation review (2026-09-10): parent saved-data probes
show the draft parser accepts a clock-grid-valid but wrong first-output time,
and an impossible slow-edge counter. Per-sample numerical equality alone is
not event-timing proof. Exact job/time joins and rejection regressions are
required before the actual run; no vendor or radio action was taken.
See [ledger timing counterexamples](reports/experiments/20260910-actual-ledger-time-parent-review.md).

Latest sampled-READY boundary (2026-09-10): parent verifies corrected additive
issuer rejects private writes when sampled READY is high but advertised capacity
is low during a natural mixed-reason-Q interval. A one-line lost-capacity-check
mutant fails the same independent probe. This is an invalid-caller primitive
test, not demonstrated real-top reachability. Full new-seam regression and
actual-FFT preparation remain in progress; no routing or radio promotion.
See [sampled-READY parent review](reports/experiments/20260910-sampled-ready-parent-review.md).

Latest retained-output gate (2026-09-10): parent independently repeats415
offline tests with exact-original clock precision; all46 sources remain pinned.
Separate403-simulation receipt audit and stricter typed5893-node/69LS graph
check pass. Nominal3645 and parked4911–4912 cycles remain conditional scripted
results, not physical/lower-clock qualification. Actual-FFT recipe preparation
only is next. The parallel sealed-product path needs exact sampled READY and
publication-only fault seams before P1 integration; no top/vendor/radio action.
See [full retained-output parent review](reports/experiments/20260910-retained415-parent-review.md).

Latest independent repaired-interface gate (2026-09-10): parent fresh1444 replay
PASSES (596 new plus848 unchanged). All54 source manifests/498 file entries
verify; independent full graph has3302nodes/36LS/no cycle and six restored
backedges are rejected. No added primitive state/healthy cycles; qualified
diagnostic summaries explicitly gain one edge. Real controller binding/reset
integration design is next, not actual FFT or physical promotion. See
[full parent review](reports/experiments/20260910-product-interface-full-parent-review.md).
In the parallel retained-output owner, parent independently reproduces eight
standalone coincident-control/ACK gaps, catches an overstrict first fence, then
verifies10 final boundary cases including legitimate receipt/ACK coincidence.
See [owner boundary review](reports/experiments/20260910-retained-owner-ack-parent-review.md).

Latest overlap evidence (2026-09-10): parent independently compiles/replays the
frozen retained-output prototype:17 PASS, all42 sources unchanged. Separate log
audit confirms8-clock next-forward dispatch,3645-clock nominal publication
interval, and4911–4912 with the reader parked. Parked-reader timing would exceed
the29.8us block budget at140MHz; no lower-clock or actual FFT claim. Full fault,
reset, graph and resource qualification is still in progress. The parallel
product-interface feedback partition is approved for additive implementation,
not top/vendor/radio promotion. See
[retained-output parent review](reports/experiments/20260910-retained17-parent-review.md).

Latest interface snapshot (2026-09-10): parent fresh compile/replay passes20
focused behaviors, including the repaired exactREADY seam and retained raw
closed/X/Z diagnostics. Complete3246-node graph still finds acceptance-derived
feedback via issuer/current-bank/read checks and handoff readiness. This
behaviorPASS/structuralFAIL snapshot is preserved; dependency repair remains
required before integration. See
[first interface review](reports/experiments/20260910-product-interface-first-review.md).

Latest correction (2026-09-10): original848 run remains recorded PASS, but its
product-fixture graph test omitted36LS concatenation nodes. Parent independently
reproduces the false negative: corrected3159-node graph exposes guard-fault /
handoff-readiness feedback. Earlier acyclicity/cone claims are withdrawn. The
additive fixture fault split and complete graph regression are required before
top integration. See
[graph correction and repair gate](reports/experiments/20260910-product-graph-correction.md).

Latest integration gate (2026-09-10): real P1 controller/design review authorizes
additive primitive interfaces/tests only. Parent independently reproduces the
missing actual-READY seam at word37 and511; both copied-fixture failures are
preserved. The fix must align producer/bank acceptance without hiding raw
closed/X/Z offers. Checked preflight head and persistent ACK receipt are also
required before top integration. See
[integration gate and exact counterexamples](reports/experiments/20260910-product-integration-gate.md).

Latest staged-validation result (2026-09-10): parent independently repeats848
offline product-reader/issuer tests, all PASS; eight healthy leases each deliver
512 consecutive checked words without gaps. Four real-controller integration
seams remain: reusable capacity, preflight checked head, retained handoff receipt,
and non-cyclic current-fault wiring. A source-specific integration design is
next, not a top or physical promotion. Recorded inverse-WDB extraction and
independent interpretation pass9472 values,64 guard snapshots and116 qualified
arithmetic comparisons; no simulation advancement or physical claim. See
[parent prototype review and next gate](reports/experiments/20260910-product-sealed-parent-review.md).

Latest actual-core result (2026-09-10, after16:20 UTC): inverse v2 original77697
PASSES complete automation; parent92874 independently repeats the full audit.
All76 jobs/38 tagged lifetimes and exact numerical/timestamp checks pass, with
all three full CSV hashes identical to the preserved first run. Only the
offline parser changed; no RTL/clock/budget relaxation. Recorded-WDB inspection
preparation and the separate staged/retained-context prototypes are next.
No routed timing or deployment pass is implied. See
[clean v2 result](reports/experiments/20260910-inverse-actual-v2-result.md).

Latest verification increment (2026-09-10): parent repeats111 inverse parser
tests and the complete saved-run reassessment, both successful. The bounded
drained profile transition is now tested; all211 original files remain intact
and original21014 remains automation FAIL. An exclusive v2 preparation with
only the parser/manifest change is next, not an authorized vendor retry. See
[transition correction and full reassessment](reports/experiments/20260910-inverse-transition-review.md).

Latest architecture evidence (2026-09-10): parent independently repeats111
overlap-ledger tests, all PASS. The original38-block/76-job timing is exactly
reconstructed; a separately labeled retained-output schedule predicts3645
cycles/pair, or3669 with+24 sensitivity. It is not implemented RTL or a lower
clock qualification. Explicit old/new raw-event cutover, retained real ACK,
fault/reset ownership and resource design are next. See
[overlap review and limits](reports/experiments/20260910-output-overlap-review.md).

Latest actual result (2026-09-10, after15:58 UTC): original21014 exits1 in
the trace parser, with source integrity intact. Parent independently isolates
one quiescent profile-switch-before-reset row, zero healthy-running fault rows.
Separate post-hoc checking verifies all76 jobs, exact words and38 full inverse
lifetimes; max nominal4555/stalled4835 remain within predeclared bounds. This
does NOT relabel the original failed automation. Narrow parser-boundary tests
are next, without retry or physical promotion. See
[failed run and diagnostic evidence](reports/experiments/20260910-inverse-actual-first-result.md).

Latest execution gate (2026-09-10): the frozen inverse bundle and nine-edit
execution owner pass parent review and independent source verification. One
actual FFT evaluation has started, owned by the inverse agent as original21014,
with no retry or automatic physical promotion. A result is still pending; this
does not supersede the failed P1 route. Exact source pins and scope are in the
[inverse preparation review](reports/experiments/20260910-inverse-actual-preparation-review.md).

Latest offline gate (2026-09-10, after 15:49 UTC): parent independently repeats
65 inverse actual-preparation tests, all PASS with unchanged source pins. This
qualifies the source/clock/protocol test harness, not a new FFT execution.
Exclusive bundle/owner review is next. A separate staged product writer/reader
prototype is authorized offline, and a trace-backed scheduling study is checking
whether next-forward processing can overlap prior-inverse result draining.
No timing constraint, production HDL gitlink, radio or PPU state changed. See
[preparation evidence and parallel scope](reports/experiments/20260910-inverse-actual-preparation-review.md).

Latest physical result (2026-09-10, after15:29 UTC): the P1 product-publication
trial's route completed but **TIMING FAILS**, WNS-1.492ns/TNS-441.681,
591 failing endpoints, hold+0.058ns. This is0.132ns worse than the ROM route.
All6916 nets routed with zero errors, but no promotion/deployment follows.
Parent independently verified all15 products and the committed full archive.
Next is a source-specific staged product-validation design, addressing both
metadata-write and input-identity fault/control paths; the inverse-bank actual
preparation continues separately. See
[failed route and next boundary](reports/experiments/20260910-product-final-route.md).

Synthesis checkpoint (2026-09-10, after15:24 UTC): original75133 PASSES the
source-pinned product-final OOC synthesis,2064 LUTs/4607 FFs/21 DSPs/15 RAMB18s,
zero black boxes. Parent independently verified complete actual-source binding,
13 copied sources and all eight products. Accepted DCP `41c756bd...` is approved
for ONE unchanged-constraint diagnostic route via the reviewed5938ff6c owner.
There is no new routed timing result yet; neither synthesis success nor a future
route-tool exit alone means deployment eligibility. See the product-final report.

Next physical gate (2026-09-10, after 15:16 UTC): product-final physical
preparation independently passes33 tests and closes19 frozen files, including
eight actual-qualified runtime modules. Exact clocks/constraints/strategy and
the synthesis owner remain unchanged. One source-pinned OOC synthesis is now
approved at recovery `product-final-synthesis-v1`, without retry or automatic
route/promotion. This approval is not a synthesis or timing result. The inverse
alternative independently passes252 tests, adding actual-third-word status
ordering. Its observed +3 publication/+6..7 reuse overhead is an unstalled
fixture result; periodic backpressure needs phase-aware absolute timing checks.
Neither alternative is a full receiver or radio qualification.

Latest verified increment (2026-09-10, after 14:59 UTC): the product-local final
publication alternative now PASSES its full vendor FFT run (original50316,
terminal0, 588.57 seconds). Parent independently checked all65 frozen sources,
19 generated-IP files, four zero owner exits, the composed result verifier and
all four complete historical numerical CSV hashes. The new observer checks
623129 edges and140 sampled publications, all authorized; its sampled negative
rows are zero and are not claimed as actual-controller coverage. Those veto
witnesses remain separate directed offline tests. No physical timing pass is
implied. Source-specific physical preparation is next; no new synthesis/route
or radio launch is authorized yet. See
[actual result](reports/experiments/20260910-product-final-fence-review.md).
The inverse sealed-bank alternative independently passes the final combined
235-test suite, including the corrected independent timestamp-order checker.
Runtime RTL is unchanged from the136-test cut. Actual preparation must measure
early-status join latency rather than borrowing delayed-status test bounds;
see [inverse review](reports/experiments/20260910-inverse-sealed-integration-review.md).

Parent-reviewed increment (2026-09-10): the independent producer-local final
publication alternative passes 26 repeated offline tests, including a newly
required real-checker sticky-fault witness and its missing-veto mutation. It
adds no state/cycles at source level and leaves original global checks intact,
but has no actual-controller or physical timing result yet. Next is additive
actual-core preparation and observer testing, not deployment. See
[scope and exact evidence](reports/experiments/20260910-product-final-fence-review.md).
That preparation now independently passes 60 tests and its exact 65-file bundle
verifies. Unique execution-owner and independent sampling-order reviews now
pass; one exact-source actual FFT run is approved, without retry or physical
promotion. No new vendor result or physical pass is claimed.
The separate inverse sealed-bank integration now independently passes 136 frozen
offline tests, including nonzero real-guard data, paused-source resets, ten
targeted mutants and a clock-phase sweep. Observed healthy reuse overhead is
4–6 fast clocks in that sweep, not complete FFT throughput. Next is additive
actual-core preparation; physical timing remains unqualified. See
[integration evidence](reports/experiments/20260910-inverse-sealed-integration-review.md).

Latest update (2026-09-10, after 13:47 UTC): build-output storage recovered
without discarding evidence. The corrected late-request testbench independently
passes694 offline tests and its fresh vendor run2011 now passes the unchanged
late-rejection/coarse/pilot gates, independently verified by the parent.
L1 synthesis passed,
but its first diagnostic route **fails** setup at -1.549 ns, worse than the
-1.341 ns arithmetic baseline. ROM-prefetch actual23845 remains incomplete after
a `/tmp` quota error; it is not a passing run. Its unchanged-source successor10102
now PASSES the full functional suite: all four historical traces are unchanged,
and parent verification confirms complete ROM/CDC/control receipts and stored
source integrity. ROM physical preparation independently passes 43 tests; its
source-specific one-shot synthesis passes with 2059 LUTs, 4607 FFs, 21 DSPs and
15 RAMB18s (+73 LUTs/+107 FFs versus C1). Parent verified all products and source
identities. Its diagnostic route improves C1 setup from -1.830 ns to -1.360 ns,
but still FAILS (575 setup endpoints); hold is +0.058 ns. Product metadata through
input validation into publication is now the worst path. The additive sealed-bank
controller independently passes 526 standalone tests; a source-specific inverse
adapter and dual-clock bank are the next offline composition, not yet a timing
or receiver result. See
[first-slice scope](reports/experiments/20260910-sealed-bank-first-slice-review.md).
Integration review additionally reproduced an inherited paused-slow-clock reset
hazard: a stale source request can leave an old prefetched word after the producer
finally purges. An independent remote-purge barrier prototype passes four fresh
recovery cases and rejects both barrier-disabled controls. The actual new
dual-clock/issuer/top composition must still pass those scenarios; see
[reset diagnostic and prototype](reports/experiments/20260910-paused-source-reset.md).
No runtime promotion or radio
operation followed. See [storage recovery and new routing evidence](reports/experiments/20260910-build-storage-recovery.md).

Earlier measured increment: the first combined60 common-source coarse/native/
pilot vendor-FFT simulation now passes (original5432 terminal0). It checks894
exact coarse scores/447 retained map words,520 native captured samples,257 raw
hypotheses/241 qualified tuples, two26-word public packet reads and512 independent
pilot CI16 words. Native full drain takes74641 control cycles (746.41us at the
simulated100MHz clock), within the unchanged84000 limit. Parent independently
ran the frozen result verifier, rehashed both250-file input bundles and checked
generated-IP before/after identity. Actual own-clock FFT/capture overlap is245
transfers. This is one static-known-center ideal-clock simulation with a declared
startup pause and13312 continuous60 samples, not causal acquisition,750-frame/s,
production-map, physical60, IIO-throughput or RF qualification.
The exact111 control candidate synthesized with zero black boxes and completed
its diagnostic route, but timing FAILS: island175 setup -1.761 ns, global setup
-1.862 ns, hold +0.071 ns. Distributed-fault CDC-10, other crossings, reset
recovery and external I/O qualification remain open. The original failed route
is archived before a separate default-off per-cause CDC candidate. No release,
full-receiver timing or on-radio qualification follows.
The separate R1/B1/O1 arithmetic candidate has now also synthesized and routed:
island175/global setup -1.341 ns, hold +0.038 ns, all6762 routable nets complete.
This still FAILS, with379 internal and118 crossing setup failures. It is not the
combined control/CDC candidate or a full receiver. Its worst internal path is
input validation into descriptor capture; no physical release is authorized.

Next timing cuts are independently checked offline: CDC actual preparation101
PASS and local first-admission descriptor enable349 PASS. One frozen CDC
R1D1S1C1/extras1/175 actual-core simulation now PASSES (original20091 terminal0,
580.44s), with all four historical CSVs unchanged and independent CDC/status
receipt verification. Its exact C1 synthesis now passes with zero black boxes,
1986 LUTs/4500 FFs/21 DSPs/15 RAMB18s; the targeted CDC-10 finding is absent,
but139 mailbox CDC warnings remain. Root independently verified all8 products
and13 source/IP hashes. The unchanged-constraint diagnostic route completed
(original49744 terminal0), but timing FAILS: island/global setup-1.830ns,
653 global setup failures, hold+0.058ns. The worst path ends at the input
descriptor capture enable; the CDC change alone does not close timing.
The first local-enable actual
attempt stopped before simulated traffic because its diagnostic lookup did not
handle Vivado's escaped parameterized top name. The failed attempt is retained;
the recorder-only correction independently passes143 tests with runtime,
stimulus and numerical comparisons unchanged. Corrected frozen L1 actual14041
passed waveform discovery but failed its new155-bit observer at time zero,
before healthy traffic. Both original failures remain preserved. A separately
proved settled-pre-NBA observer schedule passes188 independent offline tests;
the successor L1/R1B1O1/175 actual6473 now PASSES all original numerical/fault
gates with the complete historical CSV unchanged. Parent independently reran
the frozen result verifier and verified the189-file actual archive from Git.
All155 guard bits remain unconditional, with zero added hardware cycles. The
final pre/post counters differ by one at the shared finish/+1ps time slot;
this is retained explicitly, not rewritten. Read-only saved waveform inspection
now confirms all155-bit views match at17 sampled times and localizes the pending
counter increment to the final edge. It cannot resolve individual simulator
regions within a timestamp. Source-specific physical preparation is next;
no physical benefit, explanation
of the earlier vendor startup mismatch, or D/S/CDC union is established. Their
reviewed sources/evidence are pushed to their respective experimental DNM
branches, not firmware main. The60 public bank/STOP/pilot interface independently
passes660 tests; its combined common-source coarse/native/pilot harness passes311
independent preparation/verifier tests under a frozen no-tail numerical/service
contract. Full source review and frozen108-source/250-file verification now
pass; the first healthy common-source60 vendor-FFT simulation now PASSES
(original5432 terminal0), independently verified above. This bounded447x2/static-known-center test is not a causal,
750-frame/s, full-map, physical or radio qualification.
An additional isolated ROM read-ahead/last-visible-retention prototype passes149
offline tests, including continuous512-beat traffic; it adds37 logical bits at
D18 and no nominal cycles. All old visible coefficient/control fields compare
unconditionally. Additional directed occupied X/Z-ready and flush coverage
passes31 tests. The additive metadata-prefetch extension now independently
passes60 tests (31 retained plus29 new), targeting the separate measured
kernel block-metadata capture-enable path. It adds70 logical bits beyond the
word-only variant and no nominal cycles. Its additive C1 joiner/bank integration
now passes147 independently repeated offline tests, including all inherited
source checks and positive private-reset coverage. One exact K1/M1 actual-core
run is authorized after frozen-source verification; no result or physical
benefit is claimed yet. The separate expected-late60 composition passes681
independently repeated preparation/verifier tests; its one vendor-core rejection
run completed but its overall result FAILS: the first status audit started after
seven numbered control cycles rather than the required minimum eight. Original
failure and sources are retained; only an offline stimulus-scheduling correction
is authorized, with rejection/settling/upper bounds unchanged. Healthy60 runtime
and golden samples remain unchanged. Separately, L1 physical preparation passes
58 parent-repeated tests and its first isolated synthesis57050 now PASSES:
1945 LUTs/4547 FFs/21 DSPs/15 RAMB18s, zero black boxes. This is one additional
LUT and unchanged FF/DSP/BRAM versus the arithmetic baseline. Root independently
verified all eight products and14 recorded source/IP hashes. One unchanged-
constraint diagnostic route is authorized; no timing benefit or receiver
promotion is established by synthesis alone.

Latest checkpoint (2026-09-10): the additive complete three-bank coarse scorer
passes actual-core numerical/fault replay and 64-block continuous capacity tests
at 175/200 MHz. Independent primary-branch 175 MHz replay also passes: 5,364
exact scores and 28,608 ordered burst/stall scores with no ingress stalls.
Whole-coarse synthesis measures 3,868 LUTs, 6,499 FFs, 27 DSPs and 14 BRAM tiles;
this is not routed receiver area or timing qualification. Paired digital PSS/PIL1
replay now passes both reduced geometries at bank175/bank200/shared200 with exact
independent pilot bytes. Eight separate bank-map fault/reset/re-enable cases pass.
The held-phase/balanced-identity route improved175MHz setup from-2.438ns to
-1.596ns. The subsequent held-preflight/two-comparator refactor passes both
actual-core modes and264 tests (eight explicit physical skips), including
independent old current/sticky fault predicates and20 root-repeated focused
tests, but its single route still fails at-1.614ns. A subsequent data-only
payload-enable/balanced-kernel-identity refactor also passes both actual-core
modes and preserves prior control traces. Its single route is still failing:
175MHz setup-1.559ns/hold+0.071ns,553 failing same-clock endpoints. The worst
path crosses output-bank current framing checks into forward kernel state
enables. The subsequent forward-only phase-separation experiment passes exact
functional equivalence, but its single unchanged route is worse:175MHz
setup-1.907ns/hold+0.071ns,664 failing same-clock endpoints. Read-only netlist
inspection confirms the intended output-bank current-metadata dependency is
removed from kernel enables; input-fault aggregation, unregistered multiplier
B inputs and remaining kernel control still fail. No timing closure, runtime
promotion or additional physical retry is authorized. A stage-local fault and
arithmetic-pipeline proposal is under review.
Generated175 MMCM active-traffic reset/recovery also passes
an independent primary replay with 7,853 exact accepted scores. The original
4,096-block175 burst/stall soak completed:1,830,912 ordered scores, FIFO358/512
and no ingress stalls. This is the frozen alternative source, not an exact
primary-source4096 replay or physical qualification. The single full20,000-by-64
simulation now passes:1,280,000 admitted scores, all20,000 map words, retained
reads/release and a fresh447-score classified partial abort. Root verified all103
artifact hashes and replayed its strict terminal verifier. Additive map tests,
oracle and evidence are integrated on primary without runtime RTL changes;
352 combined policy tests pass. This is not a second full recovered map or RF
qualification. The new true-PSS520 concurrent fixture passes244 independently
repeated offline tests; both actual175/200 runs pass and parent independently
verified all238 archived artifacts plus ordered native/pilot observations.
Additive tests/evidence are integrated;415 combined primary tests pass. The late
native-command negative now passes actual-generated-core simulations at175/200:
late rejection with no capture/packet/IRQ, exact62 register reads and2048 pilot
bytes each. Parent independently checked frozen sources and archived outputs;
its additive integration passes303 primary regression tests. These are
simulation results, not on-radio or physical qualification.

The separate rounding candidate improves isolated setup from-1.577 to+0.207ns;
its internal register-to-register setup/hold are+0.964/+0.103ns. All176 remaining
isolated hold failures start at top-level ports; those are not waived, and
neither this local result nor its74-fabric-FF reduction closes bank timing.
The first active control-candidate comparison failed in both baseline and
combined modes during the original missing-forward-status epoch. Both failures
are retained. A subsequent unchanged-comparison diagnostic isolates one raw
FFT status-byte mismatch; status valid was inferred low from the saved guard
output and literal veto logic. All216 other fields agree. The narrowly qualified
payload observer now passes29 independent parent tests, including valid-status
fault and same-edge publication checks. The baseline actual run reproduces
both complete historical CSVs but fails later in an added fault epoch; a
stimulus/checker same-time hazard was identified. The phase-aware added-stimulus
correction passes53 independent parent tests; its frozen actual baseline retry
now passes the complete old/extra suite and qualified-status audit, without
any original assertion changes. This is R0/D0/S0 only. The original
raw217 failure remains retained and no candidate is promoted.
A separate one-stage operand-register prototype targets the
BRAM-to-DSP path with explicit added latency and offline qualification. Its
first two physical attempts failed before synthesis due to an inherited tool
library conflict. A subprocess-only repair passes60 independent parent tests;
both subsequent isolated routes complete. The new stage maps AREG/BREG1/1 in
all four DSPs with80 additional fabric FFs and no extra DSP. Internal setup/hold
are+0.441/+0.152ns, but all-path hold remains-0.685ns from top ports. This is
input-register inference, not bank timing closure; upstream BRAM and the full
receiver are absent. Integration must preserve the bank's existing private
bubble semantics and held-overflow fault/publication fences.

The additive bank arithmetic port now passes101 independently repeated offline
tests, including exact token math and held-overflow ownership checks. Parent
verified all5850 archived files and31 frozen sources. Its zero-frame bank test
interface is synthetic, not vendor FFT evidence. Final actual-FFT preparation
now passes180 independent parent tests, including failed-run integrity and
delayed success-receipt publication. The175 baseline/candidate actual pair both
terminate with PAYLOAD_PRODUCT_OUTPUT_MISMATCH during the deliberate epoch14
product-overflow injection. Parent independently verifies their preceding
19456 ordered words/stream and16986 output-derived oracle scores each, but both
full runs remain FAIL. Standalone vendor simulation isolates a force/monitor
register-versus-wrapper observation distinction. A narrow three-field rebind
per observer preserves all comparisons and runtime arithmetic and now passes226
independent parent tests. Both source-frozen175 retry benches complete all
functional checks; the automation then fails looking for a diagnostic marker
in the wrong log. Parent independently verifies the full functional/event/source
checks, but original automation failures remain recorded. Internal waveform
verification and a separate post-hoc assessment are pending. No complete-bank
routing pass is claimed. See the parent review for exact source/inventory pins.
The control R1/D1/S1 settings-only freeze passes94 independent
parent tests and its single175 actual run now PASSES, including the complete
historical registered CSV and both extra fault/reset suites. Parent independently
verified all1246258 qualified observations, including292463 explicitly retained
invalid-status-only differences. This is not original raw217 equality. Offline
preparation for a source-specific physical measurement is next; neither branch
is promoted. The control test-stimulus correction now handles the low-phase
early-publication boundary found in its first attempt; old assertions remain.

The30MS/s common-source offline cohort is frozen and independently verified.
A new explicit30-upper bank+STOP public interface remains isolated/offline;
its unknown-parameter guard repair and legacy regressions pass340 independent
parent tests. The unchanged51-file numerical cohort independently rederives.
The real30 common-source bank/native132/PIL1 harness is prepared:490 agent tests,
91 new independent parent tests,95 frozen sources and unchanged51 goldens.
Its standalone native service budget passes, including continued computation
after source disable; this does not prove the combined FFT composition. The
first actual launch failed before vendor initialization due to a missing loader
path; the environment-corrected run now PASSES with unchanged inputs:894 exact
scores/447 map words,260 native capture samples,129 raw tuples and512 pilot
outputs. Parent independently reran the frozen verifiers and checked all636
run-file hashes. Native capture overlaps actual FFT consumption and refinement
survives coarse STOP. The additional healthy30-upper343x2 actual run also passes:
686 admitted/687 visible scores,343 exact map words, unchanged fine/pilot results
and native budgets. The late447 actual negative now passes: one expired command
is rejected with no native capture, computation, packet or interrupt, while894
coarse scores,447 map words and512 pilot samples remain exact. Parent reran its
frozen verifier and checked all794 original-run and536 portable artifact hashes.
Other negative cases and runtime promotion remain open. The343/late case packages
pass253 independent parent tests and652 agent regressions with unchanged
original447 inputs; both actual results are archived separately.
Actual60 bank/native/pilot
integration remains open. Latest
source-specific decisions and measurements:
[`reports/experiments/20260910-high-rate-and-round-boundary-parent-review.md`](reports/experiments/20260910-high-rate-and-round-boundary-parent-review.md).
The separate60 sample-support contract is now tested:16423 raw samples map to
4096 canonical samples, with520-sample native capture and exact pilot support.
The new upper60 common-source numerical cohort also passes256 independently
repeated tests and full frozen-helper rederivation of all69 numerical artifacts:
seven coarse blocks,264-tap native257 raw/241 qualified tuples and512 pilot outputs.
The cohort itself remains offline arithmetic, not actual60 composition.
The separate39 support tests plus unchanged30/60 golden regressions pass132 tests:
[`reports/experiments/20260910-high-rate60-support-contract.md`](reports/experiments/20260910-high-rate60-support-contract.md).
Native60 service preparation and a corrected public-index readback witness now
pass575 independently repeated tests. One actual standalone native60 simulation
passes with the same16423 original source samples/no added tail: publication
72498 cycles, public release73287, full257 drain74642, then256 no-stale cycles.
Computation continues after source-off; the final five raw tuples complete after
packet release. Original public-readback failures remain preserved. Readback
coherence/age is checked separately from unchanged actual command/lead/deadlines.
This is not queued-load capacity, causal acquisition or actual paired60 PSMA/PIL1.
No receiver profile or radio has been changed. Completed alternative studies are preserved
on remote do-not-merge branches. See
[`reports/starlink-coarse-parallel-evaluation-20260910.md`](reports/starlink-coarse-parallel-evaluation-20260910.md)
and [`reports/starlink-bank-owned-integration-gates-20260910.md`](reports/starlink-bank-owned-integration-gates-20260910.md).
Primary replay evidence:
[`reports/experiments/20260910-bank-composition-primary-replay.md`](reports/experiments/20260910-bank-composition-primary-replay.md).

## Objective and completion gate

Capture one RX at 15, then 30, then 60 MS/s while hopping over CH1L, CH2L,
CH3L, CH4L, CH1U, CH2U, CH3U, CH4U. Each visit contains exactly 120 ms of
valid samples, excluding the transition and filter-settling guard. One run
covers approximately 300 seconds of the source-sample timeline. Export a
continuous, counter-attested 2.5 MS/s CI16 pilot stream over IIO and retain
independent FPGA PSS evidence for those same visits. Analyze every valid visit
with host GLRT after recording, including visits with no FPGA trigger.

Completion requires measured live pilot evidence AND qualified FPGA PSS timing
lock, with compatible frame timing on the same observations. Transport success,
synthetic injection, a coarse periodic peak, or GLRT alone cannot complete this
goal. No detection is an admissible recording outcome, not a lock claim.
PSS timing lock is distinct from the legacy SSS-qualified `frame_lock_claim`;
SSS is not silently added to this task, nor may its legacy gate be bypassed.

### Immediate priority: fixed-frequency paired live proof

Before expanding to hopping and higher rates, qualify one fixed upper-edge
frequency at 15 MS/s: capture the same observation through both FPGA PSS stages
and the independent 2.5 MS/s pilot IIO path, then run blind host GLRT without
FPGA timing/frequency seeds. Preserve all negative visits and fault evidence.
Report FPGA fit/timing separately from live PSS lock/GLRT agreement; passing
synthetic replay does not satisfy the live gate. The eight-target, 120 ms dwell,
300 s scanner and 30/60 MS/s qualification remain required later stages.

Resource work proceeds first through (1) improved slice/control-set packing
and suitable RAM-backed storage, and (2) shared/time-multiplexed arithmetic
with demonstrated sustained throughput. Preserve both PSS stages, frozen
coefficients, exact pilot samples, and timing/fault metadata. Measure full-design
placement and timing after meaningful changes. Removing a detector or buying
different hardware is not an approved shortcut. The .18-before-.17 deployment
and exact-serial RX-only ownership gates below remain unchanged.

## Ownership and deployment

- Firmware and firmware submodule changes stay on experimental do-not-merge
  branches; the firmware superproject is `codex/starlink-rx-only-do-not-merge`.
- Reusable PPU changes are tested, committed, and pushed to PPU remote main.
  Preserve unrelated/unqualified pending changes; never publish an untested
  firmware promotion as part of scanner support.
- Local canary: `.18`, serial `1040007c4a94000211000b009186843ef2`.
  Use serial-attested local access and reversible RAM qualification first.
- Outdoor receiver: `.17`, serial `104000bac4950008230026001b440a003a`.
  Ethernet only; deploy through PPU's qualified network-flash lifecycle, with
  exact image identities and rollback to its known-good detector firmware.
- `.17` RX1 remains on its powered 13 V, tone-off LNB/bias tee. Do not enable TX
  or assume the previous attenuated bench connection still exists.
- Do not open `.20`, `.21`, or any other radio. Acquire the serial-specific
  ownership lock before hardware work and restore settings before release.
- The existing production persistent-hop protocol deliberately excludes `.17`
  and requires dual RX. Introduce an explicit experimental single-RX capability
  and exact-serial opt-in; do not remove the legacy exclusion or impersonate
  the production FPGA/metadata identity.

## Reviewed scanner implementation

The active release selector resolved to commit
`39146ee83d00523fbd37ba02179c87a5c241a017`. Its tracked scanner plan, adapter,
target geometry, and models match the reviewed main checkout at `29be8492`.
Direct release-directory access was permission denied; the comparison used the
corresponding Git objects, not a claim to have inspected the running process.

- Leo: `src/leo/scanner/persistent_hop.py` and
  `src/leo/radio/pluto_persistent_hop.py`.
- PPU: `src/pluto_plus/persistent_hop.py` and
  `src/pluto_plus/hardware/iio_persistent_hop.py`.
- libiio commit `f6c450eada95ce99fe8756ebc244bfcf6ddcc72a`:
  `iiod/spf-hop-scheduler.c`, `spf-hop-device-local.c`, `spf-hop-session.c`.
- Kernel provider: `adi_tandem_agc.c` and the `adi_persistent_hop.h` ABI in the
  persistent-hop firmware worktree. These interfaces are not present in the
  current experimental detector kernel and require an appropriate adapter.

The host calibrates and verifies eight volatile Fast Lock slots before capture.
One IIO session remains open. A radio-local worker polls the hardware counter,
calls the owned kernel recall interface, and records before/after counter
brackets. Its sleeps are capped at 5 ms; it is not a sample-exact FPGA retune
sequencer. Valid IQ begins after the recall bracket plus the declared guard.
An independent reader and bounded writer queue decouple hopping from Ethernet
and storage. Production guidance uses a 1 ms guard, 131072-sample refills,
eight kernel buffers, eight visits of read-ahead, and a 64-visit storage queue;
the high-duty acceptance objective is at least 95%, not the historical 90% floor.
These are reference settings, not qualified values for the new image.

Fast Lock saves synthesizer calibration work. Recall return is not proof that
all analog gain/DC/filter transients have settled. Measure guard adequacy.
L/U means channel edges, not LNB polarization or 22 kHz band switching.

## Architecture and invariants

1. Keep one full-rate RX source counter running for the complete session.
2. Tap full-rate samples for sparse PSS timing. Reuse the 15 MS/s canonical
   edge-conditioning branch for coarse PSS and for the pilot export branch.
3. Translate the pilot band within that 15 MS/s stream, anti-alias filter, then
   decimate by six to 2.5 MS/s. Overall source/export ratios are 6, 12, and 24.
   The PHY remains at the full source rate; the IQ IIO device reports its own
   output rate. Do not set the AD9361 itself to 2.5 MS/s.
4. Restore only the necessary single-RX DMA path AFTER decimation. Never DMA
   the continuous full-rate IQ stream to ARM or host in normal operation.
5. Switch lower/upper mixer direction and coarse/fine coefficient banks under
   one acknowledged visit boundary. The current hard-wired upper-edge image
   cannot simply be retuned and called a lower-edge detector.
6. Fence old PSS windows and abort partial maps at each hop. Clear filter and
   detector histories without resetting the global source counter or reopening
   the IIO session. Tag every result by the visit in which its input was captured,
   not by the currently selected LO when the result is read.
7. Version the paired record contract: serial, boot/session/visit identities,
   channel/edge, actual LO/profile, frequency references, source and output
   rates, source-counter bounds, exact decimation phase and rational group
   delay, output count, coefficient/filter identities, and all invalid spans.
   Existing equal-rate, dual-RX contracts must retain their original semantics.
8. Separate intentional transition invalidity from lost samples. Neither branch
   may silently stall the ADC or conceal dropped work under backpressure.
9. Persist raw CI16 plus immutable manifests incrementally. Do not require
   compression to achieve the transport budget. Analysis runs after recording.

## Frequency and evidence limits

The existing PSS projections use rate-specific slice centers. Derive source LO,
canonical DDC translation, pilot reference, and templates from one explicit
frequency plan; do not copy the old 1.9375 GHz LO across rates. Preserve the
published pilot-bin convention separately from the scanner's historical band
reference, including any half-subcarrier difference. Account for actual LO
readback/quantization and receiver calibration before comparing CFOs.

A 2.5 MS/s output cannot cover the entire pilot band plus arbitrary +/-1.2 MHz
frequency uncertainty. Center it using an independently qualified calibration;
declare its residual-CFO coverage and filter response. If the signal may have
been filtered out, mark the GLRT comparison unobservable, not a PSS false alarm.
A separately authorized wider diagnostic recording is a fallback, not a silent
change to the requested 2.5 MS/s product.

GLRT and PSS are different detectors with different bandwidth and integration
gain. GLRT is an independent live cross-check, not an infallible truth label.
2.5 MS/s has a 400 ns sample interval; it alone cannot certify absolute 16.7 ns
PSS accuracy at 60 MS/s. Use controlled known timing and bounded full-rate debug
snippets for that gate. Debug sampling must include negatives as well as triggers.

## Schedule and throughput budget

- Per valid visit: 300000 complex output samples = 1200000 CI16 bytes.
- Continuous output: 10000000 bytes/s = 80 Mbit/s payload per radio.
- Approximately 3 GB per 300-second single-RX run, plus metadata/maps/debug.
- Eight 120 ms visits plus ideal 1 ms guards take 0.968 s per round. Actual
  recall/scheduler/startup time is additional and must be measured.
- Ideal balanced exposure is about 37.2 s per target over 300 s; this is NOT
  300 s of continuous observation of each target.
- Finish the current valid visit at the duration boundary with an explicit,
  bounded terminal overshoot; never silently truncate or claim a partial visit
  contains 120 ms. Record actual exposure and revisit gaps per target.
- Keep IQ/map/event queues bounded. Validate actual Ethernet headroom and disk
  stalls. More-frequent full maps cannot be assumed to fit beside the IQ stream.

## Stage gates

### Release ordering and promotion gates

Release A is fixed-frequency, upper-edge, single-RX 15 MS/s paired recording
and outdoor verification. Release B adds the eight-target 120 ms scanner and
the 30/60 MS/s rate ladder. Release A does not require every Release B feature,
but is not completion of the full objective.

1. In parallel: close complete-receiver physical timing; qualify prior-only
   frequency assistance and fine timing on held-out/known-origin data; finish
   the native paired recorder. The existing 25 MS/s replay remains a frozen
   externally assisted baseline, not online acquisition proof.
2. Qualify the matched stop-enabled image and paired recorder on .18. Start
   with a 120 ms transport check, then a two-second finite envelope providing
   at least one second of actual common pilot/map/fine support. The current
   PPU finite reader allows this envelope; it does not implement continuous
   30/300-second recording. Extend and test bounded continuous delivery before
   making those duration claims; do not concatenate finite sessions silently.
3. After .18 passes the relevant gates, use PPU network deployment and tested
   rollback on .17. Start fixed-frequency with a short integrity check, then
   120/300-second observations. Distinguish transport, coarse detection, fine
   lock and calibrated timing accuracy. No RF detection is a valid observation,
   not proof of receiver success or a reason to invent a lock.
4. Only after the separate short-dwell policy is qualified, add lower/upper
   switching and 120 ms visits over 300 seconds. S3/S4 remain coupled: the old
   three-map rule needs 256 ms and cannot qualify a 120 ms dwell. Boundary-stop
   at the next complete tile is not itself an exact 120 ms hop fence.
5. Repeat the same offline, full-image, .18 and .17 gates at 30 and 60 MS/s;
   pilot output remains 2.5 MS/s. All original rate/scanner requirements remain.

Every promoted image must include the exact tested FPGA, kernel, device tree
and host contracts, a fresh timing/CDC/board-I/O audit, and serial/boot identity
checks. The latest measured route is still a failure; test-vector success and
an available package or bitstream are not deployment authorization.

Frequency assistance must use evidence available before the PSS observation.
Test its source-time order, alias-selection policy, correction age and actual
processing/command latency separately. Earlier sample timestamps alone do not
prove an implementation can meet an online deadline. Keep independent GLRT on
the subsequent comparison interval free of PSS timing/frequency seeds.

### S0 — Offline contracts and source audit

- [x] Implement this plan and a hardware-free frequency/schedule compiler.
- [x] Tests: all 24 rate/target combinations, exact 300000-sample visits,
  source/output counter mapping, LO half-Hz rounding, lower/upper signs,
  target order, reject unsupported rates/serials and impossible CFO coverage.
- [x] No radio access from the plan command; no detection claims.

### S1 — Pilot DDC oracle, vectors, and resource feasibility

- [x] Initial float/fixed-point anti-alias oracle, pinned coefficients and scaling
  for the canonical 15 -> 2.5 MS/s pilot tap. Full pilot-frame and source-rate
  composition validation remains open.
- [ ] Tests: impulses and exact group delay; both edges; tones and pilots over
  the declared CFO domain; alias rejection; clipping; decimation phase; reset
  transients; PSS/pilot frequency-reference agreement at 15/30/60 MS/s.
- [ ] Finish complete-receiver physical qualification of the implemented,
  bit-tested RTL DDC. Out-of-context and full-shell synthesis/route must
  demonstrate fit and timing margin with PSS plus the single-RX IQ DMA. Do not
  assume the current nearly full design has space, and do not count
  already-removed TX resources a second time.
- [x] Implement and bit-test the largest new stage: time-shared 255-tap /3 FIR,
  including rate/phase/fault fences. This is not the complete pilot DDC.
- [x] Assemble the canonical FIFO/pacer, mixer and halfband with the /3 FIR;
  bit-test 15/30/60 compositions and complete a 120 ms supported-output replay.
- [x] Independently acquire and GLRT-score published pilot/PSS fixtures after
  the complete canonical RTL export, including a noise-only control. This is
  synthetic preservation evidence, not live GLRT or FPGA PSS-lock qualification.

### S2 — Paired fixed-frequency IIO capture on .18

- [ ] Qualify the implemented single-RX IQ/metadata path and finite PPU reader
  through real DMA/IIO/Ethernet. The individual RTL/driver/API components are
  present; native paired operation and durable delivery remain unqualified.
- [x] Add explicitly selected, bounded raw PSS map/fine refill receipts with
  error/negative retention and joined cleanup. This is a host API prerequisite,
  not a paired recorder or live IIO qualification.
- [x] Add the pure exact Q32.32 finite fine-schedule ledger, raw-packet validation
  and source-support joins. This does not submit a native schedule, establish
  continuous coverage, or prove paired capture/lock.
- [x] Add bounded public current-index/control reads and receipted finite fine
  startup. Retain individual write outcomes, driver acknowledgment separately
  from later worker/result completion, and uncertain cleanup evidence. These
  APIs remain offline-tested prerequisites, not paired live qualification.
- [x] Implement and offline-test the concurrent finite paired recorder using
  independent bounded pilot/map/fine contexts under one serial-attested owner. Open/flush maps
  before pilot ARM; keep maps running while fine requests are submitted/read.
  Preserve raw chunks before decoding/reassembly, negative observations,
  partial/error payloads and durable manifests. Progress/origin events are
  provisional until terminal identity, counts and health checks pass. Native
  `.18` DMA/Ethernet and live detector qualification remain unchecked above.
- [ ] Add an explicit map stop receipt and drain protocol. For fixed frequency,
  a stop-at-map-boundary request must finish the current tile and pending
  publication, forbid the next tile, and acknowledge a stop ticket, terminal
  generation and exact source-coordinate bound before coarse disable. Preserve
  both ready banks and every real fault; absent scores must timeout, not imply
  completion. Legacy immediate disable/flush semantics stay unchanged.
  The proposed two-register ticket/receipt ABI, exact boundary semantics and
  executable rollout gates are in `docs/starlink-map-stop-boundary-plan.md`;
  the complete native controller/driver/recorder path is not yet qualified.
- [x] Add the default-disabled map-core publication fence, with same-edge
  admission blocking, actual-publication acknowledgment, retained terminal
  metadata and real fault/abort accounting. Tests include the production
  20000-bin by 64-frame geometry; native control is a separate increment below.
- [x] Add the default-disabled synchronous PSMA ticket/window/controller and
  wrapper wiring. Enabled shared-15 ABI 1.6 supports actual fence-edge ticket
  acceptance, frozen terminal bounds and retained IRQ/pilot wiring; dedicated
  RTL tests pass. Reduced real-FFT/canonical/PIL1 shutdown-tail testing is
  recorded below; production-duration integration and enabled-image timing
  remain open.
- [x] Add the pure PSST 1/12 receipt decoder in PPU, with explicit structural
  qualification and diagnostic failure retention. It does not admit a new
  firmware ABI or perform native stop/drain operations.
- [x] Add Linux's typed stop-request/receipt attributes with explicit ABI 1.6
  admission, bounded acceptance/read phases and preserved healthy IRQ draining.
  Actual-C register/IRQ models and ARM compilation pass; real kernel scheduling,
  feature-enabled firmware and paired native PPU recording remain unqualified.
- [x] Add explicit ABI 1.6/profile opt-in and bounded stop request/read APIs to
  PPU main, retaining raw/error/timeout evidence and existing legacy defaults.
  A completed API observation is not a healthy boundary or proof of delivery.
- [x] Test the actual digital shell/CDC/canonical/real-FFT/PSMA/PIL1 pair at
  reduced 447x2 geometry, including exact pilot bytes, independent source
  support bounds, continuing pilot after stop and a retained real late fault.
  This does not exercise ADC formatting, DDR DMA, native IIO or the fine engine.
- [ ] Keep map IRQ/readers alive until published, driver-enqueued and
  host-reassembled terminal generations agree. Use 200-chunk/one-map refills
  initially; a 400-chunk watermark can strand an odd final map after stop.
  Drain finite fine request IDs/results too: disabling submissions does not
  prove already-submitted work completed. Only then join readers and destroy
  buffers, with fresh terminal health and restoration receipts.
- [ ] Run deterministic digital replay through both branches; the existing
  short PSS-only injection fixture does NOT prove GLRT pilot capture.
- [ ] Test split IIO buffers, exact sample counts, shared counter mapping,
  saturations, slow consumers, buffer exhaustion, cancellation, and restoration.
- [ ] Progress through short, 30-second, and 300-second transport runs. Require
  zero unexplained gaps, bounded memory, complete terminal receipts, and TX mute.

### S3 — Hop-safe dual-product recording on .18

- [ ] Adapt the proven local scheduler/recall concept to the detector's counter
  and ownership interface. Do not require the legacy tandem FPGA identity.
- [ ] Preload eight Fast Lock slots and both edge coefficient sets. Keep source
  rate and analog bandwidth constant within each 300-second run.
- [ ] Initially publish one complete 64-frame PSS map per 120 ms visit and all
  paired IQ. Explicitly discard/account for the unfinished map at the boundary.
  A 120 ms visit is 90 canonical frames, not an integral number of 64-frame
  maps. A versioned intentional-tail-discard receipt must name the visit/fence,
  exact discarded start/count and last completed map. Keep intentional discard
  distinct from genuine discontinuity, preserve concurrent faults and completed
  tiles, and compare GLRT only on declared common coarse support while retaining
  all 120 ms of pilot IQ. Do not subtract an assumed abort from aggregate health.
- [ ] Tests: adjacent channels with distinguishable injected content; pulses
  immediately before/after every hop; no mixed-channel maps; no stale results;
  delayed recall; failed readback; counter discontinuity; lost events; disconnect;
  cleanup; repeated sessions without reboot. Prove the map restart limitation
  is fixed or safely avoided without weakening health gates.
- [ ] RF settling needs separate RF evidence; digital injection does not prove
  PLL/gain/DC settling. Do not assume a transmitter cable is currently available.

### S4 — Independent GLRT comparison and short-dwell PSS lock

- [ ] Run host GLRT on every valid visit, independently of FPGA candidate seeds.
  Preserve acquisition/control scores, timing/CFO uncertainties, and abstentions.
- [ ] Produce per-visit agreement, GLRT-only, PSS-only, neither, and unobservable
  classifications; compare matching time support and frequency references.
- [ ] Existing 64-frame maps take 85.333 ms; the old three-map qualification
  takes at least 256 ms and cannot be reused for a 120 ms visit.
- [ ] Replay 16/32/64-frame alternatives against frozen positives and negatives
  at equal false-alarm budgets. Version changed integration/qualification rules.
  A candidate option is three 16-frame maps in 64 ms, leaving about 56 ms for
  full-rate refinement; this is a proposal, not a sensitivity guarantee.
- [ ] Perform local candidate-to-fine handoff without an Ethernet round trip.
  Record CFO hypothesis, complete timing-search support, and matched/control
  evidence. Accumulate at candidate lags before selecting a weak-signal winner.
- [ ] Do not let post-run GLRT-guided replay masquerade as an independent online
  FPGA detection. Report diagnostic and primary results separately.

### S5 — Network deployment and live .17 qualification

- [ ] Only after .18 passes: exact-serial PPU network deployment, attested boot,
  firmware/HDL/kernel/host identities, and a tested rollback path. No USB on .17.
- [ ] S5a / Release A: short fixed-frequency integrity capture followed by
  qualified longer single-channel recording and independent live GLRT/PSS
  comparison. This may follow S2 without waiting for all S3/S4 hopping work.
- [ ] S5b / Release B: after S3/S4, one 300-second eight-target run at the
  qualified source rate, with 2.5 MS/s IQ and FPGA evidence from the same RX1
  stream. Fixed-frequency success does not complete this requirement.
- [ ] Require at least 95% measured valid duty, exact valid visit lengths,
  balanced target coverage, no unexplained drops/overflow/event gaps, and exact
  restoration. Repeat runs must not require unexplained radio resets.
- [ ] Require independently qualified host pilot evidence and FPGA fine PSS lock
  with compatible timing on live observations. If there is no usable RF signal,
  report transport qualification separately; do not claim the objective complete.

### S6 — Rate ladder and final handoff

- [ ] Qualify 15, 30, and 60 MS/s source builds through the same .18-before-.17
  gates. Output remains 2.5 MS/s; separate per-rate 300-second sessions.
- [ ] Publish comparison reports with uncertainties, confusion categories,
  observed CFO coverage, duty/latency/throughput, and controlled timing errors.
- [ ] Push tested reusable PPU changes to main and all experimental source pins
  to their do-not-merge remotes. Seal artifact hashes and independent replay.

## Current progress

### Idle mailbox admission and parallel alternatives — 2026-09-10

Follow-up audit-only HDL `aa1b2d52` completes read-only checks on both saved
receivers, preserving all constraints and requiring destination timing even
when a targeted dependency has disappeared.214 audit/constraint/build-policy
tests pass. The metadata-to-job-start combinational path is absent in the
candidate, but job-start from other sources still fails at-1.053ns and vendor
FFT internal paths fail at-.717ns. Final saved-DCP resources are13060LUT/
18575FF/4400slices/53.5BRAM/54DSP. No timing/CDC/hardware pass is inferred.
See `reports/experiments/20260910-routed-dependency-audit.md` and its archive.
The FFT-island agent is developing the next isolated bank-ownership slice;
no replacement has been integrated into the full receiver.

HDL `d1b3107b56c869d59724df2a8d695112a1f6ac3c` is pushed only to the
experimental DNM branch. It opts the actual service into an idle-only mailbox
fault predicate. Current output framing faults require a private write, which
requires an active guard; idle admission and ACK release require inactivity.
The sticky mailbox fault remains included. Active/nonfinal/final publication
checks and all fault reasons retain the full current mailbox fault; default
callers are unchanged. No arithmetic, latency, ABI or constraint change.

The expanded regression passes **970 tests**, with two older optional-netlist
cases skipped. Fresh phase-input and idle-mailbox guard netlists are included;
both idle modes match the frozen public guard over256jobs/131072words each.
The enabled netlist also passes real-bank ACK and six current-link corruption
cases against a frozen reference. Actual synthesis removes the full framing
input from job-ready only, retaining active/final/reason checks; both isolated
modes use111LUT/180FF. This is not an isolated or complete timing improvement
claim. Portable evidence also replays after relocation (12tests).

The actual FFT service passes26healthy jobs/13312exact words plus adversarial
reset/input/final/ACK cases, with actual idle/ACK/private-write premise checks.
Full coarse numeric replay returns1341exact scores, the64-block burst/stall
run returns28608ordered scores, and reduced paired PSMA/PIL1 replay preserves
894scores/2048pilot bytes plus a late real fault. These do not exercise native
ADC/DMA/IIO, fine timing or production duration.

The fresh complete15MS/s receiver build was launched at00:04UTC in
`hdl/projects/pluto/shared-realtime-idle-admission-v1`, with both detectors,
pilot DMA, boundary stop and the original clocks/constraints. It completed at
00:20:46UTC, exit1: setup WNS **-1.269ns**, TNS **-125.326ns**,355 failing
endpoints (351 on200MHz and four asynchronous recovery paths).100MHz passes
at+0.009ns; hold passes at+0.002ns. All34008 nets route without errors, but
timing regresses from the best `18c96bb9` reference. This candidate is rejected
for deployment; generated bitstream/bad-timing XSA are not qualified firmware.
The original13 input/two output delay gaps also remain. No radio was accessed
or flashed.

At the user's explicit request, three independent agents and firmware/HDL
worktrees completed first studies of (1) a consolidated FFT processing island, (2) a direct
time-shared66-tap coarse correlator and (3) narrower-rate/causal-GLRT assistance.
They do not change the selected receiver or the required native60MS/s fine
search. Worktree/branch ownership and bounded comparison gates are recorded in
`reports/starlink-coarse-parallel-evaluation-20260910.md` and
`docs/starlink-coarse-architecture-review-20260909.md`. Detailed current
candidate evidence is `reports/starlink-idle-mailbox-admission-20260910.json`.
The root independently reran20 new tests across the three studies successfully.
No alternative is yet selected: the island has no physical/outer-bank proof,
the direct slice fails numerical comparison and hold gates, and narrowband
assistance retains unresolved CFO aliases and unmeasured live handoff costs.

### Balanced private output-metadata check — 2026-09-09

HDL `65adf692da07422f10fea6c342b2711807ff7a89` is pushed only to the
do-not-merge branch. A stateless three-bit equality/six-way reduction tree
shortens the output mailbox's mapped metadata-check logic without dropping any
bit, delaying any veto, adding state, or changing legacy mailbox behavior.
The isolated framing cone has one CARRY4 instead of eight, at a cost of eight
LUTs and no extra FF/BRAM/DSP. Its *unrouted* delay estimate is worse; this is
not yet evidence of a receiver timing improvement.

The expanded regression passes **940 tests**, with two older-netlist cases
explicitly skipped. Both actual synthesized mailbox variants match frozen RTL
through 225 malformed metadata cases and 1536 healthy words each. A portable
retained-netlist archive also passes 45 follow-up replay/admission tests after
extraction into a different directory. Actual FFT replay preserves all 1341
numeric scores and reset recovery; the 64-block burst/stall workload passes
with 28608 scores. The paired digital shell preserves 894 scores, 447 map words
and 2048 pilot bytes, including the late invalid-release rejection.

Packaging passed. A fresh complete receiver launched at **23:14 UTC** in
`hdl/projects/pluto/shared-realtime-metadata-tree-v1`, at the original clocks
and constraints with both detectors, pilot DMA and boundary stop retained.
It completed at **23:25:50 UTC**, exit1. All33977 nets route without errors,
but setup failures increase from68 to **180**:100MHz **-0.044ns** (two failures),
200MHz **-0.910ns** (178 failures), TNS **-46.554ns**. Hold passes at+0.014ns.
Final resources are13099LUT,18532FF,all4400slices,53.5BRAM and54DSP.
The final read-only audit confirms the targeted metadata-to-job-start path
improves from-0.421 to **-0.183ns**, but still fails. The worst path is now
output-mailbox write-position[2] to service state[1], with5.700ns data delay,
of which4.438ns is routing. The input-cursor-to-result-fault path worsens to
-0.508ns. These are not grounds to promote the emitted bitstream/bad-timing XSA.

This is an unsuccessful complete-receiver timing-closure experiment, despite
passing functional tests. Preserve18c as the best measured physical baseline;
keep the candidate and netlists for reproducible comparison. The next control
investigation is idle job-admission feedback from the active private-write
framing checker. Any separation must first prove its real mailbox/guard phase
premise and retain full same-edge active/final vetoes and sticky fault reasons.
HDL `eb96c64738697c10b9c0abb379ab64f6a4a5c59c` adds only the tested read-only
path audit after this build; its runtime RTL is identical to built65adf692.
No radio has been accessed. Board-I/O/CDC/reset, native RX and paired IIO,
causal refinement, .17 live GLRT/PSS agreement, 120ms/300s hopping and the
15/30/60MS/s ladder remain required. Detailed evidence and replay instructions:
`reports/starlink-mailbox-metadata-tree-20260909.json` and
`reports/experiments/20260909-mailbox-metadata-synthesis.md`.

### Lower FFT clocks rejected by throughput evidence — 2026-09-09

Separate simulation-only trials at 150/175 MHz preserve the canonical 15 MS/s
source and exact generated FFT/RTL configuration. Both pass 1341 exact numeric
scores and reset recovery, but the 64-block burst/stall workload fails with an
energy-cache miss after 16/58 completed blocks, respectively. Observed block
interval rates are approximately 12.93/14.37 million scores/s. A required energy
entry has already been overwritten. These lower clocks cannot sustain the
unchanged pipeline; a short numeric pass or larger buffer is not a remedy.
The complete receiver retains its original 100/200 MHz clocks. No clock
or constraint change was promoted. The isolated experiment patch, 18 admission
tests and reproduction notes are archived under `reports/experiments/`; exact
receipts are in `reports/starlink-fft-clock-throughput-20260909.json`.

### Atomic private bridge-error summary — 2026-09-09

HDL `18c96bb93f0aea5f868fb8b4c15a2eb1bce7a873`, pushed only to the
experimental do-not-merge branch, replaces the 96-bit historical bridge-error
counter reduction with one exact sticky summary. Each of the five original
error sites sets it on the same edge as its unchanged saturating counter.
Current-event vetoes, public counts, reset semantics, both detectors, pilot
output, coefficients, clocks and timing constraints remain unchanged.

All **58 targeted tests** pass. The supplemental complete-controller shadow
covers every increment site, idle/active/terminal observations, staged rejection,
both resets and explicitly seeded saturation; all seven faulty variants are
rejected. Its decoded-bus injection is not native AXI evidence. Separate real
AXI/map traces remain cycle-identical to the frozen controller in all four
health/map-summary configurations. The broader suite passes **887 tests** with
two older-netlist cases explicitly skipped. Current guard/cursor netlists pass.
The actual FFT + paired shell replay preserves 894 scores, 447 map words and
2048 independent-oracle pilot bytes, including the real late invalid-release
fault. That replay uses reduced map geometry and is not live IIO/RF proof.

Acquisition IP packaging passed. A fresh complete receiver launched at
**22:37 UTC** in `hdl/projects/pluto/shared-realtime-bridge-summary-v1`, with
the original 100/200 MHz clocks and complete 15 MS/s paired profile. No prior
checkpoint was reused. It completed at **22:49:41 UTC**, exit 1: all 33861 nets
routed without errors, but the 200 MHz domain still fails. The **100 MHz domain
now passes at +0.019 ns**, with zero setup failures. Overall failures fall from
724 to **68**, all in the 200 MHz domain; WNS improves to **-0.421 ns** and TNS
to **-7.772 ns**. Hold passes at +0.045 ns. Final resources are 13068 LUT,
18505 FF, all 4400 slices, 53.5 BRAM tiles and 54 DSP.

The exact final-checkpoint audit at 22:51:28 confirms input cursor +0.133 ns,
return slot +0.194 ns and mailbox fault +0.287 ns. Vendor internal -0.206 ns
and publication -0.118 ns still fail. The worst path is now the output mailbox's
wide metadata check into the fast service's job-start control. Shortening that
logic must retain every same-edge private-link fault check and the now-passing
100 MHz paths. Lowering the FFT clock to 150/175 MHz is independently rejected
by throughput evidence above. Static board-I/O/CDC/reset safety and native RX
qualification are also still open. No radio has been accessed; the emitted
bitstream and `bad_timing` XSA are not eligible for deployment. Detailed evidence:
`reports/starlink-bridge-counter-summary-20260909.json`.

### PPU RX-interface matrix evidence — 2026-09-09

PPU main `4bc2ca6a50dd8dd3c925522acfff5466385fbfd5` adds a hardware-free
validator for complete AD9361 RX timing matrices. It checks the exact rate,
selected clock/data-delay readback and an explicit one-dimensional or square
margin policy, retaining negative/raw/hash evidence and rejecting malformed
reports. It does not collect a matrix, attest a radio, change settings or
qualify board timing. The pinned driver's test routine changes hardware state;
a successful command return alone is not proof that tuning succeeded.

All 72 focused tests pass; the hardware/firmware/browser-excluded regression
passes 2836 tests, with one unavailable seeded fixture skipped and ten cases
deselected. Changed-file Ruff and package mypy pass. The change is pushed to
PPU remote main and the primary checkout is fast-forwarded; its four unrelated
dirty files are byte-for-byte preserved and not published. No radio was accessed.
Native collection/restoration and the full hardware gates remain open. Evidence:
`reports/starlink-rx-interface-evidence-20260909.json`.

### Private input-cursor retirement — 2026-09-09

HDL `f96d0b0d89ee8a8d55a5107b464ebe1b957e789d` removes the metadata and
ordinal validation chain from the private input counter's enable. All public
delivery/certification checks still use the original pre-edge ordinal. A bad
beat may advance the private cursor only on its quarantine edge; no later
delivery or certificate can occur before the unchanged reset. The counter
saturates at 511. No public ABI, arithmetic, coefficients or constraints change.

All 11 targeted tests pass, including baseline/candidate synthesized checkers
with identity checking disabled/enabled. The actual FFT service now shadows
both input and result checkers against immutable references on real service
pins: 284647 public result comparisons and 13312 exact words pass. Isolated
synthesis removes 10/80 metadata/framing inputs from all nine cursor D/CE
fan-ins, with LUT counts 34 -> 33 / 59 -> 59. This is not timing proof.

The combined regression passes **877 tests**, with two previous-source netlist
cases intentionally skipped. Current guard and all four cursor netlists pass.
Numeric replay preserves 1341 scores and reset recovery; paired replay preserves
894 scores, 447 map words and 2048 pilot bytes including a retained late fault.
The finite burst/stall case delivers 28608 scores at FIFO high-water 358.
Acquisition IP packaging passed. The fresh complete receiver launched at
21:50 UTC in `hdl/projects/pluto/shared-realtime-input-cursor-v1`, retaining
both PSS stages, pilot DMA, boundary stop and the original constraints, with
global synthesis and no reference checkpoint. It finished at 21:54:54 UTC with
exit 1: **placement failed** (`Place 30-99`, could not commit all instances).
The original structural/constraint INIT gate passed, but there is no new routed
timing result. The failed candidate's optimized checkpoint contains 13445 LUT,
18472 FF, 53.5 BRAM tiles, 54 DSP and 443 control sets, below raw chip capacities.
One bounded `AltSpreadLogic_medium` diagnostic placed that exact checkpoint in
4398/4400 slices at 22:00:15 UTC. Pre-route estimates still fail and do not prove
routed timing. No constraints or source checkpoint were changed. HDL
`6090190c4442d2fd0e825136d87b692e2ad6deef` selects this measured policy for a
fresh full build, keeping runtime RTL unchanged. All 291 policy/provenance/
constraint/build-contract tests pass. The diagnostic checkpoint is not reused.
The fresh complete receiver launched at 22:03 UTC in
`hdl/projects/pluto/shared-realtime-input-cursor-medium-v1`; no final timing
result was available at launch. It finished at **22:22:29 UTC**, exit 1:
all 34025 routable nets routed with no route errors, but final timing fails at
**WNS -0.716 ns, TNS -167.843 ns, 724 setup endpoints**. Hold passes at
+0.011 ns. The saved final design uses 13103 LUT, 18548 FF, 4398/4400 slices,
53.5 BRAM tiles and 54 DSP. The exact-checkpoint audit at 22:28:07 confirms
the changed cursor now passes at +0.052 ns; the return slot passes at +0.214 ns.
The worst path is now the private bridge error-counter reduction into map RAM
control (100 MHz). The 200 MHz domain still fails at -0.494 ns; vendor internal,
publication and mailbox fault paths also remain negative. Worst slack improved,
but total slack and failing endpoint count worsened: this is not timing closure.
The emitted bitstream and `bad_timing` XSA are not deployment candidates.
The expanded read-only audit reproduces the older cursor's -0.956 ns path,
inventorying nine registers and 18 D/CE pins. Its 21 admission/policy tests pass.
No radio or PPU operation occurred. Evidence:
`reports/starlink-input-cursor-20260909.json`.

### Explicit final-only result authorization — 2026-09-09

HDL `0a1af8933bb7d9bc4f0fa78b3350196e98045cda` exports the guard's existing
qualified-final predicate separately for the explicit-commit output mailbox.
Ordinary result validity, private writes, actual mailbox checks, same-edge
fault vetoes and packet ABI remain unchanged. This removes the excluded
nonfinal input-validation branch from publication authorization.

The actual guard/mailbox structural comparison removes all three raw-input
fault ports from the publication register's fan-in. Composition LUTs fall
185 -> 179; 367 FFs and one RAMB18 remain. The 36-test targeted qualification
includes both current synthesized guard netlists, frozen public guard/mailbox
comparisons, all final-veto rows, late ACKs and private-link corruption. Actual
FFT replay matches 284647 public comparisons and 13312 words; numeric replay
preserves 1341 scores; paired replay preserves 894 scores, 447 map words and
2048 pilot bytes with late faults retained. A finite 64-block burst/stall run
delivers 28608 scores at FIFO high-water 358. The full suite passes 870 tests
with two intentionally unused previous-source netlist cases skipped.

There is no standalone routed result for this revision. The preceding final
checkpoint now identifies input-checker ordinal feedback as the worst path;
that separate private-cursor change is being qualified before the next full
receiver build. No radio or PPU operation occurred. Evidence:
`reports/starlink-final-authorization-20260909.json`.

### Certified phase-specific input veto — 2026-09-09

HDL `ccdf64365e8145113115f2e933ee8b2901f6d3e0` specializes input fault
checks only in actual reset-idle/completed-input final/ACK phases. Generic
callers retain the unrestricted checks by default. Same-edge duplicate-start,
vendor/transport faults, full active-input checks, sticky reason accumulation
and publication qualification remain. The final handshake is expanded explicitly
to avoid reconverging its excluded nonfinal fault branch. No FFT arithmetic,
coefficient, public packet ABI, clock or constraint changed.

The whole regression passes **861 tests**, including both actual synthesized
phase-mode netlists; two previous-source occupancy-netlist cases are intentionally
skipped. The actual FFT service matches the frozen public guard across 284647
comparisons, including duplicate starts at final/ACK. Numeric replay preserves
1341 exact scores, paired replay preserves 894 scores/447 map words/2048 pilot
bytes with late faults retained, and the finite 64-block burst/stall capacity
case delivers 28608 scores with FIFO high-water 358. These are simulation gates,
not radio qualification.

Isolated synthesis removes all three raw-input fault ports from job-ready,
active-state D, ACK-state D and commit-pulse D fan-in, replacing them with the
explicit phase predicate. This is not a routed timing claim. Its first real
dependency check failed at active state; the failed evidence is retained and
the unchanged gate passes after the explicit final-handshake expansion.

Fresh full receiver `hdl/projects/pluto/shared-realtime-phase-input-v1` launched
at 21:15 UTC with both PSS stages, pilot DMA and boundary stop retained, global
synthesis, unchanged constraints and no reference checkpoint. It finished at
21:29:59 UTC with exit 1: **timing failed**, WNS -0.956 ns, TNS -43.261 ns,
223 setup failures and zero hold/reset-recovery failures. Final-checkpoint
resources are 13094 LUT, 18503 FF, all 4400 slices, 53.5 BRAM tiles and 54 DSP.
All 33990 routable nets routed. The 200 MHz worst path is now the input checker's
ordinal comparator feeding its own position-counter enable. The 100 MHz domain
has 72 remaining failures, WNS -0.124 ns; RX and reported inter-clock paths pass.
The final audit completed at 21:31:25 UTC: vendor FFT -0.365 ns, publication
-0.114 ns and output-mailbox fault -0.708 ns. Board-I/O/CDC obligations remain.
No radio or PPU operation occurred. Detailed evidence and hashes:
`reports/starlink-phase-input-contract-20260909.json`.

### Atomic map-counter summary — 2026-09-09

HDL runtime `f284b9f5a909c1c64f9040ac3dd7b90e42e6e659` sets an exact sticky
fault summary atomically at all 15 existing map error-counter increment sites.
Counters, common-reset semantics and current-event vetoes are preserved. Only
the real same-clock/reset paired stop controller opts into this summary;
generic users retain all independent counter checks. No public ABI, FFT math,
coefficients or receiver constraints changed.

The 60 targeted tests pass: frozen full-map and public-controller comparisons,
all 224 generic error-counter bits, unused 0/1/X/Z summary inputs, actual map
errors before/during stop, rejected mutations, production 20000x64 map geometry
and actual wrapper/canonical-tap wiring. Isolated controller synthesis removes
224 counter inputs from stop admission's combinational fan-in, replacing them
with one summary input. LUT primitives change 928 -> 835 and FFs 1439 -> 1441;
this does not include new producer logic or prove whole-receiver timing.

Actual reduced paired FFT/PSMA/PIL1 replay preserves 894 exact scores, 447 map
words and 2048 pilot bytes, including the late-fault receipt. The complete
regression passes 851 tests in 157.74 seconds. Its first run's 14 failures were
legacy test-stub port mismatches; commit `af96c48e` updates that interface only,
retaining rejection of enabled stop and all real-engine tests.

The acquisition package was refreshed. Fresh receiver build
`hdl/projects/pluto/shared-realtime-map-summary-v1` started at 20:41:03 UTC from
clean tracked HDL `af96c48ed34a58d54c548b4a2dc414aeff593c39`, with both PSS
stages, pilot DMA and boundary stop enabled, unchanged constraints, and no
reference checkpoint. It finished at 20:51:17 UTC with exit 1: **timing failed**.
Final WNS is -2.183 ns, TNS -189.135 ns, 335 setup failures and zero hold
failures (WHS +0.014 ns). The 100 MHz domain passes at +0.029 ns and RX passes
at +2.200 ns; 332 failures remain within 200 MHz plus three 200 MHz reset-recovery
failures (-0.355 ns). Reported inter-clock paths pass.
Resources are 13092 LUT, 18502 FF, 4397/4400 slices, 53.5 BRAM tiles and 54 DSP.
All 33946 routable nets routed, but an emitted bitstream is not deployable.

The final-checkpoint audit completed at 20:54:20 UTC. Worst categories include
vendor-internal FFT -1.202 ns, publication -1.818 ns and mailbox fault -1.127 ns.
The receiver's worst path is input-mailbox position to result-guard active state.
Thirteen missing input delays, two missing output delays and CDC warning
obligations remain. HDL is pushed to the experimental do-not-merge branch.
No PPU or radio operation occurred. See
`reports/starlink-map-counter-summary-20260909.json` for exact artifact hashes.

### Registered-quarantine occupancy cut — 2026-09-09

HDL `52f921f69cbc1fd38e30db79911ef7ed761d229d` removes the complete
current-fault tree from the private FFT return-occupancy register. Existing
registered fault reasons mask effective active/return validity on the same
edge; the hidden occupancy can clear later. Exact current publication vetoes,
fault reasons, ACK ownership, payload/descriptor behavior and packet ABI remain.
No clock, physical constraint, FFT arithmetic or coefficient changed.

Actual isolated synthesis reduces the occupancy D-pin's raw validation-port
fan-in from 41 to zero; its CE is constant high. Guard LUT primitives fall
114 -> 110 with 180 FFs unchanged. This is not routed/full-receiver timing.
The 51-test adversarial guard suite passes. A new public-only reachable test
compares 256 complete jobs, 131072 words and all 254 faulted/two healthy ACK
combinations with the immutable ff4229 golden; both actual synthesized guards
also pass using the vendor's precompiled UNISIM models. Earlier source-model
Icarus initialization failures and test-harness corrections remain recorded,
not presented as receiver failures or omitted from the diagnostic trail.

Actual FFT service, three-block exact numeric replay, bursty/stalled 64-block
capacity and reduced paired digital PSMA/PIL1 shutdown tests pass. The complete
integrated run passes 821 tests in 152.87 seconds, including actual guard
netlists. None of these is native DMA/IIO, production-duration or live RF proof.
The acquisition IP package was refreshed successfully. Fresh full receiver
`hdl/projects/pluto/shared-realtime-guard-occupancy-v1` started at 20:07:51 UTC
from the clean tracked HDL pin above, with boundary stop enabled, the DSP
tracker retained, global synthesis and no reference checkpoint. By 20:12:27 UTC, synthesis and
the actual INIT_DESIGN structure/clock checks passed, with both PSS stages,
pilot DMA, ten reducer DSPs, 67 stop-controller and four map-fence registers.
The generated guard source hash matches the tested runtime. The build finished
at 20:21:18 UTC with exit 1: WNS -2.463 ns, TNS -147.397 ns, 543 failing setup
endpoints and zero hold failures. The final read-only audit finished at
20:23:04 UTC. All 34069 routable nets are routed, but 4399/4400 slices are used;
13 input and two output delay omissions plus CDC review remain unresolved.
The worst 200 MHz path is input-guard expected position to result-guard ACK
ownership; output publication is -1.899 ns and vendor-internal timing -0.884 ns.
The return-slot category improves to -0.636 ns, but overall worst slack is worse
than the preceding image. This is not a physical pass or radio promotion.
The next isolated experiment summarizes map error counters atomically for the
independent 100 MHz stop cone; it does not resolve the 200 MHz obligations.
See
`reports/starlink-guard-occupancy-20260909.json`.

### Existing DSP tracker selected for shared paired image — 2026-09-09

HDL `550c21172c8641472aa25797e830e4eb9eeb45e5` adds an explicit
`USE_DSP_REDUCER` choice. The shared paired receiver reuses the existing exact
DSP TRACK_ONE reducer; other profiles keep serial at 15/30 and DSP at 60 MS/s.
Both reducer implementations are unchanged. This preserves score, first-wins
ties, aperture and packet ABI, but changes service latency; it is not a claim
of cycle-for-cycle behavior or whole-receiver sustained throughput.

An isolated complete 15 MS/s tracking-core comparison measures 3744 -> 2977
LUT primitives, 3124 -> 2763 fabric FFs and 3 -> 13 DSP48E1s, with unchanged
RAM use. The unchanged OOC timing contract measures +2.111 ns unplaced setup
for both. These savings are not a whole-chip fit/timing result. Exact five-job
RTL packet comparisons, deliberate tie/denominator mutations, composed core
tests and explicit-DSP AXI wrapper tests pass. Existing integrated regression
passes 795 tests, and both raw-core and wrapper suites pass. The explicit-DSP
wrapper also matches every expected word across the existing 210-window
recorded-data fixture (5460 words, zero errors); this is assisted fine-window
replay, not blind or live acquisition.

The expanded 60 MS/s composed fixture initially requested its window too early:
the actual scheduler recorded one late rejection and zero admissions. Its
stimulus and expected winner now move together from center 400 to 1600 only
at that rate; real lead checks and publication timeout remain unchanged, and
both frozen baseline and candidate pass. No runtime failure was suppressed.

The tracker IP package now makes its selector an explicit integer rather than
an inferred derived boolean. Fresh full receiver
`hdl/projects/pluto/shared-realtime-track-dsp-v1` has actual BD readback=1 and
ran from the clean pin above. Its actual pre-placement gate passed,
including the ten-DSP reducer inventory, absence of the serial subtree,
both detector stages, pilot DMA and the original timing-path obligations.
Physical qualification remains open. No radio or PPU was changed. See
`reports/starlink-track-dsp-selection-20260909.json`.

At 19:35:38 UTC this receiver completed placement and saved its placed
checkpoint. It uses 13132 Slice LUTs, 18501 fabric registers, all 4400 slices,
53.5 BRAM tiles and 54 DSP48E1s, with 444 control sets. Placement has advanced
beyond the previous three-slice failure, but post-placement estimated setup
slack was -2.763 ns. This was a placement estimate, not routed
timing closure and no hardware promotion is allowed from this checkpoint.

The complete run finished at 19:46:00 UTC with timing failure: final WNS
-1.386 ns, TNS -290.129 ns, 1082 failing setup endpoints and zero failing hold
endpoints. The saved post-route checkpoint has 13226 LUTs, 18508 FFs and all
4400 slices occupied, 34122 fully routed nets and zero routing errors. The
read-only final audit measures vendor-internal -0.816 ns, return-slot -1.386 ns
and output-publication -0.450 ns. Thirteen input and two output delay obligations
and CDC-6/15/17 review remain open. An emitted bitstream is not a deployable
image. The following guard refactor is a measured path cut, not a promise to
resolve all these independent failures.

### Snapshot data-enable remap: replay passes, placement still fails — 2026-09-09

HDL `6ee01b7c399f06765ea387720a5c3ccfa6e62de1` retains local request
replication and applies `extract_enable=no` only to the snapshot payload.
The executable RTL, snapshot edge, reset/CLEAR and ABI remain unchanged.
Actual isolated pilot synthesis removes variable CE pins from all 616 payload
FFs, reducing control sets 76 -> 57 while adding 616 LUT primitives. Both
actual synthesized cores compare successfully through 38726 cycles, 12
snapshots, 396 AXI reads and 567 delivered pilot samples. Integrated regression
passes 608 tests; the complete 120 ms replay again preserves all 300000 CI16
samples exactly, with no capture/DDC faults or saturation.

The complete receiver finished with placement failure at 19:18:17 UTC:
2414 unplaced slices required versus 2411 available, a three-slice shortfall,
439 control sets and 17307 total LUTs. This improves the preceding placement
shortfall (nine) but does not establish fit or timing; it has no routed result
and is not deployable. The next measured resource option is the existing DSP
tracker above. See `reports/starlink-snapshot-data-enable-20260909.json` and
`reports/starlink-snapshot-data-enable-dwell-rtl-20260909.json`.

### Local pilot snapshot replication and actual netlist comparison — 2026-09-09

HDL `24bac44461c78868689ddb6b35e2f4edfd6d5d5d` adds only a local
`max_fanout=32` attribute to the registered pilot snapshot request. Snapshot
capture timing, reset/CLEAR behavior, data and ABI are unchanged. Actual pilot
core synthesis reduces the single 649-load driver to 22 drivers with at most
31 loads each, preserving all 649 loads. The cost is 21 additional LUT
primitives, 21 FFs and 20 control sets in the isolated core; this is a fanout
measurement, not a receiver fit/timing improvement claim.

Two actual synthesized pilot cores pass a public-interface comparison with
vendor primitive models: 38726 cycles, 12 snapshots, 396 AXI reads and 567 pilot
samples. The test covers live snapshots, held snapshots, output stalls,
overflow/drain, active-CLEAR rejection and reset, with unknown valid data/control
rejected. The RTL comparison and two deliberate snapshot-semantic mutations
also pass their expected gates. Integrated oracle/constraint regression passes
608 tests. The complete 120 ms PIL1 replay preserves all 300000 CI16 samples,
matching the integer oracle exactly, with zero capture/DDC faults or saturation
and a passing offline PPU parser. None of these tests accesses native DMA/IIO
or proves live RF detection.

The preceding health-summary receiver (`84a1a358`) finished with placement
failure: 2413 unplaced slices required versus 2408 available, a five-slice
shortfall and 441 control sets. It has no routed timing result. The new
snapshot-replication receiver in
`hdl/projects/pluto/shared-realtime-snapshot-fanout-v1` also finished with
placement failure: 2420 unplaced slices required versus 2411 available, a
nine-slice shortfall and 458 control sets. Its pilot IP package was refreshed;
clocks, exceptions and paired/shared-realtime/boundary-stop profile were
unchanged. Local fanout improvement has not produced complete-receiver fit or
timing improvement. Next reduce packing/control-set pressure without changing
snapshot semantics or weakening the detector's publication fences; an unchanged
rerun is not a demonstrated fix. Physical promotion remains closed; neither .18
nor .17 was accessed and PPU is unchanged. See
`reports/starlink-pilot-snapshot-fanout-20260909.json` and
`reports/starlink-snapshot-fanout-dwell-rtl-20260909.json`.

### Integrated stop-health simplification and final baseline timing — 2026-09-09

HDL `84a1a3589a08f5af72323755d38b9d7ef9153846` implements the explicit
same-epoch health-summary selection. Only the integrated stop-enabled wrapper
opts in; independent counter inputs remain conservatively checked by default.
Five redundant 32-bit counter reductions leave the stop-admission path, with
no added cycle, no change to the snapshot ABI, and no change to fatal causes.
Independent ingress loss stays checked; denominator-zero stays diagnostic.

The actual AXI controller/map-core bench now uses the actual health producer
before admission, after acceptance and around terminal retirement. Old/new
public traces are byte-identical for 10029 default-mode and 9754 summary-mode
cycles. Generic independent-counter and diagnostic-policy mutants fail as
expected. These are tested RTL workloads, not formal or native-IIO proof.
The integrated oracle/constraint suite passes 604 tests; acquisition wrapper
15/30/60 MS/s and pilot-only regressions pass. Isolated actual-controller
synthesis removes the counter-to-stop path, retaining the flag-to-stop path;
LUT primitives fall 936 -> 928 and FFs 1441 -> 1439. That is not a full-design
timing-improvement claim.

The preceding descriptor-BRAM receiver at runtime `653a3205` is now terminal:
its complete route has no routing errors, but post-route optimization still
fails WNS -3.737 ns, TNS -12470.662 ns and 9941 setup endpoints. All 4400 slices
remain occupied. Final read-only audits find pilot snapshot-enable fanout 649
(-3.384 ns), the FFT return slot (-3.737 ns), vendor FFT internals (-2.711 ns),
and a still-relevant health-counter-to-map-RAM-enable path (-3.351 ns).
Thirteen input/two output delay obligations and CDC review remain open. The
generated bitstream and `system_top_bad_timing.xsa` are not deployable.

A fresh complete receiver at `84a1a358` is running in
`hdl/projects/pluto/shared-realtime-stop-health-v1`, after refreshing its
acquisition IP package. The profile, clocks and constraints are unchanged;
no reference checkpoint is used. Neither .18 nor .17 was accessed. PPU is
unchanged. Source pins, retained tests, isolated synthesis, final baseline
audits and launch evidence are in
`reports/starlink-stop-health-integration-20260909.json`.

### Read-only timing-pressure inventory and stop-summary premise — 2026-09-09

The original descriptor-BRAM build is still live. It reached zero failed nets
and successful net verification in one routing phase, then performed an
incremental placement change and re-entered routing. That intermediate result
is **not** a completed route or timing pass. Runtime sources remain unchanged
from its launch pin while it runs; no radio has been accessed.

A hash-bound inspection of its saved **pre-route** physical checkpoint finds
two substantial paths: input-guard position through result-guard return-valid
at 200 MHz (9 logic levels, estimated slack -2.517 ns), and acquisition health
counters through stop admission into map control at 100 MHz (13 levels,
estimated slack -1.758 ns). Estimated routing accounts for 70.251% and 80.393%
of those path delays. Pilot delivered-count to first-index enables is another
100 MHz candidate. These are pre-route diagnoses, not final critical-path
rankings or measured improvements. Board input/output-delay obligations remain.

The first bounded experiment tests a premise for shortening the stop-control
path: the real health producer sets five sticky bits on exactly the same edges
as their corresponding saturating counters become nonzero. Six RTL runs cover
all 8192 simultaneous producer-input combinations, both FFT health-bit
conventions, and counter widths 1/3/32; four bad-premise/policy mutations are
rejected. The unchanged fatal mask, independent ingress-loss count and
diagnostic-only denominator-zero policy are preserved. The complete
oracle/constraint regression now passes 589 tests.

This is a **test-only proposal**, not a receiver change or formal equivalence
proof. A future implementation must retain conservative checking for arbitrary
independent controller inputs, explicitly select the stronger integrated
producer contract, compare actual stop/receipt behavior and measure the full
image. It does not solve the separate 200 MHz guard path or routing congestion.
Evidence, the optional QoR-report tool crash and the original live build state
are recorded in `reports/starlink-physical-pressure-20260909.json`.

### Descriptor BRAM: complete receiver placed, routing still active — 2026-09-09

Runtime HDL `653a3205bc7bd158a7267a9288beba63aebe12cf` selects block RAM
for the 161-bit, three-usable-entry fine capture descriptor FIFO. The FIFO
algorithm, public latency, retained payload, capacity and coordinated-reset
contract are unchanged. Six asynchronous-clock/reset-release combinations
pass against frozen old RTL and an independent queue oracle, including the
actual synthesized standalone BRAM netlist. Wrong-address, stale/cleared-data
and premature-synchronizer mutants are rejected.

The complete optimized receiver uses two RAMB36s and one RAMB18 for this FIFO.
Global synthesis also absorbs 144 bits of downstream winner metadata into the
RAMB36 output registers. An initial standalone-latency structural assumption
correctly rejected this different shape; inspection and public AXI/RX tests of
the **actual globally optimized tracker subtree** now verify the relevant
behavior. The first packet is checked in all 26 words, later packets' descriptor
metadata are checked independently, and a pending packet is retained for the
epoch-reset test. This is not a full-receiver ADC/DMA/IIO simulation. The new
read-only audit explicitly checks the fused shape, both pointer synchronizers,
clock ownership and normally timed read/registered-enable controls; it neither
changes constraints nor declares physical timing/CDC clearance.

The complete stop-enabled paired receiver has now **passed placement**. Its
placed inventory is 13276 LUTs, 18841 FFs, 53.5/60 BRAM tiles and **4400/4400
slices**, with 446 control sets. This advances beyond the older 65-slice
placement failure below, but leaves no spare slices. The original full build
`shared-realtime-descriptor-bram-stop-v1` is still routing, with congestion and
negative intermediate slack; no final route/timing qualification exists.
Do not restart it just because observation takes time, and do not deploy it.

The raw/fine regression and 15/30/60 MS/s AXI wrapper regression pass, including
210 recorded-data windows and the stronger successive-descriptor checks.
The full oracle/constraint regression passes 572 tests. Audit and
simulation-admission tests reject weakened paths, stale/unbound
inputs, missing pass markers and simulated fatal/error completion. Exact
source pins, completed evidence and the explicitly provisional physical
status are recorded in `reports/starlink-descriptor-bram-20260909.json`.
No radio or PPU worktree was changed. Next: consume the original route's
terminal result, inspect its real critical paths and complete physical gates
before the first paired native IIO canary on .18.

### Measured transform-FIFO BRAM storage — 2026-09-09

HDL `4c9a3b7358fa0e9122c80293e6e5021285582ac0` changes only the
transform FIFO's runtime memory attribute from distributed to block. Its
behavioral tokens, registered output latency, capacity, metadata checks and
fault handling are unchanged. Pinned cycle-by-cycle equivalence passes at
depths 2/4/8/16, with wrong-address and wrong-reset-payload mutants rejected.
The actual synthesized default-depth BRAM netlist passes against the frozen
old RTL, including 512 ordered words, stalls, full/drain, malformed metadata,
flush and reset. The first netlist run was correctly rejected for a missing
VCD output directory; the corrected run has no such diagnostic.

Isolated synthesis measures 132 -> 60 slice LUTs and 201 -> 86 FFs for two
BRAM tiles. The complete optimized receiver confirms its FIFO changes from
188 -> 122 LUTs and 198 -> 83 FFs. Nevertheless the full stop-enabled image
**still fails placement by 65 slices** (2449 required versus 2384 remaining),
with 438 placement control sets, 16920 total LUTs and 19147 FFs. Synthesis
uses 51 of 60 BRAM tiles. This is a measured resource reduction, **not** a
packing or timing improvement; no routed checkpoint or deployable image exists.

The actual reduced paired digital simulation preserves all 894 scores and
2048 pilot bytes, pilot continuation after stop, and a real late fault. The
full oracle regression passes 508 tests; focused tooling tests reject changed
checkpoints and unbound netlists. ADC/DMA/IIO/fine/production-duration and live
qualification are not inferred from these checks. Authoritative pins, exact
scope and terminal build failure are in
`reports/starlink-transform-fifo-bram-20260909.json`.

The next isolated storage experiment uses the already parameterized 161-bit,
three-usable-entry fine capture descriptor FIFO. It measures 125 -> 16 LUTs
and 184 -> 23 FFs for 2.5 BRAM tiles, without changing the receiver's current
distributed-memory selection. Before integration, test its synthesized BRAM
behavior with asynchronous clocks, retained metadata, wrap, backpressure and
coordinated reset, then the capture bridge and full receiver. This measurement
does not establish CDC safety, fit or timing. Neither radio was touched.

### Private idle observation clear — 2026-09-09

HDL `ced8a17d21e5ea00a134eb075a095d5ecf435955` moves six private
per-job observation clears out of the full fault-qualified admission mux and
into healthy idle/ACK wait. Active validation, immediate public fault veto,
descriptor holding, exact sticky reasons and faulted private-state freeze are
unchanged. This targets the measured output-mailbox metadata-to-input-counter
path; no clock or timing constraint was relaxed.

The 51 focused actual-RTL guard tests pass, including a nonvacuous 11-job ACK
clear witness and a rejected admission-only-clear mutation. The actual generated
FFT service passes 26 jobs / 13312 exact words with the existing fault/reset/ACK
cases. The actual reduced digital shell/CDC/FFT/PSMA/PIL1 pairing also passes
894 scores, 447 map words and 2048 exact pilot bytes, including pilot continuation
after stop and retained late invalid-release failure. These are not ADC/DMA/IIO,
fine detector, production-duration or physical qualification.

The fresh full stop-enabled receiver completed with placement failure in
`hdl/projects/pluto/shared-realtime-idle-clear-stop-v1`: 65 slices short
(2432 required versus 2367 remaining), 438 control sets, 17074 total LUTs and
19259 flip-flops. Compared with the preceding 63-slice shortfall, this is not a
packing improvement; no routed timing result exists. Its authoritative build
and test evidence is `reports/starlink-private-idle-clear-20260909.json`.
The full oracle regression passes 482 tests after updating the 25 existing BD
admission cases to execute the new shared validator. Physical fit/timing and
all native/live promotion gates remain open; neither radio was touched.

### Deployment work resumed — 2026-09-09

A fresh full-receiver diagnostic completed with timing failure from clean HDL
`1003cf0f84ef9c6661ff05483c992133ba6bc059` in
`hdl/projects/pluto/shared-realtime-private-descriptor-v1`. It measures the
private-descriptor change with the same explicit shared realtime 15 MS/s
paired-pilot configuration as the previous route. Packages were refreshed;
global synthesis was used and no incremental reference DCP was present. Final
WNS is -2.047 ns, global TNS -236.046 ns with 361 failing endpoints, including
18 reset-recovery failures. The saved-checkpoint read-only audit also measured
vendor-internal WNS -1.064 ns and publication WNS -1.819 ns. All 4400 slices are
occupied; 13 input and two output delay obligations remain unresolved. This is
not a deployable image. Launch pins and terminal evidence are recorded in
`reports/starlink-private-descriptor-build-launch-20260909.json`.

Boundary stop remained disabled in that diagnostic. The normal project entry
point now has explicit default-off `STARLINK_PSS_BOUNDARY_STOP` admission,
BD parameter/readback, and a synthesized stop-controller/map-fence state check.
The pure helper and actual Tcl entrypoint/constraint gate regressions pass;
they do not substitute for a separately measured stop-enabled receiver image.

The first stop-enabled full receiver (`b73758989a0a236fa429f23ee999628c42ed7e94`)
passed actual BD readback and the synthesized structure/clock gate (67 surviving
controller and four map-fence registers at 100 MHz), then failed placement by
63 slices: 2428 required versus 2365 available for the remaining instances,
441 control sets. No route or deployable image exists for it. See
`reports/starlink-boundary-stop-build-20260909.json`.

PPU `04b93d29753c7cdc3762e5f7a81e11d890bc331f` implements the actual finite
three-context paired recorder, explicit diagnostic fine schedule, raw durable
records and terminal delivery accounting. Sticky cleanup failure, late external
cancellation, stale epoch, producer/storage errors and process-control exception
retention have targeted tests. Its clean intended tree passes 2764 offline tests
(one skip, ten hardware/firmware/browser deselections), full Ruff and strict
mypy over 81 source files. This is not native `.18` DMA/Ethernet qualification,
an automatic candidate handoff, persistent 300-second recording, or live lock.
See `reports/starlink-finite-paired-ppu-20260909.json`.

The predeclared earlier-pilot held-out study is complete: later positive
baseline combined z 4.981/4.721 fails, fixed-prior assisted z 8.474/8.077 passes;
the negative prior abstains, both negative baselines fail, and all six combined
scrambled controls fail. One positive baseline individual map passes. Exact
limits and pinned evidence are in
`reports/starlink-capture25-causal-heldout-20260909.md`. Source order is not an
online latency or fine timing proof. No radio was opened and no frozen earlier
recording result was edited. `.18` remains the only local canary; `.17` is
reserved for subsequent network deployment after promotion gates pass.

### Targeted recorded 25 MS/s replay — 2026-09-09

Capture `cap-20260909T121248-414fb81f488c` has now been replayed offline on
two continuous, evidence-selected 320 ms windows. A documented +5 MHz
translation and 3/5 filtered conversion feed the frozen 15 MS/s PSS model;
this is not a new native 25 MS/s hardware profile. No radio was accessed.

The positive interval passes all three PSS maps and the combined gate with
the independently saved GLRT-derived +285.799 kHz correction (combined robust
z=9.96). Its uncorrected baseline fails (z=4.89). Both corrected and uncorrected
negative runs fail, as do all four combined frame-scrambled controls. The
independent 2.5 MS/s pilot model and blind GLRT distinguish the same intervals
without PSS seeds. No numerical clipping or FFT overflow was reported.

Coarse PSS and pilot phases are near 400 microseconds modulo the nominal frame,
but individual PSS lobes move and the combined drift optimum reaches the bank
boundary. This does not establish fine timing, a stable clock estimate or lock.
The tested windows are targeted, not held-out discovery or a false-alarm survey.
Full input/derivative/backend identities, limitations and next tests are in
`reports/starlink-capture25-replay-20260909.md` and its companion JSON receipts.
Actual recorded-data RTL numerical replay also passes for two three-block
snippets: all 1341 scores per snippet match their full-window C-model slices,
with all transform values and metadata checked. Support-matched PSS/GLRT phase
differences remain about 1–2 microseconds, not a fine timing bound. Physical
timing closure, paired hardware IIO and live lock remain unfinished gates.

### Private FFT observation enables — 2026-09-09

HDL `90c539cd4ea51bd0dbe3e8154177f62c388d394c` is pushed and remotely
verified. The remaining worst path in `9f7699cc` reached the result guard's
status-exponent enable through the full current fault cone. Private job
observations now update independently of that cone; immediate quarantine,
fault reasons, return validity and final publication gates are unchanged.
Ten directed fault edges witness all seven moved fields, 1408 quarantine
event combinations preserve exact public behavior/reasons against the frozen
golden, and 11 complete jobs verify reset recovery. Three mutants are rejected.

Actual service, exact-score and reduced native-stop XFFT replays pass on this
new runtime. A fresh same-clock/same-constraint full receiver build completed
in `shared-realtime-private-observations-v1`: 200 MHz setup still fails at
-1.722 ns with 361 failing endpoints, improved from -1.999 ns/444. The 100 MHz
domain (+0.237 ns), reset recovery (+0.318 ns) and hold (+0.021 ns) pass.
Boundary-stop remains disabled for this separate timing measurement. This
image is not deployable; no failing constraint has been waived.
The wider regression now passes 886 tests. Two preexisting legacy text-contract
failures are retained in the report; their replacements execute the actual
profile-specific DMA gates and compile exact multirate header contracts while
preserving historical manifest evidence. No runtime was changed for those tests. See
`reports/starlink-realtime-private-observations-20260909.json`.

### Checked publication with independent private RAM writes — 2026-09-09

HDL `9f7699cc91249d8386bdcd761011832ca6d69b07` is pushed and remotely
verified. The realtime result bank now separates private RAM/cursor updates
from final publication authorization. A held final word may be rewritten but
cannot publish until the original certificates and immediate vetoes pass.
Current private-link framing faults also veto the guard's commit receipt on
that same edge. No RAM, clock or healthy-path latency was added; the legacy
mailbox mode remains the default.

The combined regression passes 815 tests. Actual Vivado service, exact-score,
reduced-map and bursty-64-block replays all pass on the frozen new runtime;
the bursty run checks 28608 ordered scores, not every numerical value or a
120 ms horizon. The fresh full receiver build in
`shared-realtime-private-bank-v1` completed with 200 MHz setup failure:
worst slack -1.999 ns, 444 failing endpoints. The 100 MHz domain (+0.007 ns),
reset recovery (+0.184 ns) and hold (+0.050 ns) pass in this final report.
Boundary-stop integration is disabled, so its timing effect remains separate.
This is not a deployable image. See
`reports/starlink-private-bank-and-stop-integration-20260909.json`.

The preceding HDL `8129e8a0` implements the native stop controller. Its 10
dedicated cases and 76 adjacent cases pass, with independent review. The shell
test uses a declared toy scorer and proves continuing canonical-tap wiring,
not actual FFT/PIL1 shutdown behavior. A separate reduced real-FFT test now
passes: 894 exact scores, 447 exact map words and an actual unfinished third
FFT block at the boundary acknowledgment. Native map read/release and both
live-pending vendor-fault and post-terminal bridge-fault negatives pass.
The continued source is test stimulus, not canonical-tap/PIL1 DMA evidence;
the full pilot/fine/source-support join and production-duration tests remain.

### Private descriptor and production-like stop residue — 2026-09-09

HDL `deb9badcc9a521d4694ceebe0223c97344cb7566` separates private idle
descriptor capture from public admission/fault authorization. Focused tests
cover 2048 idle combinations, exact healthy metadata, active/final/ACK ownership,
same-edge faults and reset; six deliberate mutations are rejected. The root
regression passes 802 selected oracle/contract/policy tests, and actual real-FFT
service, exact-score and paired-pilot replays pass. The physical timing effect
has NOT been measured; the latest completed route remains the -1.722 ns failure.

The paired test now also admits explicit reduced 343x2 geometry: 686 scores end
at residue239 within a447-score block, matching production1280000 mod447. It
checks 343 exact map sums, ignores no real faults and preserves all2048 pilot
bytes. At acknowledgment,687 tagged scores have emerged but only686 entered
the map; the extra score did not leak into another map. The unchanged default
447x2 test also passes. These remain finite simulation tests, not full-duration
recording or deployment evidence. See
`reports/starlink-private-descriptor-and-stop-residue-20260909.json`.

The subsequent user-requested 25 MS/s recording diagnostic is reported above.
It does not add a 25 MS/s hardware profile or waive timing closure. Its explicit
translation/resampling, frequency-assistance and source-support limits remain.

### Paired digital stop and native PPU support — 2026-09-09

HDL `32a1f12cf457b68d09c89bf0e9dd6e7997039c3c` is pushed to the
do-not-merge branch. The actual digital acquisition shell now has a passing
combined simulation: 894 exact PSS scores, 447 exact native map words and all
2048 CI16 pilot bytes matched to an independent integer oracle. Pilot capture
continues after map-boundary stop; a subsequent invalid bridge release retains
its failed health and terminal coordinates. Two real idle bootstrap samples
establish a clean held canonical gap before ARM. The test explicitly pauses
for pre-roll configuration and uses reduced map geometry; neither is a live
production-duration or transport claim.

PPU main `dfd5e46a10f8edd7daf19b7172b28fbf8fb65579` is tested, pushed and
remotely verified. Both explicit experimental flags admit the exact shared-15
ABI 1.6 image/profile. Bounded native request/read calls retain raw PSST,
identity/contract observations, unknown writes, budget and elapsed-time evidence.
The immutable clean-copy suite passes 2707 tests (one skip, 10 deselections),
changed-file Ruff and 80-source-file mypy. Unrelated dirty PPU work is preserved.

The integrated terminal-generation drain ledger and paired pilot/map/fine
recorder are still open. Full-image timing still fails at -1.722 ns on the
preceding runtime route, which did not enable boundary stop. No radio was
accessed or flashed. Next gates remain timing closure, a stop-enabled full
build, production-duration tests, fixed-frequency same-support capture with
blind GLRT, then .18-before-.17 qualification and the complete 15/30/60 MS/s
scanner. See `reports/starlink-paired-realtime-psma-stop-and-ppu-20260909.json`.

### Native map-boundary stop driver — 2026-09-09

Linux `4357f41a721df9d89a66be7a2a3f921a71d46bad` is pushed to its
do-not-merge branch. New `acquisition_stop_request` and `acquisition_stop`
attributes require the exact shared-15 ABI 1.6 contract. Request success means
engine acceptance only; status polling returns diagnostic PSST words and keeps
the IRQ and IIO readers alive after a normal boundary stop.

The focused actual-C tests pass: both retained banks drain as 400 exact chunks,
six IRQ failure paths remain fail-closed, timeouts/vanished acceptance remain
errors, and independently changing receipt fields are retried or rejected.
All six admitted legacy/new image contracts and health receipts are exercised.
The ARM module builds, and the actual-C receipt passes PPU main's pure decoder.
This does not qualify real kernel timing, IIO transport, paired capture or RF
lock. PPU native admission was added subsequently as recorded above. See
`reports/starlink-map-stop-native-driver-20260909.json`.

### Private return/publication timing cut and production map fence — 2026-09-09

HDL `0463f887d592452c940d3c70589becc330d70a0c` is pushed and remotely
verified on the do-not-merge branch. It preserves public validity and immediate
fault veto while removing the expected-position dependency from all 51 private
payload register enables. A read-only old/new checkpoint audit confirms that
specific structural change; the nine mailbox write-position enables still
depend on expected position, so it is not a claim that timing is closed.

Conditional final-veto and private-payload mutation tests pass, alongside the
actual FFT service, exact score/map replays and a 64-block bursty run. The
combined regression passes 761 tests. The enabled map-core fence separately
passes the production 20000-bin by 64-frame geometry: 1280000 accepted scores,
20000 exact map words, correct 64-bit boundary and retained bank contents while
the input continues through host-like reads/releases. It remains default-off
and is not yet connected to native stop controls.

The full receiver build in `shared-realtime-publication-cut-v1` passed synthesis,
placement and routing, but failed timing: 200 MHz setup WNS -3.186 ns with 646
failing endpoints, plus seven reset-recovery failures at -0.501 ns. The 100 MHz
setup WNS is +0.055 ns and hold WNS +0.015 ns. The worst setup path reaches
output-bank metadata CE; independent vendor, validity and publication paths
also fail. It does not enable the new map fence. Later controller work is not
part of this frozen netlist. No radio has been accessed or flashed. See
`reports/starlink-realtime-publication-cut-20260909.json`.

One exact-net FFT direction-register replication attempt on that immutable
final checkpoint was rejected by Vivado 2022.2: the selected force-replication
option is not supported post-route. No rerouting or alternate mutation was
attempted; the original checkpoint is unchanged. This is a retained negative
experiment, not a timing fix. See `docs/starlink-xfft-direction-replication-trial.md`.

### Pure stop-receipt support in PPU — 2026-09-09

PPU main `5c78c01a3f6fa455c9ac86f43d77d0a1ecd171a2` is tested, pushed and
remotely verified. The pure proposed PSST v1 decoder preserves raw pending,
failed, empty and invalidated tuples; explicit qualification checks the exact
ticket and representable terminal map coordinates. Its 84 tests include all
24576 state/failure/command combinations. The exact clean committed archive
passes 2309 offline tests, Ruff and mypy (79 source files). No IIO client ABI
admission, native calls, radio access or deployment changed. See
`reports/starlink-pss-stop-receipt-ppu-20260909.json`.

### First measured realtime control-cone cut — 2026-09-09

HDL `2e552234336a5426adcecb538f5da5ced844b7d1` is pushed to the DNM remote.
It factors the idle admission predicate and removes the complete same-cycle
fault cone from the private watchdog's enable. Public fault/commit vetoes,
healthy watchdog deadlines, coefficients, numeric IP configuration and clocks
are unchanged. Differential RTL against immutable `ff4229bb` covers 23 healthy
and 37 rejected jobs, 12 resets, 12288 idle combinations and six watchdog
configurations. This is bounded executable comparison, not a formal theorem.

The new source passes actual-core service (26 jobs / 13312 exact words), score
(1341 exact values), reduced map (447 exact reads), and bursty 64-block capacity
(28608 ordered scores) tests. The expanded regression passes 737 tests. The
clean full receiver route in `shared-realtime-control-cut-v1` completes but
fails at -2.538 ns fast WNS, with 530 failing endpoints; slow WNS is +0.007 ns
and hold +0.021 ns. The watchdog dependency is structurally gone, while the
worst path now ends at mailbox write-position CE. Independent vendor and
publication paths still fail. The older frozen 4096-block soak
continues separately and cannot certify the changed source by itself. No radio
was accessed or flashed. See `reports/starlink-realtime-control-cut-20260909.json`.

### Bounded native fine-control evidence — 2026-09-09

PPU main `1245220f6078f9bcb3008aec9f6bacef83f5419e` is pushed and remotely
verified. Public current-index/control reads and finite fine-start receipts now
share the existing exclusive context lifecycle. Each schedule write, buffer
allocation and enable operation has retained attempted/returned/error evidence.
A normal enable-write return is driver acknowledgment; the later worker enable
flag and submission counts are not substitutes for that acknowledgment or proof
of result completion. Multi-attribute reads remain explicitly non-atomic.

The API preserves unknown writes and cleanup failures. Review fixed cleanup
ordering around receipt-construction failure and retained a known live handle
when destruction was never attempted; uncertain attempted destruction is not
retried. There are 91 new tests and 559 passing focused tests. The exact committed
clean export passes 2225 offline tests, Ruff and mypy. The 2230-test working-tree
run contains five unrelated dirty tests that remain uncommitted. See
`reports/starlink-pss-control-ppu-20260909.json`.

The durable concurrent paired recorder, map-boundary stop/drain, coarse/GLRT
support reconciliation and live .18/.17 qualification are still open. No radio
was accessed, and the native API does not infer new 30/60 MS/s contracts.

### Default-off realtime integration — 2026-09-09

HDL `ff4229bb230437fcd975413390a34c00ffcc226f` integrates the candidate behind
`STARLINK_PSS_REALTIME_XFFT=1`, requiring the existing shared selection,
paired-pilot profile and 15 MS/s. The new selector defaults to zero. Packaging
contains separately named fixed realtime/nonrealtime IP definitions, avoiding
environment-sensitive reuse of a cached library. The old IP definition,
coefficients, scores, source coordinates and PSMA 1.5 contract are unchanged.

Actual realtime and default-nonrealtime score replays each preserve 1341 exact
scores and 1536 exact words in each forward/product/inverse stage. Both final
source-matched phase replays preserve 447 exact map reads, zero healthy flags
and the existing bit-14 partial-map fault/abort receipt. Their three-frame,
447-bin map geometry is a reduced test, not a production-size tile proof.

The realtime bursty/stalled 64-block replay passes 28608 ordered scores with
bounded queues and zero forward stall cycles. It tests counts/order/backlog,
not every numerical value and not 120 ms. The frozen `ff4229bb` 4096-block
nominal replay has now passed: 1830977 source samples (122.065 ms nominal),
1830912 ordered scores, FIFO peak356 and bounded backlog. This is prior-source
counts/order/capacity evidence, not a current-source or numerical qualification;
see `reports/starlink-realtime-private-observations-20260909.json`. The expanded firmware
regression passes 714 tests, including executable selector and physical-gate
models. Those models do not establish actual synthesized endpoints or timing.

All original clock/CDC constraints remain. The new sticky source-fault crossing
has a narrow 5 ns first-stage bound, with both synchronizer flops, clocks,
ASYNC_REG markings and normally timed second-stage path required by the actual
implementation gate. A review caught and corrected a generate-hierarchy naming
mismatch before synthesis. The fresh full receiver now completes synthesis and
placement: 13284 LUTs / 18951 registers at synthesis (129 LUTs / 87 registers
fewer than d80), and an actual fully placed checkpoint. All 4400 slices are
occupied. The real implementation gate confirms one realtime core, both PSS
stages, pilot DMA, actual clocks and both new fault-synchronizer timing paths.
Routing is complete, but final post-route timing FAILS: the 200 MHz domain has
-3.531 ns WNS, -1008.150 ns TNS and 577 failing setup endpoints. The 100 MHz
domain passes by only +0.002 ns; hold passes at +0.049 ns. The longest path is
input-position certification through result-guard fault/admission logic to the
service state; the private watchdog enable shares that deep validation cone.
The generated XSA is explicitly `bad_timing` and is not deployable. The longer
frozen capacity run remains pending, and retained CDC warnings require review.
No radio has been accessed or flashed. See
`reports/starlink-shared-realtime-physical-20260909.json` for the final routed
evidence, separate from earlier synthesis and placement success.
See `reports/starlink-shared-realtime-integration-20260909.json`. After these
gates, native paired capture/stop/drain and .18-before-.17 live qualification
still precede the complete hopping/rate ladder.

### Latest explicit transport / registered CLEAR checkpoint — 2026-09-09

Receiver RTL `d80fd15490ce82b7eda151be4594433ac9e738f5` is tested and pushed
only to the DNM branch. The adapter now exposes an explicit metadata-independent
transport-ready output for mailbox retirement. The checker still accepts and
faults malformed stalled input immediately; all output/completion fences remain.
The actual synthesized netlist audit requires all nine position registers,
18 address-control pins and the BRAM read enable: the old routed metadata
dependency reached all 19 endpoints, whereas the new synthesis reaches none.
This is a demonstrated structural cut, not proof of routed timing closure.

Pilot CLEAR legality stays at its original inactive/empty check, but an accepted
command executes from a registered token one clock later. Capture, DDC and
snapshot state reset together before acknowledgment. Invalid CLEAR, STOP and
active fault/admission timing are unchanged. Eleven new actual-AXI race tests
and 74 prior pilot tests pass. The final combined firmware regression passes
533 tests, including the new physical-diagnostic admission/inventory guards.
The real checkpoint audit also confirms the pilot FIFO-count dependency changed
from 64 of 128 FIR job-index CE/D pins to zero; the registered CLEAR source now
reaches the 64 enable pins instead. All six FIFO registers and 128 destination
pins are required by the audit, preventing missing endpoints from faking a pass.
The fresh 120 ms pilot replay preserves all 300000 complex samples, exact source
coordinates and the prior CI16 hash, with no capture/DDC/clipping faults. It
executes AXI/DDC/AXIS RTL and the offline PPU parser, not Linux DMA/IIO or RF.

Current real-XFFT service replay passes 82 jobs / 41984 exact words and unchanged
29.74 us maximum pair latency. Exact numerical replay preserves 1341 scores and
phase-map replay 447 reads, including partial-fault rejection. The bursty/stalled
64-block capacity test passes ordered counts/backlog bounds; it does not compare
every score value with an oracle. The older 728d 4096-block run is now terminal
PASS (1830912 ordered scores / about 122 ms, bounded queues), but belongs to that
older revision and also checks capacity/order rather than all numerical values.
See `reports/starlink-shared-return-stage-capacity4096-20260909.json`.

Fresh full synthesis uses 13413 LUTs, 19038 FFs, 49 BRAM tiles and 48 DSPs. High
placement fails by 10 slices; the same opt checkpoint's medium trial fails by 12.
Neither produces a current routed timing result. Two further bounded physical
alternatives also fail: higher-effort placement is short by 6 slices, and area
optimization plus high spread by 87. All four trials are terminal; no build is
still running. RTL/clocks/constraints were retained. No hardware is qualified.
See `reports/starlink-shared-transport-clear-20260909.json`. A future realtime
service contract is documented in
`hdl/library/starlink_pss_acquisition/SHARED_REALTIME_CANDIDATE.md`; it proposes
511 private mailbox writes plus a held final word with independent status/fault
commit checks. Qualifying that candidate is the next architectural step, not
another assumption that placement settings alone will fix the design. Its
isolated input/private-result guards and synthesizable persistent service are
now implemented and actual-core tested; complete receiver integration and
physical timing are not qualified. All paired-live,
map-stop/drain, hopping, duty and 15/30/60 MS/s gates above remain open.

### Bounded PSS readers and realtime dependencies — 2026-09-09

PPU main `a0b4918a8e770d28ccf7eb4b289b836773f904aa` is pushed and verified.
Explicit batch mode retains actual native map/fine refill bytes before decoding,
including empty, short, malformed and negative observations. Admission caps
4096 scans and one MiB, applies a finite timeout and excludes concurrent context
operations. Completion requires exact decoded scan coverage. Interrupted final
decisions/accounting retain evidence and poison the stream; uncertain failed-open
cleanup quarantines the context and permits only joined teardown. Two independent
reviews and 250 focused tests pass. A clean export of the exact pushed commit
passes 1994 offline tests, Ruff and mypy; the 1999-pass working-tree run includes
five unrelated dirty tests that were deliberately not committed. See
`reports/starlink-pss-raw-batches-ppu-20260909.json`.

HDL `239f096fec99b3173c362ecf58be1a1efdc6ef93` adds isolated guards only;
the actual receiver remains the nonrealtime `d80fd154` runtime. The input guard
checks each demanded delivery immediately. The result guard reuses the output
mailbox for 511 private words and holds the last word until independent status
and all explicitly certified premises pass. Synthetic real-mailbox tests cover
late/missing status, malformed beats, exact commit-edge faults, reset and ACK
ownership. External reservation and event-fence premises are not proven by
supplying asserted flags in those tests. A registered admission token is required
when composing the guards to avoid readiness/fault combinational feedback.

The separate actual-XFFT delivery sweep passes 27 healthy jobs with 13824 exact
complex words and observes all 10752 output words wrong across 21 deliberately
starved jobs. Twelve vendor halt cycles arrive after the input phase, directly
disproving an input-phase-only halt check. Twenty explicit reset recoveries pass.
Observed two-clock event/status delays are not universal bounds. The combined
firmware regression passes 538 tests. See
`reports/starlink-realtime-guard-dependencies-20260909.json`.

The subsequent actual-core/both-mailbox joint replay now passes 12 healthy jobs
with 6144 exact published complex words and six missing-demand jobs quarantined
before any private write or publication, followed by six reset recoveries.
The coordinator and final-fence premise are still testbench-owned, and both
mailboxes reset between jobs. This does not prove prefetched-bank preservation
across local FFT resets or a synthesizable controller-owned final fence. Both
diagnostic runners now reject assertion-stopped/incomplete logs even when Vivado
would return zero. Corrected real replays pass; prior failed attempts remain
retained. The expanded firmware regression passes 573 tests. See
`reports/starlink-realtime-guarded-mailbox-20260909.json`; these diagnostic changes
are HDL `13df9535ef1acf22280135f30fd8347ae6fdabf4`, not a receiver promotion.

The subsequent synthesizable service now passes 26 actual-core jobs / 13312
exact raw and published words. Persistent mailbox ownership, per-job FFT/input
resets, synchronized sticky faults and a controller-owned cause-coverage fence
are implemented. Tests reject six demanded-input gaps, three final-edge vendor
faults, and malformed bank metadata at words 10/511; both raw reset inputs pass
interruption/recovery during configuration, partial input and queued-bank/ACK
ownership. A late ACK-drain fault remains quarantined. The six-job latency lane
measures 28.46 us per pair, including ACK/reset/config; it is not a capacity soak.
See `reports/starlink-shared-realtime-service-20260909.json`.

Next, qualify the explicit default-off integration with exact scores/maps,
current-source 120 ms capacity,
whole-chip resources, all timing constraints and CDC. None of the current guard
passes authorize flashing. The separate paired recorder still needs to compose
the now-available native fine admission with durable bounded recording, map-boundary
stop/drain and independent GLRT on proven common observation support.

### Exact finite fine-schedule ledger — 2026-09-09

PPU main `90eaecd74719539495399b5de00d37d4edb2c68c` is pushed and remotely
verified. Its pure immutable ledger checks each retained fine batch against the
kernel's exact Q32.32 carry sequence, finite request IDs, coefficient generation,
native batch accounting and external observation identity. It re-decodes raw
scans, retains negatives and malformed evidence, and refuses to advance the
accepted prefix on a failed batch. Full fine-search capture and actual winning
support remain distinct. No FPGA result selects or seeds the GLRT comparison.

The 140 new tests and 337 combined contract tests pass. Independent review also
compared 97373 centers from 3000 manifests against the kernel recurrence. A clean
export of the exact pushed commit passes 2134 offline tests, Ruff and mypy; the
2139-test working-tree run includes five unrelated dirty tests not published.
See `reports/starlink-fine-schedule-ppu-20260909.json`.

This is explicitly the qualified 15 MS/s shared processing geometry, not inferred
30/60 MS/s support. Native current-index and schedule-acceptance receipts are now
implemented separately; durable transition ownership, concurrent paired capture
and graceful map stop/drain are still required. Separation between validated fine
anchors is not continuous
sample coverage or measured timing lock. All live and full scanner gates remain.

### Latest counter/retirement checkpoint — 2026-09-09

PPU main `ffc41137f71c6156897148754c831c851b07bcf6` now exposes bounded
immutable ARM/origin/IQ/terminal events from the finite pilot reader and an
external cancellation token that survives startup. Queue overflow fails closed
and preserves partial IQ/cleanup evidence; a terminal event is best-effort,
never the sole completion authority. The new origin is published only after
an actual refill. Review caught the driver's mandatory preenable CLEAR resetting
snapshot generation: ARM now starts a new epoch, and only later snapshots must
increase within it. The shared fake models that real lifecycle. Cancellation
during final hashing also invalidates completion. Fifty-seven new tests bring
PPU's offline suite to 1880 passed (one skip, ten deselections); 210 focused
tests, Ruff and mypy pass. These hooks do not yet implement the paired recorder,
disk persistence, live evidence or300s streaming. See
`reports/starlink-pilot-iio-progress-ppu-20260909.json`.

HDL `6b58ea9223402ef301be92c6c5930c9c0f0f8e4f` is committed and pushed
only to the experimental DNM branch. The shared service advances its private
output-position counter from the raw healthy-phase handshake; dedicated users
retain the validated default. Publication, exponent/status validation, sticky
faults and final completion still use their original checked gates. Mailbox
retirement additionally requires core readiness, removing malformed-input
readiness from the retirement feedback path without delaying its adapter fault.

The combined firmware/oracle/contract regression now passes 494 tests, including
the isolated realtime probe's admission guards. Differential
adapter tests cover 30 first/middle/final faults in each identity-check mode.
Real two-clock XFFT replay passes 82 jobs / 41984 exact words, including six
malformed-input-under-stall cases: the adapter faults immediately while mailbox
storage/ACK stay held. The maximum saturated pair remains 2974 clocks at
100 MHz (29.74 us). Numerical replay preserves 1341 scores and all transform
words; phase-map replay preserves 447 reads and rejects partial faulted maps.
Bursty/stalled 64-block replay preserves 28608 scores with explicit backlog
bounds; this does not replace longer-duration qualification.

Fresh full receiver build `counter-retirement-v1` synthesizes to 13427 LUTs,
19037 FFs, 49 BRAM tiles and 48 DSPs. Medium-spread placement fails by thirteen
slices (2378 available versus 2391 required, 446 control sets). A bounded
high-spread trial of its saved opt DCP now places and routes all 33486 nets
without route errors, retaining the same 100/200 MHz clocks, constraints,
coarse/fine detectors and pilot DMA. Setup still fails:100MHz -0.421 ns /
421 endpoints,200MHz -1.027 ns /303 endpoints. Hold +0.025 ns and bus-skew
checks pass. Final resources:12943 LUTs,19070 FFs,49 BRAM tiles,44 DSPs.
Total setup violations increased from315 to724 endpoints (TNS -133.855 ns),
so this is NOT an overall timing win or deployment qualification. The routed
worst200MHz input-retirement path still includes the metadata comparator;
the intended Boolean simplification was not sufficient. Explicit transport
readiness must separate that cone. Pilot FIFO/stop-to-DDC control and vendor
BFP-RAM (-0.905 ns) / CE-prediction (-0.678 ns) paths remain independent gates.
See `reports/starlink-paired-counter-retirement-high-route-20260909.json`.
The older completed route below belongs to the prior source. No radios accessed.
See `reports/starlink-shared-fft-counter-retirement-20260909.json`.

### Completed control-isolation checkpoint — 2026-09-09

The completed physical checkpoint uses RTL
`2e3280ce63a750b5843d1803e8679537a5bac80a`; subsequent HDL diagnostics and
fault-semantics documentation do not change that frozen receiver RTL.
Both are pushed exclusively to the DNM branch. The pilot now registers the
whole IQ/index/visit/support observation before output FIFO admission. Its
one-clock transport latency does not change signal coordinates or filter delay.
Twenty adversarial boundary cases cover termination, combined STOP/full/index
conditions, counter exhaustion and the final-admission/internal-DDC-fault edge.
The latter retains sticky DDC fault evidence even if capture auto-stop precedes
its observation of registered DDC halt; both fault domains remain mandatory.

The shared FFT separates descriptor capture, local return state and transport
fault detection while preserving checked words and the final completion fence.
Current real-XFFT tests pass 76 jobs / 38912 exact words, six final/drain faults,
two drain resets, and two blocked-return cases. Numerical replay preserves all
1341 scores; phase-map replay preserves 447 exact reads and aborts a faulted
partial map. A current-source bursty/stalled 64-block replay preserves all
28608 scores and passes explicit backlog/retention bounds. The older-source
4096-block run remains live and pending; it does not qualify this newer source.
The current firmware/oracle/contract regression command passes 444 tests.

Linux `ab93ab53638a8837990053250a9971c59f30c310` adds read-only, serialized
`PSMH 1 46` health receipts and is pushed only to DNM. Fresh coherent fault
snapshots catch faults after the last map. Live DDC telemetry is explicitly
separate (including the paired-30 low-word-only ABI limitation). Actual C and
real RTL register-mapping tests cover late faults, all admitted ABIs, busy/timeouts,
generation races and bounded counter reads; ARM compilation/checkpatch pass.

PPU `1828eba15ad7c150909c79d291ec1b310a7f3de6` is pushed to main: strict
fresh health decoding, explicit joined-reader cleanup without native cancel,
retained failed receipts, and a two-second finite pilot envelope (120 ms default
unchanged). Offline tests: 1745 passed, one skip and ten deselections; 284 focused
tests, Ruff and mypy pass. Direct decoding of the actual Linux C-harness golden
also passes. Four unrelated PPU edits remain untouched.

The full `control-isolation-v1` receiver synthesizes to 13416 LUTs, 19037 FFs,
49 BRAM tiles and 48 DSPs. Medium-spread placement fails by four slices (2383
remaining available versus 2387 required), with 449 control sets. A bounded
high-spread trial of the same saved opt DCP now places and fully routes all
33446 nets, with zero route errors. Clocks, timing exceptions and detectors
are unchanged. Setup still fails: 100 MHz WNS -0.289 ns / 28 endpoints;
200 MHz WNS -1.035 ns / 287 endpoints. Global hold +0.019 ns and all four
bus-skew checks pass. Final utilization is 13011 LUTs, 19071 FFs, 49 BRAM
tiles and 44 DSPs. The reduction from 1755 to 315 setup-failing endpoints
compares both changed RTL and placement, not an isolated causal experiment.
The current 120 ms pilot replay passes all 300000
supported outputs with exact IQ hash
`d653ccfb1f3fb48d10c5c859b316074dc2b7e3229681294b611301043dda97a1`,
zero capture/DDC faults and zero clips. This exercises RTL AXI/DDC/AXIS and the
current offline PPU parser, not actual Linux DMA/IIO or RF. There is still no
deployment qualification. The worst 200 MHz path is the expected-output
counter's validated enable feedback (-1.035 ns); input-mailbox retirement is
next (-1.006 ns). An independent vendor-internal index-to-CE-prediction path
also fails (-0.756 ns), so wrapper changes alone cannot prove closure.
Thirteen missing RX input delays and two control-output delays remain separate
board-interface qualification work; they are not waived by internal timing.
No radio was accessed. Fixed-frequency paired orchestration, complete common
source support, live lock/GLRT comparison, hops and the rate ladder remain open.
Source pins and completed artifact hashes are recorded in
`reports/starlink-paired-control-isolation-20260909.json` and the terminal
`reports/starlink-paired-control-isolation-high-route-20260909.json`.

A separate source-pinned FFT diagnostic applied the actual 5 ns clock during
synthesis as well as implementation. It retains the frozen radix-4/BFP18
architecture and produces exactly the same measured internal +0.168/+0.053 ns
setup/hold slack, CE-cone delays and resource counts as the historical 10 ns
synthesis / 5 ns implementation probe. This does not fix the integrated core
path or justify changing production IP configuration. Its 50 unqualified OOC
boundary hold warnings remain excluded from the explicitly internal-only gate;
see `reports/starlink-shared-fft-actual-synthesis-clock-20260909.json`.

An explicit, diagnostic-only realtime-throttle probe removes the standalone
CE predictor and measures 1172 LUTs / 2988 FFs / 658 slices: 111 LUTs, 131 FFs
and 78 slices below the nonrealtime baseline. Internal setup/hold are
+0.192/+0.052 ns, only 24 ps better setup. This changes the vendor handshake
interface and is NOT a drop-in qualified service. No production XCI changed.
Including the unqualified OOC boundaries, hold still fails at -1.195 ns across
38 endpoints; the positive register-to-register result is not overall closure.
Before considering it, prove input starvation handling, status/data ordering,
unbackpressured output capture, exact numeric replay and full-service fences;
then remeasure the full receiver. See
`reports/starlink-shared-fft-realtime-feasibility-20260909.json`.

A separate isolated actual-IP realtime observer now preserves seven healthy
jobs / 3584 exact 36-bit complex words, exponents and framing, including three
no-reset direction changes. It measures status arriving TWO 200 MHz cycles
after the first data, so the current service's wait-for-status output
backpressure cannot be reused. Withholding 64 ready input opportunities during
an active frame produces 512 incorrect output words while index/TLAST/exponent
checks still pass; the core emits 64 input-halt cycles, first observed two clocks
after the gap. Explicit reset restores exact replay. This proves the need for
qualified starvation quarantine and unbackpressured early-data retention, not
a universal halt rule or integrated-service qualification. No production RTL
or XCI changed. See `reports/starlink-shared-fft-realtime-protocol-20260909.json`.

PPU main `18608952f76515c1e047dad0cf1d1690f24434a2` adds a pure, explicit
paired15/shared-ABI1.5 source-support profile with 78 focused tests. It binds
observation identities, pilot filter histories, actual FFT-block processing
envelopes and fine capture windows; joins retain negatives and incomplete or
unobservable records. Geometric inclusion does not prove complete coverage,
health, continuity, fine-request completion or lock. Initial boundary maps
may be unobservable, and nominal dwell duration is not the first-to-last-center
span. Separate 30/60 profiles and the actual paired recorder remain required.
The repeated PPU offline suite passes 1823 tests (one skip, ten deselections);
the source-support Ruff/mypy checks pass. Evidence and source hashes are in
`reports/starlink-paired-source-support-ppu-20260909.json`.

The concurrent-recorder audit also found a terminal-policy dependency:
disabling the current map engine during FILL increments its aggregate
`discontinuity_abort_count`. The new graceful-close health receipt correctly
rejects that condition. Do not forgive it just because software intended to
stop. Implement and test an explicit bounded terminal-discard receipt or
stop-at-map-boundary protocol before claiming a fully healthy paired session.

### Return-stage implementation checkpoint — 2026-09-09

The following supersedes the status of older, dated experiments below; it does
not turn their source-specific results into evidence for a newer build.

- HDL `728d2c873d882b148514c7a224c9193af289ab68` is pushed only to the DNM
  branch. The FFT adapter's redundant first-input output-counter reset is gone;
  registered return words retain their descriptor through an explicit final-word
  completion fence. The pilot overflow bit is computed beside its decoded
  counter from the same synchronized Gray word, with unchanged fault visibility.
  Halfband folded read addresses now walk in registers without changing the
  arithmetic, issue spacing, or 13-clock start-to-transfer latency. Paired-only
  30 MS/s observation counters are widened for 300-second accounting.
- The firmware regression suite passes 429 tests. Actual adapter/CDC/halfband
  tests cover same-edge health, independent resets, absolute-index preservation,
  address wraps, numerical samples and latency. Real-XFFT replay preserves all
  1341 scores and transform words. Both 74-job service profiles pass final-word
  fault/drain/reset tests. Measured pair service is 28.52 us without stalls and
  29.74 us with the declared injected stalls; the latter is not intrinsic engine
  headroom. Nominal and bursty/stalled 64-block coarse runs retain all 28608
  scores and report bounded queue/retention ages. The current 4096-block run is
  still pending, not interchangeable with the older long-run proof.
- The full 120 ms PIL1 RTL replay exports 300000 exact supported samples,
  1200000 CI16 bytes, zero faults/clips, and the same IQ SHA256
  `d653ccfb1f3fb48d10c5c859b316074dc2b7e3229681294b611301043dda97a1`.
  Independent blind GLRT again passes the synthetic signal and noise controls
  after current RTL export. These are not DMA/IIO or live RF evidence.
- Reusable PPU finite-reader support is pushed to main at
  `953cc68475ff78b4b5f3fb4b6969bdf6928b1c01`: exact serial/rate/buffer admission,
  bounded reads, complete/partial receipts, acknowledged-close-oriented cleanup
  and restoration, plus rejection of silent partial-map restarts. Offline tests:
  1660 passed, one unavailable-transmitter skip, ten hardware/browser/firmware
  deselections; full Ruff and mypy pass. This API currently caps finite captures
  at one second; persistent 30/300-second recording and paired upstream/PSS
  health integration remain required. Four unrelated PPU edits were preserved.
- Matched Linux `6e062f2ca4e133c88e9c010d53a22d8c06c8de99` is pushed only to
  the DNM branch. It rejects odd/oversize/mismatched finite DMA geometry before
  ARM and detects actual backend capping while preserving in-flight ownership.
  Executable tests run the real driver lifecycle and DMA submit helper against
  MMIO/controller mocks; ARM compilation and checkpatch pass. No fabricated
  partial-descriptor completion or IRQ guarantee was introduced.
- The completed `return-stage-v1` full build synthesizes to 13407 LUTs,
  18908 FFs, 49 BRAM tiles and 48 DSPs. Its high-spread placement fails by
  12 slices (2376 available versus 2388 required for remaining instances);
  the bounded medium-spread trial on its saved opt DCP completed at 04:02 UTC
  with unchanged clocks/constraints. All 33356 routable nets complete with zero
  route errors, but setup fails at -0.968 ns (100 MHz) / -1.632 ns (200 MHz).
  Hold and all four declared bus-skew checks pass. The final utilization is
  13000 LUTs, 18961 FFs, 49 BRAM tiles and 44 DSPs. This is worse setup slack
  than the earlier routed source (-0.304/-1.364 ns), not a timing improvement.
  There are no unconstrained internal endpoints or combinational loops, but
  13 RX input and two control output delay warnings remain separate board-I/O
  qualification gates. See
  `reports/starlink-paired-return-stage-medium-route-20260909.json` for completed
  artifact hashes, exact path evidence and the independent vendor-core failure.

No radio was held, accessed, or flashed in this checkpoint. Next remains
complete-receiver placement/timing and board-I/O/CDC qualification, then matched
paired .18 canary capture before PPU network deployment to .17. The full
120 ms L/U hopping, 300-second duration, independent live agreement and 30/60
MS/s gates remain open.

Read-only source review is complete. No radio has been opened, retuned, or
flashed during this scanner task. The S0 compiler and existing PSS geometry
regression suite initially passed 38 tests using PPU's Python environment. The compiler
also executes with Python `-I -S` and no third-party packages. S1–S6 remain
unqualified. The added pilot-DDC tests bring the focused suite to 76 passing
tests. A 31-tap halfband plus 255-tap divide-by-three FIR, with pinned Q17
coefficients, meets the requested 2.2 MHz passband with less than 0.01 dB ripple
and greater than 70 dB modeled stopband rejection. The Q16 mixer uses a shared
64-entry phase table; upper/lower frequency steps are +12/-13 table positions
per canonical sample. Group delay is exactly 269 canonical samples; complete
filter history spans 538 canonical samples. Tests cover both edges, arbitrary
chunk splits, explicit hop resets, ties-even arithmetic, clipping accounting,
and independent floating convolution. This is not a complete RTL fit or RF
qualification.

The next checkpoint adds 26 RTL tests for the 255-tap /3 stage; the full oracle
and scanner-plan suite now passes 133 tests. Direct integer convolution agrees
exactly across minimum 13-clock input spacing, nominal 13/13/14 pacing, arbitrary
initial phases, high source indexes, ring wraparound, clipping, invalid support,
flush boundaries, and fail-closed index/phase/overspeed faults. The stage uses
eight time-shared DSP MACs and four block-RAM tiles in the standalone synthesis
experiment. Mixer/halfband/pacer RTL, whole-receiver fit/timing, IIO, host GLRT
comparison, and all hardware deployments remain open. See the HDL submodule's
`library/starlink_pss_acquisition/PILOT_DDC.md`; the standalone routed timing
gate explicitly does not qualify the unplaced OOC boundary ports or the full
receiver. No radio access has occurred as part of this new scanner work.
The retained checkpoint is
`reports/starlink-pilot-fir3-offline-20260908.json`: 1105 LUTs, 472 fabric
registers, eight DSPs, and eight RAMB18s. Internal routed setup/hold slack is
+0.145/+0.104 ns at 100 MHz. Unplaced boundary hold failures remain reported;
this is not a whole-design timing pass and does not authorize a deployment.

The assembled canonical pilot DDC now passes 52 additional RTL tests, including
the existing 30/60 conditioners upstream, for 185 tests in the full oracle/plan
suite. A separate 120 ms CW replay accepted 1,800,540 inputs and emitted 300,090
outputs: exactly 300,000 supported samples after 90 startup-invalid results,
with zero overflow or saturation and FIFO high-water one. Standalone synthesis
uses 2514 LUTs, 2551 registers, fourteen DSPs and eight RAMB18s. Internal routed
setup/hold slack is +0.173/+0.053 ns at 100 MHz; boundary ports and whole-shell
timing remain unqualified.

Three 20 ms fixtures also pass exact RTL/reference agreement followed by blind
host GLRT acquisition: lower-edge and upper-edge positives and noise-only.
Positive GLRT margins are about 0.908/0.877, compared with 0.00877 for noise;
both positives recover the known frame epoch on the output grid and CFO within
1.2 Hz. These are strong synthetic fixtures, not a measured live sensitivity
or false-alarm specification. Reports `starlink-pilot-glrt-*-rtl-20260908.json`
retain source/IQ hashes, independent candidate scores, and explicit false live
RF/PSS-lock flags. Receiver/DMA/IIO integration, runtime PSS edge banks, hop
fences and short-dwell lock policy, full-shell timing, and .18/.17 deployments
remain open. No radio has been touched during these scanner implementation gates.
The aggregate checkpoint is `reports/starlink-pilot-ddc-offline-20260908.json`.
The next implementation step is the opt-in paired pilot capture profile: expose
the existing canonical tap, add a single-RX post-decimation DMA and its truthful
2.5 MS/s IIO device/counter contract, then close full-shell timing before .18.
Do not replace that integration gate with more standalone arithmetic passes.

### Paired receiver integration checkpoint — 2026-09-08

The opt-in `paired-pilot` block design now connects the existing canonical tap
to a complete pilot exporter and AXIS-to-DDR DMA, preserving both coarse PSS
and the full-rate tracker. The new PIL1 AXI control exposes atomic snapshots,
immutable visit identity, exact contiguous-prefix counters, bounded output
FIFO loss detection, and an optional hardware-supported-sample limit. Its
initial integrated profile is explicitly upper-edge-only, not eight-target
hopping. See `hdl/library/axi_starlink_pilot_capture/CAPTURE_ABI.md`.

`linux/drivers/iio/adc/adi_starlink_pilot.c` and the separate opt-in
`zynq-pluto-sdr-paired-pilot.dts` compile with the workspace ARM toolchain.
The module is not enabled in the default defconfig or installed/autoloaded in
the root filesystem yet. This is a compiled frontend, not an IIO capture pass.
Source clock admission, both-IQ scan-mask admission, explicit DEV_TO_MEM DMA,
pre-arm DMA submission checks, serialized snapshots, and stop-before-DMA-abort
are implemented. Queue-drain failure is reported and blocks re-arm; bounded
hardware recovery, partial descriptor accounting, and fault propagation to the
host reader still need execution tests before deployment.

Verification now includes 60 real-DDC/AXI/AXIS capture tests (rate reporting at
15/30/60; canonical stimulus remains 15 MS/s), plus compiled device-tree
isolation and driver-contract checks. Existing acquisition-wrapper tests pass
at all three rates with map-only and pilot-only enable ownership. Replayed
upper-edge published pilot/PSS IQ still matches the integer oracle exactly;
blind host GLRT recovers epoch 1622 and CFO 42000.9399187 Hz, with unchanged
margin 0.877051434. This remains a synthetic result, not an FPGA PSS lock.

The **complete 15 MS/s receiver** has now been synthesized and placement has
been attempted twice. First synthesis: 15697 LUTs, 23151 FFs, 53 BRAM tiles,
65 DSPs. Placement failed packing (2752 unplaced slices needed vs 2082 available).
A bounded ExploreArea/Explore diagnostic also failed; that diagnostic opens a
synthesis checkpoint without the project-generated clocks and is **not timing
evidence**. Do not interpret its timing report as receiver qualification.

The halfband implementation was then changed from parallel history/pair
registers to even/odd RAM rings and shared pair arithmetic, preserving the
frozen coefficients, exact samples, and external latency. Fresh full synthesis
uses 15300 LUTs and 21922 FFs (397 LUTs / 1229 FFs saved), still 53 BRAM tiles
and 65 DSPs. Full placement still fails: 2606 unplaced slices needed vs 2133
available. Neither attempt reached routing or produced a deployable image.

The next required work is further whole-receiver packing/resource reduction,
while preserving both PSS stages and bit-exact pilot evidence, followed by full
route/timing closure. Do not flash either radio or bypass that gate. After fit:
finish the matched rootfs/PPU reader and test real DMA/IIO lifecycle and recovery
on .18, then qualify paired digital replay before outdoor .17 deployment.
No PPU files or radios were changed in this integration checkpoint. All source
and source pins remain on their experimental do-not-merge branches.

### Packing and independent accounting checkpoint — 2026-09-08

The immediate priority is now the fixed-frequency paired live proof above.
The approved resource approaches preserve both PSS stages and exact pilot IQ;
neither detector removal nor a hardware purchase is part of this work.

Pilot mixer/halfband/FIR rounding now operates directly on signed values instead
of taking a magnitude and restoring its sign. All coefficients, rounding ties,
saturation flags, sample values and external latency remain unchanged. Direct
tests cover 1,209,792 integer-boundary/random cases across the three functions.
The independent upper-edge RTL/GLRT fixture still returns epoch 1622, CFO
42000.9399187 Hz and margin 0.877051434. This is synthetic validation, not live RF.

Coarse score preparation now retains one denominator/index bank for a job
instead of copying 133 unchanged bits through three stages. No-stall admission
is once per four 100 MHz clocks. The real two-XFFT numerical replay matches
all 1,341 scores and every transform intermediate; a 64-block capacity run
produces all 28,608 ordered scores at canonical 15 MS/s with FIFO high water
356/512. Stalls, flushing and protocol failures remain covered separately.

Fresh **complete receiver** measurements, not standalone-fit claims:

| Build | LUTs | FFs | Control sets at failed placement | Unplaced slices needed / available |
|---|---:|---:|---:|---:|
| Previous halfband RAM rings | 15300 | 21922 | 435 | 2606 / 2133 |
| Signed pilot rounding | 14778 | 21922 | 441 | 2632 / 2201 |
| Signed rounding, threshold 16 trial | 15271 | 21925 | 289 | 2641 / 2206 |
| Signed rounding + single score job | 14757 | 21656 | 442 | 2616 / 2206 |

Every row retains 53 BRAM tiles and 65 DSPs. Every row **fails placement**;
none reaches routing or qualifies timing/deployment. Threshold 16 reduced
control sets but increased LUTs and did not improve fit. Default remains 4;
explicit 4/8/16 trials are bounded to `paired-pilot`, not other profiles.
The command FIFO also stays in block RAM: a separate storage-only measurement
used 27 LUTs/31 FFs/2.5 BRAM tiles versus 131 LUTs/191 FFs in distributed RAM.
That comparison is not a CDC/timing gate and does not justify changing storage.

PPU remote main now contains `b5e8f6f`, the offline `PilotSnapshot` parser and
finite-prefix accounting checks. It preserves fault diagnostics, rejects
malformed or inconsistent snapshots, checks expected visit/source/received-byte
counts, and maps sample centers exactly back to the full-rate source counter.
Its 73 new tests pass; PPU's full local suite passed 1562 tests with 11 explicit
browser/hardware exclusions, plus lint and type checking. Four pre-existing
PPU changes were preserved and were **not** committed or pushed. This parser
does not open a radio, enable firmware, prove disk persistence or claim a lock.

The firmware oracle/plan/contract suite passes 277 tests. The procedural CW
capture runner `tools/starlink_pilot_capture_dwell.py` exercises the real AXI
control, DDC and AXIS exporter with a finite supported-sample limit, comparing
every exported sample against the integer oracle and feeding real RTL snapshot
words through PPU. Its kernel header is explicitly synthetic: it is not an IIO,
DMA, radio or live-GLRT test. The small runner test covers all three advertised
source-rate geometries with canonical 15 MS/s stimulus.

The full 120 ms integrated replay now passes as well:
`reports/starlink-pilot-capture-dwell-rtl-20260908.json` records exactly 300,000
supported outputs / 1,200,000 replay bytes, 90 unsupported startup results,
first/last newest canonical indexes 540 / 1800534, and original-source signal
centers 271 / 1800265. The DDC accepted 1,800,543 inputs before hardware auto-stop;
additional driven samples were not admitted. Every output matches the oracle,
all clip/fault counters are zero, and export FIFO high water is one. The real
RTL snapshot passes PPU accounting. There is still no DMA, IIO or live-lock claim.

The remaining fit gap requires a larger measured reduction, not another claim
from a smaller standalone core. Next investigate sharing the wide exact-score
arithmetic or a transform resource with demonstrated forward-plus-inverse
throughput and appropriately frozen numerical references; simply sharing the
existing 20 MS/s burst core cannot be assumed to sustain both transforms.
Retain the current working design until a candidate passes exact replay,
capacity/fault tests and fresh complete placement/timing. After fit, finish the
real IIO reader and matched image packaging, qualify .18, then deploy .17 via
serial-locked PPU network flashing for the paired live proof. No radio has been
accessed, flashed or reconfigured in this checkpoint; live GLRT/FPGA lock and
the broader hopping/rate gates are still unproved.

### Shared-transform candidate checkpoint — 2026-09-08

A concrete replacement for the second coarse transform core is now implemented
as an unselected experimental composition. `starlink_pss_iq_to_score_shared`
keeps the canonical ingress, kernel multiplication, energy cache and score path
at 100 MHz and uses a single 200 MHz XFFT through complete-block dual-clock RAM
mailboxes. Both PSS stages and the pilot branch remain required. No existing
receiver profile or default two-core implementation has been replaced yet.

The actual two-clock coarse pipeline passes exact forward/product/inverse
intermediates and all 1341 frozen numerical scores, including stalls and fault
recovery. Independent FFT reset now explicitly quarantines active acquisition
until disable/flush; reset release alone cannot silently erase lost work.
The reset/recovery check passes. A separate canonical 15 MS/s run returns all
28608 ordered scores across 64 overlap blocks, with FIFO high water 356/512
and no faults. This approximately 1.96 ms simulation is not a full dwell or a
300-second hardware soak.

Earlier measurements establish why this candidate is worth integrating, not
that it already fits the receiver: one unchanged radix-4 BFP18 FFT uses 1283 LUTs,
3119 FFs, 17 DSPs and 11 RAMB18s and has +0.168/+0.053 ns internal setup/hold
slack at a genuinely constrained 200 MHz. Each final 512x36 mailbox with 70-bit
metadata uses 71 LUTs, 185 FFs and one RAMB18; internal setup/hold slack is
+0.904/+0.104 ns for 100->200 MHz and +0.227/+0.084 ns for 200->100 MHz.
The service's actual return metadata is 75 bits and still needs integrated
measurement. Unplaced boundary timing and held-bus CDC reports remain visible
and unqualified for the receiver. The first 200 MHz mailbox write path failed
timing; removing the wide validity comparator from unpublished RAM writes fixed
it without weakening complete-block publication checks.

Twelve mailbox tests cover independent clocks, stalls, malformed blocks, and
resets during partial input, stalled output and partial reads. A real-XFFT
service-only test passes 66 jobs/33792 exact words, including an in-flight fault
after partial output buffering and both independent reset recoveries. These
results are distinct from the complete coarse-pipeline replay above. See
`hdl/library/starlink_pss_acquisition/SHARED_XFFT.md` for scope and reproduction.

The next gate is **full paired-receiver integration and placement/routing/timing**
with the real 200 MHz clock and properly scoped CDC constraints. Resolve the
experimental shared-fault identity before any deployment; no production ABI is
silently reinterpreted. The last actual complete-receiver placement still failed
as recorded above, and the candidate has no full-receiver fit claim. Then finish
the matched real IIO path on .18 and deploy .17 for fixed-frequency paired live
proof before hopping/rate expansion. No radio access, flashing, TX, new PPU
changes, live GLRT detection or FPGA live timing lock occurred in this checkpoint.
The source-pinned aggregate is `reports/starlink-shared-xfft-candidate-20260908.json`.

### Shared-transform receiver integration checkpoint — 2026-09-08

The opt-in `STARLINK_PSS_SHARED_XFFT=1` build now connects the actual single
200 MHz transform island through acquisition, phase-map wrapper, packaged IP
and complete paired-receiver block design. The selector is restricted to
`paired-pilot` at 15 MS/s; defaults preserve the two-core selection and their
rate-dependent register ABIs. Both PSS stages and the exact 2.5 MS/s pilot DMA
branch remain present. No feature was removed to obtain the resource savings.

The experimental image identifies itself as PSMA ABI **1.5**, capabilities
`0x13f`. Shared transform faults have a distinct sticky health bit 14, not the
direction-specific forward/inverse bits. Existing kernel/host readers still
reject 1.5 and must gain explicit tested support before deployment. There is
no silent reinterpretation of a deployed ABI.

The real two-clock shared phase-map replay passes 1341 exact scores and 447
exact map reads at reduced test geometry. A fault after partial-tile score
accumulation aborts that tile and publishes no partial map; its cause and
episode count are verified. The dedicated-core regression also matches all
scores/map entries. The offline oracle/plan/contract suite passes **311 tests**,
including 22 new policy/health/ABI tests, and the acquisition module and
all-rate wrapper suites pass. These tests do not establish live detection or
production dwell sensitivity.

The first full integration attempt exposed Vivado synthesis rejecting Tcl
control flow inside packaged XDC. Declarative constraints replace it. A new
pre-placement audit verifies actual 100/200 MHz endpoint clocks, exactly one
transform core with coarse/fine/pilot DMA still present, all four ownership
crossings, fault synchronization, and every bit of both 70/75-bit held metadata
buses. This gate passes in the fresh full builds. CDC reports retain the held
bus and reset-fanout diagnostics for explicit review; they are not blanket
waived and do not yet constitute full integrated CDC qualification.

The best properly constrained full build uses **13546 LUTs, 18856 FFs, 48.5
BRAM tiles and 48 DSPs**, but still fails placement: 2372 unplaced slices need
2361 remaining locations, an **11-slice shortfall**. The threshold-8 packing
experiment is worse (22 short), so threshold 4 remains the baseline. The
pre-integration complete receiver was 410 short. There is still no routed or
deployable paired image. A real-XFFT 4096-block (~122 ms source span) capacity
simulation has started and remains running at this checkpoint; do not count
it as a pass or restart it merely because this task yields.

Next: targeted full-receiver fit/timing and integrated CDC work, then explicit
ABI 1.5 kernel/host support and matched real IIO qualification on .18, followed
by serial-locked network deployment to .17 and same-observation blind live
GLRT plus FPGA PSS timing-lock proof. The remaining eight-target/120 ms/300 s
and 30/60 MS/s gates remain required. No radio, PPU, Linux, or default firmware
image was changed in this checkpoint. Source/evidence pins are recorded in
`reports/starlink-shared-xfft-integration-20260908.json`.

### Complete route and targeted control-timing checkpoint — 2026-09-08

The first complete paired receiver now places and routes, preserving both PSS
stages and pilot DMA. This is progress beyond the prior 11-slice placement
failure, but **not a deployable image**. Common service/mailbox reset release
reduced the shortfall to two slices; forcing the existing synchronous pilot
pacer memory to remain a real BRAM boundary closed placement. Synthesis uses
13396 LUTs, 18841 FFs, 49 BRAM tiles and 48 DSPs. The routed `pilot-pacer-bram`
checkpoint has all 33333 routable nets complete, no route errors, and passing
declared bus-skew constraints, but setup slack is -3.109 ns (100 MHz) and
-2.323 ns (200 MHz). Hold slack is +0.014 ns. The full build failed its timing
gate as required. The new checkpoint audit reads the saved constraints without
clock redefinitions or blanket waivers.

The worst paths identify control logic rather than a changed numerical kernel:
AXI command decode through pilot flush/fault controls into RAM write enable,
and input-framing logic through the FFT output-state gate. A registered PIL1
decode now acknowledges writes only after execution. Output-state gating is
factored by its existing lifecycle predicates without removing the global
fault checks. Tests cover command execution/acknowledgement ordering and every
reserved command bit/partial strobe; 1048576 actual-adapter control/metadata
combinations match the original output-state expression. Real-XFFT replay
retains 1341 exact scores, 33792 exact service words, reset/fault recovery, and
the same saturated service interval. That offline suite passed 361 tests.
The fresh `registered-control-v1` build has the same synthesized LUT/RAM/DSP
counts with seven additional FFs. Its completed route still fails setup:
-1.851 ns at 100 MHz and -1.727 ns at 200 MHz; hold is +0.019 ns.

The pilot BRAM change preserves all 300000 samples in the full 120 ms RTL
export and the same IQ hash as the earlier integer oracle. Blind GLRT still
acquires the exported synthetic pilot without FPGA seeds. These are separate
software/RTL fixtures, not real DMA/IIO, live GLRT, or FPGA live lock evidence.
The older 4096-block capacity simulation remains tied to HDL f85f0888, not the
current reset/control revision; a running log must never be counted as a pass.

Next remains timing closure and integrated CDC review, explicit matched ABI
1.5 kernel/host support, real paired IIO on .18, then serial-locked PPU network
deployment to .17 for same-observation blind live GLRT and qualified FPGA PSS
timing lock. Lower/upper 120 ms hopping over 300 seconds and 30/60 MS/s gates
are still required. No radio, Linux, or PPU was changed in this checkpoint.

### Active admission, mailbox metadata, and explicit ABI support — 2026-09-08

Further PIL1 factoring removes inactive ARM eligibility from active DDC/sample
admission without changing the complete sticky fault checks. 262144 actual RTL
gate comparisons and continuous capture-test assertions agree with the old
predicates. The 120 ms replay still exports all 300000 exact IQ words with SHA256
`d653ccfb1f3fb48d10c5c859b316074dc2b7e3229681294b611301043dda97a1`.

The complete `active-admission-v1` build uses 13397 LUTs, 18848 FFs, 49 BRAM
tiles and 48 DSPs, with all 33325 routable nets complete. Timing improves again
but still FAILS: 100 MHz -1.208 ns, 200 MHz -1.478 ns, hold +0.011 ns. Its own
saved-constraint audit passes all four declared bus-skew constraints and finds
no unconstrained internal endpoints. Thirteen missing RX input delays and two
missing enable/txnrx output delays still require board-I/O qualification.
They are not removed or hidden by timing waivers.

The latest 200 MHz path passes through the mailbox's full metadata comparison
into first-word metadata capture. A new `metadata-load-v1` candidate factors
the exact first-word predicate while retaining every subsequent framing check,
fault and complete-block publication rule. Ninety-six mailbox cases now cover
both actual metadata widths (70/75), three depths, four clock pairs and four
reset-release geometries. Real-XFFT numerical and service replay pass with
unchanged scores, words, reset recovery and service interval. Current 64-block
capacity and reduced-geometry phase-map replay also pass, including partial-tile
fault quarantine. The new full default implementation fails placement (Place
46-13 / 30-99: more than 5% of movable instances require spiral search), using
13429 LUTs, 18848 FFs, 49 BRAM tiles and 48 DSPs at synthesis. A separate
spread-placement trial on that saved opt DCP is running; no route is yet proved
for the latest source.
The firmware offline suite passes 411 tests.

Reusable PPU ABI support is committed and pushed to main at
`5e3d6b91c18383c74d356fa490c8a245a96328b6`. It explicitly selects shared-XFFT
ABI 1.5 only at 15 MS/s, requires a serial for opt-in connections, binds every
map chunk to the admitted context ABI, and preserves legacy defaults and TAG2
exclusions. The local suite passed 1578 tests, with one unavailable-transmitter
skip and ten browser/hardware deselections; full lint and type checks pass.
The four unrelated dirty PPU files remain untouched and uncommitted.

Matched Linux `b0c3128f995b3e9a5bebc84aa9be04b8b3524184` is pushed only to the
DNM branch. It requires 1.5/0x13f and canonical 15 MS/s geometry and rejects the
shared-service health bit 14. The ARM module compiles; extracted real kernel
contract/health functions pass 1408 register mutations and 2240 health-bit cases.
These checks do not execute kernel IRQ/DMA/IIO or qualify hardware.

Next: finish complete-receiver timing and board-I/O/CDC qualification, package
the matched image and implement the real finite pilot IIO reader. The current
kernel requires finite sample limits to be whole IIO buffers (for example,
300000 samples in twelve 25000-sample refills), and STOP must drain before DMA
abort. Qualify both products on .18 before serial-locked PPU network deployment
to .17 for blind live GLRT plus FPGA PSS timing-lock agreement. Short-dwell L/U
hopping over 300 seconds and 30/60 MS/s remain uncompleted requirements.
No radio has been accessed or flashed in this checkpoint.

The completed physical spread trial on the older `registered-control-v1` DCP
routes all 33348 nets but still fails timing: 100 MHz -1.127 ns, 200 MHz -1.289
ns, hold +0.014 ns. Clocks and exceptions were not relaxed; no bitstream was
produced by that diagnostic runner. Do not attribute its timing to newer RTL.

The older HDL f85f0888 full 4096-block coarse capacity simulation has now
completed with its actual PASS marker: 1830977 input samples, 1830912 ordered
scores, 2097152 words at each transform boundary and FIFO high water 356. This
~122 ms simulation is not the current mailbox/control revision, paired pilot
capture, hardware IIO or live GLRT/PSS lock evidence. Its completed log is
preserved with that older source identity.

Source pins, completed artifact digests, test scope and outstanding gates for
this checkpoint are in `reports/starlink-paired-control-timing-20260908.json`.
