# Sealed-bank first slice: offline contract and evidence

This is an additive, **unintegrated fast-clock prototype**, not a receiver or
timing result. `starlink_pss_epoch_sealed_bank.v` defaults to the byte-unchanged
original explicit-commit mailbox. No existing caller, runtime baseline62da,
arithmetic, generated FFT, numerical vector or old155-bit observer was changed.
The original proposal is retained at FW265a309a1; the reviewed revisions below
supersede its immediate-private-fault suggestion and80-bit target.

## Three distinct events

| Event | Authority and timing |
| --- | --- |
| `private_take` | VALID, pending-new-reference marker and registered owned capacity. Exactly512 writes, including one final write. Not a commit. |
| `checked_seal` | Last token's ordinal/TLAST, lease and all75 metadata bits have drained25 three-bit equality leaves and5 reduction groups. Final take at n permits seal at n+2. This proves local consistency, not independently expected identity. |
| `publish` | Sealed immutable payload, independently matching certificate, empty check pipe, no sticky fault, and direct current publication veto clean. Earliest n+3; later certificates delay publication. Exactly one ownership-toggle event. |

The75-bit descriptor includes every bit72–74 in the25th leaf. A uniformly wrong
descriptor may seal locally; the separate expected certificate must reject it.
A first-token-only wrong descriptor is caught when the next unchanged token is
checked. The first offending **offered** lease and9-bit position are retained.
Private framing/metadata/lease causes become sticky two edges after that take,
not on the old mailbox's current-framing edge. `input_framing_fault_now` in the
opt-in branch denotes this delayed check. No old public counter/ABI timing
equivalence is claimed; integration needs an explicit adapter and requalification.

There is no parallel full75-bit token comparator feeding the publication fence.
The wide certificate comparison qualifies its private receipt only. Once sealed,
input capacity is closed and the pipe must be empty; once certificate-seen, no
new current-lease certificate can be consumed. Direct publication/read vetoes
remain raw `live_faults`, genuinely new closed-current-lease input/certificate
offers, unknown control simulation conditions, and registered sticky reasons.
This structurally separates the old cross-module private-check path; its physical
effect and remaining fanout are **unmeasured**.

## Issuer, lease, reset and adapter obligations

- `input_offer_new` and `certificate_offer_new` identify an outstanding reference,
  not a VALID rising edge. They stay asserted through backpressure and fall only
  after the corresponding take. A legacy held final can keep VALID high with its
  already-consumed marker low; this produces no second RAM write. New raw core
  output must independently assert the orphan live cause even when READY is low.
- A certificate joins the snapshotted N descriptor/lease. Legal N+1 source or
  certificate metadata movement cannot replace it. A real N+1 source fault still
  quarantines the common epoch when its CDC cause becomes visible.
- Release is an issuer's **old-lease reference-drained attestation**, accepted only
  after actual512th output acceptance, synchronized ACK and local pipe drain.
  Exact-next-lease offers may remain queued throughout old release, avoiding the
  circular wait caused by requiring all VALID signals low.
- Two lease bits do **not** reject arbitrary stale identical certificates after
  wrap/reset. Before reuse, issuer consumption must be acknowledged and all old
  queued/held/in-flight references retired. Merely observing VALID low is not
  enough; tagging unlabelled raw FFT status with today's lease proves nothing.
- Either raw reset asynchronously invalidates ownership/publication. Two-clock
  release does not rearm. Rearm requires core held reset, three independently
  flushed peer queues, no offers/release pending, and drained local reader/check
  state. It must not clear lease to0 and accept a surviving stale0 certificate.

The intended in-island guarantees have concrete owners: the input/return pipeline
controller acknowledges its producer queue flush/last consumed token; the
transform-status/result-guard controller acknowledges status consumption and
pipeline purge while the core is held reset; the bank reader owns final read/ACK
and consumer flush. These adapters are **not RTL-implemented here**. The finite
issuer model retains consumed references until separate ACK, allows one old and
one future reference per actor, and refuses release/rearm with outstanding old
references. The SV bench uses independent finite actor flags and staggered flush
delays, actual takes/reads and explicit release; it does not generate attestation
from the DUT's desire to advance. A model counterexample explicitly shows that an
untracked stale copy surviving an asserted drain can match again after four
lifetimes or reset. This is a conditional interface contract, not a full ABA proof.

Missing certificate has no local deadline register. A bounded independent test
issuer supplies a live timeout after8192 clocks. Intended integration must retain
the existing result guard's `WATCHDOG_CYCLES=8192` age/deadline cause; indefinite
status waiting without that issuer is outside the bounded liveness guarantee.

Reasons0/1/3 are delayed framing/lease/metadata;2 certificate;4 release;5 new
closed input;6 duplicate certificate;7 unknown-interface simulation condition;
8–15 are independent live causes. All simultaneous causes remain sticky until
common reset. Invalid bubbles can contain X; unknown valid/offer controls at a
would-be publication edge quarantine. Silicon is not claimed to detect X/Z.
The pre-first-reset `FAULT 1 0 xxxx` trace is explicitly classified as the
pre-NBA startup register observation, and accepted nowhere after RESET/JOB.

## Honest storage and latency budget

The implemented option declares **317 logical register bits**:222 reused bank
storage/reader/cursor/toggle bits and95 control/check bits. The95 comprises2 reset
release,7 ownership/lease/seal/certificate,16 reasons,30 equality evidence,
6 pipeline valid/last/error,22 delayed lease/position and12 first-fault-token bits.
It exceeds the original80 target by15. There is one18432-bit512×36 RAM, no second
payload RAM and no DSP. These are declaration counts, not inferred/mapped area.

The exact old mailbox also owns8 reset-synchronizer bits and1 input-fault bit in
addition to those222: the raw declaration comparison is317 versus231, net+86,
not+95. Synthesis could optimize same-clock logic differently. External issuer,
reset coordination, CDC and legacy held-final adapters require additional state;
the SV model's3 ownership flags and14-bit timeout counter are test actors, not
an area estimate for those missing adapters. Their implementation must enter a
later total budget before integration is accepted.

One slice demonstrates512 contiguous private takes, a two-edge check drain, and
publication no earlier than n+3; its reader retains the mailbox-style registered
read and ACK stages. This does not establish a transform-pair service interval.
The previous actual core observed4549 clocks/pair at175, with5215 available for
447 results/29.8us. The proposed maximum+24 clocks/pair remains a planning
allocation, not an achieved bound. Outer CDC/input/egress banks, FFT/config/reset,
status deadlines, scoring/energy expiry, bounded stalls and issuer overhead still
need complete source-specific measurement. No robust150MHz or timing claim follows.

## Offline execution and limits

Final original handle92094 returned0: **526 tests passed in8.14s**. Ruff passed.
Raw logs/XML, frozen inputs and all mutant failures remain under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/epoch-sealed-tests-v6.92Nhpa0l`.
The exact suite is one file, `tests/starlink_oracle/test_epoch_sealed_bank.py`:

```sh
env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest \
  tests/starlink_oracle/test_epoch_sealed_bank.py -q --tb=short \
  --basetemp /ABS/NEW_UNIQUE/cases --junitxml /ABS/NEW_UNIQUE/results.xml
```

Retained attempts, never overwritten or relabelled:

| Attempt | Original outcome |
| --- | --- |
| manual smoke v1 `jjp4L9z7` | Icarus compile EXIT2: indefinite-width concatenation in bench metadata helper; subsequent vvp EXIT255 had no executable. No RTL execution. |
| ownership v1 `X3u1HOqu` |10 passed,363 deselected; an early subset only. |
| full v2 `4AMJtgtA`, handle51640 |453 passed,3 mutant-survival failures: wrong live-fault phase, raw cause never cleared, and insufficient unauthorized-rearm observation. Tests corrected, not production RTL. |
| full v3 `I3lszlLF`, handle85765 |476 passed6.74s; before the final reviewer-requested receipt/stall/join additions. |
| full v4 `ANpePoWN`, handle66455 |454 failed,42 passed,23 fixture errors14.56s. The strengthened parser attempted hexadecimal conversion of documented pre-reset `xxxx`; original HDL terminals retained. Read-only diagnostic also identified exact simultaneous unknown-marker/closed-offer masks, now explicitly required. |
| full v5 `LvArdYld`, handle7110 |525 passed,1 mutation-selection failure8.30s: deletion removed optional startup FAULT, not the owned nonzero cause. The parser correctly continued accepting the remaining complete negative trace. |
| full v6 `92Nhpa0l`, handle92094 |526 passed8.14s. The deletion now targets the actual owned cause; all15 executed RTL mutants reject. |

The unintegrated RTL SHA is
`d9c2382f9087ccd2088fa5a5d3fed5c6fe885359d6d4c367ed2ea81ce099d9f6`;
old mailbox remains
`e85122eb6689ff49b31aa5a0c200e2666786629055b4f45856fe79fb829dbb55`.
Portable inventories bind the remaining bench/model/test bytes and original logs.
Source pins: FW`f8754e23afc136870d1dd68228bdecb197a6e6c7`,
HDL`2c2460ad55981ed0833eeadfef60463f1d1bca10`.
The [portable archive](../reports/experiments/20260910-epoch-sealed-offline-v1.tgz)
and [complete member receipt](../reports/experiments/20260910-epoch-sealed-offline-v1.json)
preserve5705 unique regular files,9,372,940 compressed bytes, SHA
`a0742fb322eb2382088b49aa273f5e9068679f30cb944ebbbb9a3d6fafd55fef`.
Every member hash and all final compile-source inventories were checked after
creation, and the live six-source cohort still matches its pre-run snapshots.
The first archive script's classification assertion is retained: the RAM-corruption
mutant legitimately reaches vvp EXIT0 and is killed by the independent numerical
oracle, not an HDL fatal. The final receipt records the actual rejection layer
and reason for each15 mutant; it does not rewrite any simulation outcome.
The independent event model checks full512×36 payload/order and75-bit descriptor,
actual offered lease, seal/publication/release epoch/lease/cycle, and delayed
fault-token tags. Every profile requires its exact finite stimulus/event/cause
inventory: a negative terminal alone, truncated cause, duplicate/missing terminal
or late failure is rejected. Public stalled VALID and tuple stability are checked
unless an actual reset/current veto/sticky quarantine lawfully retracts the offer.

Coverage includes eight drained lease lifetimes, held final200 clocks without
rewrite, every75-bit first-only/interior/final and certificate corruption, bad
ordinal/lease/TLAST, certificate-before/with/after seal, n through n+3 and late
current causes, partial-prefix/final-read/ACK quarantine, future queued offers,
withheld/mistagged release, missing-status timeout, one-sided and off-edge reset
at the joins/read/ACK, and explicit fresh-epoch replay. Default and explicit0
compare against the original mailbox across1024 outputs and its held-final rules.
Executed mutants cover premature seal/publication, omitted current veto, closed
offer/duplicate certificate, omitted25th leaf, future-offer deadlock, wrong leases,
sticky loss, unauthorized rearm, RAM corruption, fault-token identity and a
one-cycle healthy stalled-VALID withdrawal. No unexecuted mutant is counted.

This proves only the tested standalone binary/four-state simulation contract and
independent transaction checks. No vendor FFT, synthesis, route, physical CDC,
scorer RTL, continuous receiver or RF evidence was produced. Continuous canonical15
from source15/30/60, original-rate sparse native fine search,2.5MS/s pilot, .18
before .17, and eventual eight targets/120ms dwells/300s remain the full objective.
