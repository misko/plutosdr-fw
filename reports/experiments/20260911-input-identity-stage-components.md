# Registered input identity boundary: component implementation and evidence

New branch `codex/starlink-rx-only-do-not-merge-input-validation-stage`:
FW `30afa5c05`, HDL `569c1d59631126c1185d549c2cd50dcbb7af6c27`.
Based on the retained preflight/publication proof (`a2ca89ae7` / `ba8bfdf21`),
not the publication-scope timing regression. **The integrated FFT top and all
17 of its runtime modules remain unchanged. No timing or deployment pass.**

## Concrete progress

Added a one-beat private register that captures data, ordinal, LAST and the
result of all 70 metadata identity comparisons together. It supports simultaneous
retire/refill, retains the entire final word after upstream acceptance, rejects
unknown identity evidence, and cancels/quarantines on abort or unknown controls.

Added a variant of the actual input checker that consumes this registered
identity bit. A pinned complete-source inverse confirms every other checker
equation is unchanged: per-beat ordinal/LAST, duplicate start, realtime demand,
certification, completion and sticky reasons. The stage's valid signal alone
does not authorize an FFT beat. A caller must use both components together.

This targets the surviving phase -> metadata comparison -> fault -> publication
path. It places the comparison before a register, rather than delaying a common
publication veto after the fact. It is an architectural candidate, not a
cycle-equivalent local replacement: upstream acceptance moves one stage earlier
than checked FFT consumption, and ownership/cutover must account for that.

## Verification

**16 focused tests pass in 0.40 seconds**, including unchanged integrated-runtime
and preflight-order checks and existing top lint. Not the full project suite.

- Stage: 512 continuous words and 511 retire/refills, followed by a 200-cycle
  final-word stall while upstream data/descriptor change.
- All 70 identity bits with five bad/unknown cases each: 350 rejected cases.
- 4096 deterministic randomized cycles; complete run conserves 2280 accepted
  beats as 2272 retired plus eight explicitly discarded by reset/abort.
- Seven abort/unknown-control cases and fresh recovery. Six unsafe mutations
  fail (refill, data, bypassed identity, unknown equality, reset and abort).
- Stage plus actual checker logic: three healthy 512-word jobs, core waitstates,
  eight malformed jobs stopped at the exact valid prefix, a missing-sample gap
  correctly rejected, and reset while the final word is buffered before completion.

There is no vendor FFT in these new tests. The earlier full FFT evidence belongs
to the unchanged parent; it does not establish correctness of a future integrated
stage. No new synthesis or route has been run.

## Next implementation gate

Integrate the pair into the actual FFT/buffer top. Bank READY must mean capture
into the stage; certified counts and input completion must remain actual FFT
consumption. Update offered-beat summaries to the stage output. Bind descriptor
capture to the admitted phase, preserve ownership through the buffered final
word, and include stage reset/occupancy/faults in the existing cutover contract.
Do not treat early upstream LAST acceptance as FFT completion or publication.

Run actual FFT numerical and hostile-boundary tests, including priming, real
core demand, full-stage reset, stalls, malformed words and no stale data on reuse.
Measure service cost without relaxing the 5215-clock gate or simulation deadline.
Then synthesize and route the entire subsystem with unchanged constraints before
adding features. The original guard-fact reference still fails at -1.340 ns;
publication scope regressed to -1.888 ns. No new timing improvement is claimed.

The full objective is unchanged: native 60 MS/s fine search, independent 2.5 MS/s
IIO inspection, complete receiver route/CDC/reset/calibration/Ethernet validation,
reversible `.18` canary, then `.17` PPU Ethernet-only deployment with rollback,
and 300-second / 120 ms valid-dwell scanning with blind host GLRT comparison.
No radio, PPU/main or primary production HDL changes. Production HDL pin remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Evidence and continuation

[Source/test archive](20260911-input-identity-stage-evidence.tgz) and
[receipt](20260911-input-identity-stage-evidence.json): 367213 bytes, 217 members
(185 files plus directories), byte-compared against original sources. No links
or unsafe member paths. SHA256:
`d9393036451de5fe593bb01db1ce6aa64160fb34cdd24a4bee00d59062794640`.

Includes new RTL/benches/tests, original checker/top reference, all three focused
run logs/XML and the detailed integration contract. Compiled simulation images
and pytest's absolute `current` symlinks are excluded. An initial local archive
containing those convenience links was moved aside in recovery, not published.

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/input-validation-stage-worktree-v1`.
Tests: sibling `input-identity-stage-{unit,checker,reference}-v1` and XML files.
Detailed integration contract: `docs/starlink-input-identity-stage-20260911.md`
in that worktree. No live build or hardware operation remains from this step.
