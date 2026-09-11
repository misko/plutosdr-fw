# Replay quiet-phase contract — DO NOT MERGE

Branch (FW/HDL): `codex/starlink-rx-only-do-not-merge-replay-quiet-contract`.
Parent FW `be129242939799aa667dedd6267b1416b9599be2`, HDL
`36ae980a090203cd95dce952b0cfb75758591986`.

## Purpose and scope

The parent's worst routed path runs from actual FFT status payload through
shared current-fault logic to output publication. This diagnostic adds shadow
logic and tests to determine whether publication can use a phase-specific
predicate. **All 22 compiled runtime modules are byte-identical to the parent.**
No live authorization, arithmetic, buffering, clock, reset, timing constraint,
radio or PPU/main change. This is not a new physical improvement or deployment.

## Phase-specific reduction

The shadow requires inverse ACK_DRAIN, inverse raw routing, no preflight, and
both producer guards inactive. It observes this premise whenever output replay
is valid. It compares a proposed publication decision with the original equation
and compares the reduced current-fault predicate with the original current fault.

For an inactive producer, its offered local fault summary reduces exactly to:

```
mailbox fault OR offered input beat OR offered input complete
OR frame event OR status valid OR output valid
```

Reservation, return-slot and watchdog faults are false when inactive. Any new
status/output/frame/input event is then an orphan regardless of its payload.
This removes the need to interpret status exponent/header bits at this boundary;
it does not allow a late event or ignore an error.

The shadow keeps `offered_external_fault_now`, result faults, output-bank fault
and framing checks, and preparation faults. These preserve current input,
vendor, product, ownership and retained-output checks. Only the inactive guard
summary is reduced. This is scoped to the tested offered/contextual-summary
configuration; it is not a replacement for active-job validation or legacy
configurations. A first matching status during active computation can be legal.

## Test layers and retained diagnostic

- Thirteen new component/source tests include eight 4112-case guard algebra
  runs. They exercise all 4096 four-state offered/event/mailbox combinations,
  varied stale payloads and explicit X/Z payload cases. Three omitted-event/
  mailbox variants and one unsafe active-producer generalization are rejected.
- All 22 runtime modules are compared byte-for-byte with the pinned parent.
  An exact inverse removes only additive bench sections. The copied original
  publication equation is checked against the actual unchanged runtime source.
- The full regression passes **767 tests in 92.84 s** before the shadow monitor
  correction. After correction, 59 focused tests pass; this is not a second
  complete 767-test run. Runtime never changed.
- Initial main actual FFT stops at the first existing publication-pause test:
  that test intentionally forces `output_replay_accept=0`, while the shadow
  predicted the unforced equation. This is a harness comparison error, not a
  producer-ownership counterexample. The failed V1 outcome/log is retained.
  Initial auxiliary succeeds, including all ten new late-event cases.
- Corrected V2 compares the original unforced equation throughout the pause,
  and independently checks that the actual signal equals the forced-off value.
  No paused cycle or inherited test is skipped. Paused-cycle coverage is now
  explicit. Both source snapshots have byte-identical runtime modules.
- Auxiliary tests sweep every status byte with status-valid low and high:
  512 combinational checks within a replay half-cycle. Invalid status payload
  must not block publication; late valid status must always block it. Ten
  clocked cases inject eight status payload patterns (including X/Z), late
  output-valid and late frame-start. Each requires no publication/release/read
  after fault, followed by fresh 512-word/one-release recovery.

Corrected main and auxiliary actual FFT campaigns both pass, in **199.18 s**
and **185.73 s** respectively. All **64512 indexed numerical records and the
complete CSV remain byte-identical** to the parent. Service stays
**3663/3663/4929/11729/3663/3663 clocks**. Main shadow coverage is 500645 checks,
3136 replay offers, 3132 predicted accepts and **3075 deliberately paused
observations**. Predicted accepts include forced stalls and are not claimed as
actual publications. Auxiliary coverage is 435888 checks, 588 offers, 311
predicted accepts, the complete 512-entry status sweep and all ten recovery
cases. These include the separately checked invalid and late-valid payload
sweeps. Both campaigns retain every inherited boundary test.

An additional 30 historical compatibility tests pass after the monitor
correction. Source-bound evidence tests require complete terminal campaigns,
the status sweep, paused checks and all late-event recoveries; they reject
missing, duplicated, shortened and incorrect evidence. This is bounded actual
simulation and exact inactive-guard algebra, not formal proof of all scheduler
states or a hardware timing/accuracy claim.
Eleven new evidence tests and seven overlapping archive tests pass in 0.21 s;
distinct regression/new-evidence total is 778, excluding repeated subsets.

## Next implementation gate

After successful contract evaluation, add an opt-in replay-specific publication
fence using explicit owner-active outputs, current phase, and the reduced fault
summary. Keep the original path as the default/reference. Do not globally replace
the common fault summary: it still serves active computation and quarantine.
The new fence must fail closed outside its owned quiet context, retain current
external/mailbox vetoes, and never equate private completion with publication.

Re-run numerical, late-status/output/frame, payload corruption, forced-stall,
reset and fresh-recovery tests on that actual runtime change. Then synthesize
and route the integrated subsystem with unchanged constraints. Compare the exact
FFT-status-to-request endpoint and the complete worst/TNS/failure inventory;
do not promote merely because a local path improves.

The inherited route still fails at **−1.661 ns WNS / −474.560 ns TNS / 944 setup
endpoints**. Its checkpoint is retained as parent evidence, not a newly routed
candidate. Native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection
remain required. Full receiver timing/CDC/reset, board clocks, actual 60 MS/s
RX calibration, sustained IIO/Ethernet, reversible `.18` canary and `.17` PPU
Ethernet-only deployment/rollback, 120 ms dwells, 300 s scan and blind host GLRT
comparison are still outstanding. No radio is touched in this diagnostic.

## Pins

Evidence root: `/dev/shm/starlink-replay-quiet.C5YGuYRF`.
V1 prepared: `e7afdc538ae644301e28d2900fb67613032f0487f038d5aa3086383674b83637`.
V2 prepared: `4608ae9ac75663c6e5eee752ee2489d7ef79c38701172d0572218413860ec850`.
Parent CSV: `7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d`.
Inherited routed DCP: `456b3dbb87310f1c68a0188f4568d72552091b8b7e86b9ec81e52a90c7254d1e`.
The recorder rechecks source equality, outcomes, numerical evidence, tests and
the parent route before packaging. Raw failed and corrected evidence is retained;
no local artifacts are deleted. Firmware branches remain DO NOT MERGE.
