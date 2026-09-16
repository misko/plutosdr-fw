# Feature 103: buffered adaptive scan sessions

## Status and scope

This document is the implementation, test, deployment, and verification plan for
[firmware feature request #103](https://github.com/misko/plutosdr-fw/issues/103).

The first release is deliberately bounded:

- one physical receiver, RX0;
- CI16 IQ;
- frequencies and one analog bandwidth supplied at session setup;
- fast frequency changes using preloaded AD9361 fastlock profiles;
- firmware-owned weighted channel selection;
- periodic, asynchronous host feedback;
- complete-visit admission and buffering;
- fixed-rate sessions at 10, 15, 20, and 30 MS/s;
- optional mixed-rate visits up to 30 MS/s, gated separately;
- no 60 MS/s ADC or exported-IQ mode;
- no RX1 or simultaneous dual-RX operation;
- no independent pilot/decision stream in this release.

The authorized qualification radio is RX0 on serial
`1040007c4a94000211000b009186843ef2`. The implementation request authorizes
bounded qualification and RAM-first deployment on that exact unit; persistent
installation remains gated by the acceptance and rollback checks below. At
plan review it was reachable at
`ip:192.168.1.18` and ran `v0.50-plutoplus-spf-counter-rx-v1`, metadata ABI 3,
with exact 50-buffer/200 MB DMA admission. Those observations are preflight
facts and must be re-attested immediately before deployment. Each bounded
campaign must stay within 30 minutes.

## Implementation ledger

This ledger records evidence, not completion claims. The feature remains
default-off and is not ready for deployment until every remaining item is
closed.

As of 2026-09-16:

- Linux branch `codex/feature-103`, commits `8c2927f1bdb6`, `d20eb1d417d4`, and
  `5ad4fbc32889`, adds descriptor-owner
  scan capability discovery, setup-time RX fastlock profile/frequency/CRC
  attestation, source-counter-bracketed recalls and restoration, plus an
  owner-only coherent source-counter snapshot for dwell pacing independent of
  DMA block completion. Descriptor-close remains the crash fallback. Ordinary
  sysfs LO and fastlock mutation remains excluded while the counter lease is
  owned.
- libiio branch `codex/feature-103` contains prerequisite direct-segment rearm
  commit `737d910`, scheduler/visit/radio core commit `7657d3b`, deterministic
  capacity simulation commit `556f8f0`, strict wire protocol commit `f75838e`,
  restoration receipt commit `47319ad`, session lifecycle commits `fcb2bfb`,
  `50579ae`, and `fa34857`, and production iiOD data/control integration commit
  `23e4edf`.
- PPU branch `codex/feature-103`, commits `0deb084`, `d5887e8`, and `82310bf`,
  provides byte-identical Python codecs and a strict iiOD client for capability
  discovery, setup, visit/IQ streaming, asynchronous feedback, application
  acknowledgements, terminal validation, and cleanup.
- The scheduler tests replay 256 activity masks and validate source binding,
  bounded feedback acknowledgements, fairness, and deterministic selection.
- The visit-queue tests cover 24,000 DMA-boundary combinations, shared leases,
  gaps, cancellation, age/capacity admission, and release retry. ASan/UBSan
  builds pass with warnings promoted to errors.
- The 300-second real-queue simulation with 50 one-million-sample blocks and a
  200 MB cap measures 97.2% full-session duty at 10 MS/s/240 ms, 100% planned
  delivery at 10 MS/s/120 ms, and 92.2% full-session duty at
  15 MS/s/240 ms with 55 MB/s drain. At 15 MS/s and 60 MB/s it delivers every
  planned visit and reaches 97.2% of measured payload capacity. The 20 and
  30 MS/s overload cells retain only complete visits and emit whole-visit
  skips.
- The new kernel objects cross-compile with the v0.50 ARM toolchain, the UAPI
  layout compiles for ARM EABI5, kernel `checkpatch --strict` and `diff --check`
  pass, and the native scheduler, queue, radio-UAPI, lifecycle, and capacity
  sanitizer tests pass.
- The complete provider-enabled iiOD cross-builds for ARM with the pinned v0.50
  Buildroot toolchain. The legacy provider-disabled iiOD build also passes,
  preserving default-off behavior. The production path uses a source-time
  scheduler thread, scatter/gather visit sends, independent `SCANFEEDBACK` and
  `SCANACK` commands, explicit terminal records, and restoration before final
  transport drain.
- A RAM-only FIT/DFU candidate was assembled from the unchanged qualified FPGA
  and Rev.C DTB, kernel `5ad4fbc32889`, iiOD/libiio `23e4edf`, and the v0.50
  root filesystem. RC1 (`559bc93c…69cbf5`) reached DFU download but did not
  boot because its FIT component hashes used SHA-256 while the deployed U-Boot
  has `CONFIG_SHA256` disabled. Receipt
  `97ab6f9ab7584e7daa9bec90139513b5` records the fail-closed unknown return.
  RC1 is retained immutably and prohibited from persistence.
- Corrected RC2 uses the same payloads and the qualified image's MD5 FIT hash
  algorithm. Its exact identities are DFU
  `fbc591ecbbeac83f8b24fc169fd675a834aa5e00aa5b779e79c7c097d9c61c81`
  and FIT
  `6cf16e9884fc46a362f3fcc9b61ea752c4cac89e69a8b12b3da2dbbe9b602c0e`.
  PPU commit `a58b8f1` admits RC1/RC2 only through immutable RAM profiles and
  tests that no persistent profile accepts either artifact.
- PPU commits `9959935`, `939df83`, and `f0c8f33` add strict whole-stream
  setup/terminal binding, fail-closed truncated-socket tests, exact
  source-counter acceptance metrics, and a scanner adapter whose shadow and
  adaptive modes run the same detector. Shadow mode never transmits feedback;
  adaptive mode sends periodic source-bound active/quiet observations, while
  `UNKNOWN` remains distinct from quiet.
- PPU commits `c937a09`, `224ae47`, `a2ed81a`, and `3a4eaf0` add the bounded
  exact-radio lifecycle: RX0-only factor-one setup through 30 MS/s, independent
  fixed bandwidth, TX mute, fastlock compilation/double-read/CRC binding,
  prepare-failure restoration, campaign-final restoration, application-ACK
  correlation, and a bounded retry for the narrow race between delivery and
  provider completion. The focused PPU suite now passes 122 tests with Ruff
  and strict mypy clean; the ASan/UBSan C policy/session/queue suite also
  remains green.
- PPU commit `731e29e` adds a deterministic hash-bound CI16 energy detector
  with per-visit dBFS evidence for shadow and adaptive runs. A direct newc
  archive parse proves the candidate's final `/usr/sbin/iiod` and
  `/usr/lib/libiio.so.0.25` payload hashes are `72d4aafc…dd695` and
  `ce67ffdc…d5780f`; the base symlinks resolve `libiio.so -> libiio.so.0 ->
  libiio.so.0.25`, and every ARM hard-float runtime dependency is present.

Still required before deployment: physical power-cycle recovery of the exact
qualification radio to its unchanged v0.50 QSPI image, scanner shadow-mode
integration with the production scanner detector, live mid-session socket
failure and RF signal-fidelity tests, RC2 exact-radio RAM boot, and the bounded
hardware campaigns and rollback verification below. The other attached Pluto
was not touched. Persistent installation remains prohibited until those gates
pass.

## Desired behavior

The host defines the legal scan at setup. Firmware then owns all dwell-boundary
decisions and continues scanning if the host is delayed or disconnected.

```text
setup: frequencies + fixed bandwidth + dwell/rate pattern + baseline weights
                                      |
                                      v
firmware selects target -> fastlock recall -> settle -> complete valid dwell
                                      |
                                      v
host receives complete visit(s) -> analyzes IQ -> periodically sends feedback
                                      |
                                      v
firmware validates feedback -> updates weights -> applies at a later boundary
```

The host reports what it observed. It does not directly command the next hop.
An active observation increases that channel's probability of being selected;
quiet observations decay its boost toward baseline. Minimum exploration and
maximum-revisit constraints prevent starvation.

Frequency selection and IQ sample-rate selection are separate decisions. The
session has one analog bandwidth. Hopping changes only the LO using the
setup-time fastlock profiles; it must not rewrite bandwidth or perform ordinary
LO configuration in the acquisition loop.

## Architectural principles

1. **Negotiate before allocating.** Reject unsupported topology, rates,
   bandwidth, schedules, queue bounds, or feedback guarantees before touching
   the radio.
2. **Admit complete visits, not arbitrary frames.** An admitted visit is
   delivered intact or explicitly invalidated by an unexpected acquisition
   fault. Congestion produces an intentional whole-visit skip.
3. **Keep control independent of IQ draining.** Feedback must not wait for a
   finite IQ segment to drain or rearm.
4. **Bound both bytes and age.** A large but stale queue is not useful to an
   adaptive scanner.
5. **Preserve exact source time.** Retunes, settling, valid IQ, intentional
   skips, and unexpected gaps remain distinguishable intervals.
6. **Acceptance is not application.** Firmware reports both whether feedback
   entered the mailbox and the first dwell on which it influenced selection.
7. **Fail closed.** Unknown versions, mixed runtime pins, wrong sessions, and
   unschedulable requests are rejected rather than coerced.

## Versioned session contract

Introduce a new major session version. Existing HOPR/HOPS/HOPT versions and
metadata ABI 3 semantics remain unchanged.

### Capability discovery

The provider advertises at least:

- supported request, visit, feedback, acknowledgement, and terminal versions;
- RX masks and simultaneous-RX restrictions;
- fastlock/profile capacity;
- supported physical and exported rates;
- dwell bounds and granularity;
- fixed-bandwidth requirement;
- DMA and optional DDR capacity;
- output formats;
- queue byte and queue-age limits;
- feedback mailbox capacity and maximum accepted age;
- guaranteed receipt-to-application bound for admitted configurations;
- supported overload and fallback policies;
- source-counter clock and rate-mapping model.

### Setup request

The request contains:

- session ID, policy generation, request version, and request digest;
- RX0 selection and CI16 format;
- the single session analog bandwidth;
- total source-time duration;
- valid dwell duration, separate guard and filter-settling bounds;
- channel IDs, RF frequencies, optional digital offsets, gain, and fastlock
  profile data or validated profile identities;
- baseline channel weights;
- minimum exploration and maximum revisit settings;
- allowed dwell-rate sequence or a deterministic repeated pattern;
- maximum dwell extension, if enabled;
- queue byte, queue age, and overload behavior;
- feedback maximum age and application-delay request;
- deterministic scheduler seed for replayable qualification.

Admission verifies every frequency/profile and reads back its identity before
arming. The provider computes the worst-case memory and byte-rate budget and
returns the exact admitted contract. It never silently reduces a rate, changes
bandwidth, changes RX, or alters a policy bound.

### Visit and execution records

Every planned dwell reaches one explicit outcome:

- `DELIVERED`: complete valid IQ is present;
- `SKIPPED_CAPACITY`: no complete buffer reservation was available;
- `SKIPPED_AGE`: admitting it would violate the queue-age bound;
- `SKIPPED_POLICY`: a pre-authorized lower-rate or deferral rule was used;
- `INVALID_GAP`: an unexpected DMA/source gap intersected an admitted visit;
- `CANCELLED` or `FAILED`: terminal lifecycle interrupted the visit.

The record includes session/generation, visit and event sequence, channel,
actual frequency, fixed bandwidth, RX, physical/output rate, source-counter
intervals, valid/guard/settling intervals, filter identity, selection reason,
effective weight, feedback basis, and exact skip/failure reason.

Hop and tuning history is emitted even for visits with no IQ. A terminal record
closes the final visit and accounts for every source interval through cleanup.

## Firmware-owned weighted scheduler

The scheduler runs only at dwell boundaries. It combines soft weights with hard
fairness constraints.

Conceptually:

```text
effective_weight[channel] =
    baseline_weight
    * bounded_activity_boost
    * freshness_decay
    * revisit_urgency
```

Eligible channels are selected by a deterministic seeded weighted lottery.
Hard constraints override probability in this order:

1. ownership, TX safety, counter integrity, and memory safety;
2. session duration and complete-visit admission;
3. maximum revisit and minimum exploration;
4. queue-age and feedback-age limits;
5. adaptive weights and optional dwell extensions.

Initial policy defaults should remain configuration, not wire constants. A
reasonable qualification profile is:

- equal baseline weights;
- active boost up to 3x, with an explicit maximum;
- quiet results decay the boost toward baseline rather than dividing abruptly;
- unknown or unhealthy results do not count as quiet;
- activity boosts decay with source time unless reconfirmed;
- a three-second maximum revisit;
- a nonzero exploration floor for every channel;
- a one-second maximum feedback age at receipt;
- a one-second maximum receipt-to-application delay for an admitted session.

No channel may reach zero probability. An active channel must not monopolize the
schedule. If feedback stops or becomes unhealthy, weights decay to the baseline
distribution and scanning continues.

## Asynchronous host feedback

Feedback may be submitted individually or in periodic batches. A record binds
to the evidence that produced it:

- session ID and policy generation;
- monotonically increasing feedback sequence;
- source visit and event sequence;
- channel ID and exact valid source-counter interval;
- active, quiet, or unknown outcome;
- optional confidence/score or requested bounded adjustment;
- detector configuration digest;
- observation and host-send times where available.

The provider validates ownership, generation, channel, counters, age, and
configuration before changing scheduler state. A newer update may supersede an
older unapplied update for the same channel. Out-of-order updates are allowed
inside a negotiated bounded window; the host is not required to manufacture a
result for every missing visit.

There are two observable responses:

1. A receipt: `accepted`, `rejected`, `duplicate`, `expired`, `superseded`,
   `wrong_session`, or `mailbox_full`.
2. An application event: feedback sequence, old/new effective weight, and the
   first visit and source counter whose selection considered the update.

The mailbox is bounded by count, bytes, and age. Overflow rejects the new item
without corrupting capture ownership. Feedback never relabels IQ already
acquired.

## Complete-visit buffering and transport

The current direct-async mechanism is a frame FIFO. The new provider adds a
visit layer over continuously acquired DMA blocks.

Before starting a valid interval, it reserves the worst-case number of leases
needed through the visit's end and its closing boundary. It admits the visit
only when:

- enough leases and descriptor slots are free;
- projected buffered bytes stay within the negotiated cap;
- projected oldest-visit age stays within the negotiated cap;
- the requested rate-pattern budget remains schedulable.

Completed visits should be represented as scatter/gather slices over owned DMA
blocks. Boundary blocks may be reference-counted by adjacent visits. This avoids
making a mandatory ARM-side copy at the full source rate. A lease is released
only after all visits referencing it are sent or explicitly discarded.

The IQ data command remains active for the session. It does not use short
finite segments whose drain/rearm boundary controls when feedback can be sent.
Feedback uses the session-owned control connection/mailbox concurrently.

At 120 ms, one RX CI16 visit contains:

| Output rate | IQ bytes | Drain time at 60 MB/s |
| ---: | ---: | ---: |
| 10 MS/s | 4.8 MB | 80 ms |
| 15 MS/s | 7.2 MB | 120 ms |
| 20 MS/s | 9.6 MB | 160 ms |
| 30 MS/s | 14.4 MB | 240 ms |

Buffering smooths bursts; it cannot sustain a permanent input/output deficit.
At 20 MS/s the ideal 60 MB/s transport ceiling is 75% before protocol costs.
Admission must intentionally choose which whole visits survive.

## Rate sequences and Ethernet utilization

The host may request a deterministic repeated dwell-rate sequence, for example:

```text
[10, 15, 15, 20, 15, 15] MS/s
```

The provider calculates predicted payload using valid dwell, transition time,
metadata, and terminal drain. A short HOLD preflight measures current transport
goodput. Qualification sequences target percentages of that measured value,
not an assumed Ethernet number:

- 70%: control;
- 85%: normal sustained load;
- 90-95%: intended operating region;
- 100%: capacity boundary;
- 105-115%: deliberate overload.

The rate-sequence compiler returns the exact repeated sequence, expected bytes,
expected utilization, rounding error, and whether it can meet all revisit and
exploration constraints. Runtime admission uses observed drain rate and queue
age, so clustered 20/30 MS/s visits can be deferred even if the long-term
average is feasible.

### Mixed-rate implementation gate

Fixed-rate 10/15/20/30 MS/s sessions are mandatory. Mixed-rate visits are a
separate promotion gate.

No implementation in this release may use a 60 MS/s ADC clock. One possible
mixed-rate design is a fixed 30 MS/s source clock with:

- 30 to 30 MS/s bypass;
- 30 to 20 MS/s rational 2/3 resampling;
- 30 to 10 MS/s decimation by 3.

The rational path must meet FPGA timing, resource, passband, stopband, phase,
group-delay, reset, and overflow gates. All output samples map to the unchanged
30 MHz source-counter domain. If this path is not qualified, the release still
ships complete-visit fixed-rate sessions and does not advertise mixed-rate
execution.

Fifteen MS/s can be supported as a fixed physical-rate session. It need not be
part of the first fixed-30 mixed sequence unless an independently qualified
30-to-15 path is included.

## Host and application ownership

The metadata/provider and iiOD layers own:

- version and capability negotiation;
- exclusive radio/session ownership;
- fastlock execution and restoration;
- scheduler state and feedback mailbox;
- DMA lease and complete-visit ownership;
- exact source-time, skip, and terminal accounting.

Pluto Plus Utils owns:

- strict C/Python wire codecs;
- exact serial/runtime/capability admission;
- session lifecycle and restoration checks;
- visit decoding and source-counter reconstruction;
- feedback submission and receipt/application correlation.

The scanner owns:

- IQ analysis and detector configuration;
- conversion of scientific results to active/quiet/unknown observations;
- persistence of IQ, execution history, and feedback latency;
- policy configuration exposed to operations.

## Deterministic verification before RF

### Protocol and scheduler

- Golden C/Python byte vectors for capabilities, setup, visits, skips,
  feedback, receipts, applications, cancellation, and terminal records.
- Reject unknown versions, nonzero reserved bytes, unsupported rates, changed
  bandwidth, invalid profiles, wrong RX, and unschedulable bounds.
- Model-based scheduler tests with a deterministic source clock and seed.
- With no feedback, visit shares converge to baseline weights.
- Repeated active feedback materially raises a channel's share.
- Quiet feedback decays that share toward baseline.
- Unknown/missing feedback does not become quiet evidence.
- Exploration and maximum-revisit constraints hold under every activity mask.
- Duplicate, stale, out-of-order, wrong-session, and superseded feedback has
  the specified observable outcome.
- Batched updates reach the same scheduler state as equivalent accepted
  individual updates.
- Identical requests, counters, and feedback produce identical schedules.

### Queue and capacity simulation

Use the real 50-buffer/200 MB geometry with configurable 55-65 MB/s drain,
10/15/20/30 MS/s visits, 120/150/240 ms dwells, measured transition
distributions, network jitter, socket stalls, and bursty feedback.

For 70, 85, 90, 95, 100, 105, and 115% target loads, assert:

- every admitted visit is intact;
- no unadmitted visit is reported as captured;
- skips and unexpected gaps have exact, nonoverlapping intervals;
- queue bytes and oldest age remain bounded;
- predicted and actual byte rates agree within a frozen tolerance;
- sustainable cases deliver every planned valid interval;
- overloaded cases shed complete visits according to policy;
- the executed rate mix remains within tolerance of the requested mix;
- exploration and revisit bounds survive pressure;
- initial and terminal buffered bytes are included in throughput accounting.

Reproduce the current scattered-loss behavior with a frame FIFO, then show that
visit admission converts it into intact visits plus explicit skips. Compare the
result with a calculated whole-visit bound; do not hard-code the historical 19%
result as a universal baseline.

### Ownership and failure injection

- ASan/UBSan and TSan runs where supported.
- Failure at every reserve, acquire, fill, close, enqueue, send, acknowledge,
  release, cancel, restore, and terminal transition.
- Slow consumers, control disconnect, IQ disconnect, daemon death, host death,
  cancellation with queued visits, and reconnect attempts.
- No overwrite, double release, use-after-release, deadlock, cross-session
  mutation, unbounded allocation, or poisoned subsequent session.
- Exact cleanup and settings restoration after every failure.

### Signal and rate fidelity

- Inject tones and pilot-like signals across the passband plus out-of-band
  interferers.
- Compare exported IQ with an independent offline reference.
- Freeze amplitude, passband ripple, stopband rejection, phase, CFO, timing,
  alias, and overflow tolerances before hardware promotion.
- Test rate changes only at visit boundaries and exclude all filter-reset and
  settling samples from valid IQ.
- Verify exact output-to-source mapping through every supported transition.

## Hardware qualification

All runs use the authorized serial, RX0, fixed bandwidth, pinned runtime, and
identical channel/dwell geometry unless the named factor is under test.
Preflight records serial, firmware/FIT, kernel, iiOD, capabilities, TX-safe
state, radio settings, active owners, and available storage. Cleanup verifies
the exact restored state and a fresh ordinary capture.

### Campaign A: transport and complete visits

1. Ten-to-thirty-second smoke cells at 10, 15, 20, and 30 MS/s.
2. A measured-goodput HOLD control.
3. Four 300-second cells changing one factor at a time: current baseline,
   alternate overrun policy, long-lived transport, complete-visit admission.
4. Report both capture-window and end-to-end time including terminal drain.

### Campaign B: weighted feedback

1. Baseline weights with no feedback.
2. Shadow feedback: compute proposals but execute the baseline schedule.
3. Active feedback with controlled active/quiet channel scripts.
4. Delayed, batched, stale, duplicate, and disconnected-host cases.
5. Verify selection shares, exploration, revisit bounds, fallback, receipts,
   and first-applied events.

### Campaign C: capacity staircase

Use 240 ms visits for the principal efficiency gate and run deterministic
sequences targeting 70, 85, 90, 95, 100, 105, and 115% of measured goodput.
Repeat the 90-105% boundary cells enough to establish reproducibility. Include
a clustered 20/30 MS/s pattern followed by compensating 10 MS/s visits.

### Campaign D: mixed-rate promotion

Run only after fixed-rate acceptance and FPGA/offline fidelity gates. Start
with muted or injected-tone short visits, then sustainable low-rate sessions
with isolated 20/30 MS/s bursts. Mixed rate remains unadvertised unless all
counter, filter, timing, queue, and restoration gates pass.

## Metrics

Keep these quantities distinct:

```text
planned-valid delivery =
    union(delivered complete valid intervals) / union(planned valid intervals)

full-session retained duty =
    union(delivered complete valid intervals) / full source-time interval
```

The second denominator includes transitions and intentional skips. Do not
remove skipped time, add overlapping loss categories, or double-count RXs.

Every run reports:

- raw source coverage and payload MB/s;
- complete-visit duty and planned-valid delivery;
- planned, admitted, delivered, skipped, invalid, and cancelled visit counts;
- per-channel/rate time, selection share, and revisit distribution;
- transition, filter-settling, intentional-skip, and unexpected-gap intervals;
- gap-length and contiguous-run distributions;
- queue byte/visit high-water, oldest age, and initial/final occupancy;
- DMA acquisition, metadata, socket, feedback, and terminal-drain timing;
- CPU and memory use;
- observation-to-receipt and receipt-to-application p50/p95/max;
- accepted, applied, rejected, expired, duplicate, and superseded feedback.

## Acceptance gates

### Correctness

- Every nominally admitted visit is delivered intact.
- Every loss or skip is explicit and source-bound.
- No guard, transition, or filter-settling samples appear in valid IQ.
- No channel/rate labels cross a visit boundary.
- Queue memory and age remain inside the negotiated bounds.
- Feedback application meets the negotiated maximum delay.
- No fairness, ownership, restoration, or subsequent-session failure.
- Unsupported configurations fail during setup without changing the radio.

### Duty and utilization

The measured transition fraction in the motivating configuration was about
5.48%. With 120 ms valid dwells, even lossless capture therefore has an overall
duty ceiling near 94.5%. Keep transition-limited duty separate from transport
delivery.

- 10 MS/s, 240 ms dwell: greater than 95% full-session retained duty.
- 10 MS/s, 120 ms dwell: greater than 99% planned-valid delivery; do not require
  impossible greater-than-95% full-session duty unless measured transition
  overhead falls below 5%.
- 15 MS/s: at least 90% full-session retained duty with the declared dwell.
- 20 MS/s: reproducible material improvement over the current complete-visit
  baseline; approximately 70% is the provisional stretch target, to be frozen
  after simulation and measured overhead review.
- Near-capacity sequence: at least 95% of measured sustainable payload goodput
  without violating queue-age or revisit bounds.
- Deliberate overload: 100% integrity among admitted visits and 100% explicit
  accounting of skipped visits.

Numerical tolerances and statistical confidence must be frozen before the
candidate hardware campaign, not selected after observing its results.

## Delivery and deployment sequence

1. Start from a clean worktree and the immutable v0.50 source graph; do not
   build from a mixed submodule checkout.
2. Integrate the direct-async lifecycle recovery and peer-limit negotiation
   prerequisites tracked by issues #101 and #102.
3. Land codecs, capability negotiation, scheduler model, queue simulator, and
   golden tests without enabling the provider.
4. Add fixed-rate complete-visit transport and the independent feedback
   mailbox behind a default-off build option.
5. Integrate PPU and scanner shadow mode.
6. Stage matched iiOD/libiio binaries from temporary storage on a separate
   port against the qualified v0.50 kernel/FPGA where possible.
7. Run authorized fixed-rate and shadow campaigns. Keep stock iiOD available
   for immediate rollback.
8. If kernel or FPGA changes are required, build a hash-pinned source graph and
   RAM-boot the exact candidate before any persistent write.
9. Qualify active weighting and the capacity staircase.
10. Qualify and advertise mixed-rate execution only as the separate promotion
    gate.
11. Publish matched firmware, iiOD/libiio, PPU, and scanner identities with
    immutable manifests and evidence.
12. Permit persistent installation only after offline gates, RAM boot, bounded
    hardware campaigns, exact FIT attestation, reboot, restoration, and scanner
    resumption all pass.

Retain v0.50 and its known FIT as the rollback target through post-deployment
verification. This feature must never imply that metadata ABI 3 alone makes an
arbitrary host/provider combination compatible.

## Explicitly deferred work

- all 60 MS/s ADC and output modes;
- per-visit AD9361 clock reconfiguration;
- RX1 and dual-RX scheduling;
- an independent continuous decision stream;
- packed/lossy IQ formats;
- arbitrary host-directed next-hop commands;
- fleet-wide persistent promotion.

These require separate design and qualification and must not delay the useful
first outcome: high-duty, complete, source-attested visits with fast frequency
hopping and bounded adaptive feedback through 30 MS/s.
