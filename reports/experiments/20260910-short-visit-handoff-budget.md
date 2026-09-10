# Conditional120ms coarse-to-native handoff budget

The actual full-map simulation does not by itself establish a viable120ms
receiver visit. A new hardware-free source-time model makes the remaining
capture budget explicit without inventing detector acceptance or transport
performance. This is an evaluation oracle, not a PPU scheduler, firmware
profile change or command authorization.

Implementation: `tests/starlink_oracle/visit_handoff_budget.py`.
Tests: `tests/test_starlink_visit_handoff_budget.py`.
The153 new arithmetic tests pass; with the existing scanner-plan tests,
182PASS in0.21s. Ruff passes. The initial153-test run also passed, but its
combined command failed two dictionary-style lint checks; those were corrected
before this final test/lint result.

## Inputs and assumptions

- One120ms valid visit, nominal750Hz repeats and an epoch-relative canonical
  phase in[0,20000). No fractional period, clock drift or timing-error model.
- Original-rate ratioR=1/2/4 for15/30/60MS/s. All timing arithmetic stays integer
  and source-coordinate based, including near the unsigned64 boundary.
- Caller-supplied upper bound on map availability plus command-transport delay;
  neither is a measured/attested runtime bound just because it is supplied.
- Native full capture is `[center-32R,center+98R)`. The entire input window must
  fit inside the valid visit. Winning tap support alone is insufficient.
- Existing host minimum center lead is65536R samples, from
  `tools/starlink_pssctl/starlink_pss_hw.h`. It is not the hardware scheduler's
  distinct64R capture-start lead after `admission_index+1`; both are enforced.

The result is an upper count of geometrically possible capture windows, not
accepted requests or completed measurements. It deliberately does not model
fine-engine service time, queued-result backpressure, time to drain results,
retune/coefficient ownership, RF uncertainty or software timing reliability.
Those can only reduce eligibility or require a separately justified schedule.
No pilot/GLRT result is consulted, so this calculation cannot seed a blind test.

## Conditional example from the measured digital map run

The original15MHz full-map run reports1,280,854 source presentations at its
post-ACK stop observation. Using1,280,854 as a conservative next-sample
availability coordinate gives about85.390267ms. This is simulated source time,
not host receipt time and not a worst-case map-service bound. Use it only as
the explicitly stated planning assumption below.

Enumerating all20,000 nominal coarse phases with that coordinate gives:

| Assumed additional map-read/control/transport delay | Possible full native captures |
| --- | ---: |
|0ms|22–23|
|1ms|21–22|
|5ms|18–19|
|10ms|15–16|
|20ms|7–8|
|30ms|0–1|
|31ms|0|

At coarse phase520 and zero additional delay, the22 possible centers run from
1,360,520 through1,780,520 in steps20,000. They satisfy both lead checks and
the full capture boundary. The model's30/60 rate-scaled cases give the same
22 slots, not more observation time. Scaling this assumed availability to
higher rates is hypothetical; no high-rate combined map latency was measured.

Every tested result is compared against independent brute-force inequalities.
Tests include exact lead equality, a capture ending exactly at the exclusive
visit boundary, one-sample-late rejection, no-slot cases, source-counter limits,
invalid types/rates/phases and source/header checks tying the modeled lead and
capture constants to current native implementation.

## Consequences for the implementation

1. The first coarse map must produce a provisional hypothesis, not silently
   reuse the current three-map lock rule, which needs256ms. Two sequential
   full-map CFO hypotheses also exceed120ms even before host delay.
2. Native capture must use a future supported window computed from a fresh,
   bounded source-counter observation and exact visit/channel/coefficient
   identity. It cannot request the already elapsed coarse peak itself.
3. Measure the actual map-to-command path and native result draining before
   promising a minimum number of fine results per visit. If the bound cannot
   fit, reject/record that visit instead of carrying stale history through a hop.
4. A larger pipeline budget cannot decide which ambiguous coarse peak is real.
   Freeze and evaluate a short-integration hypothesis/rejection policy against
   independent pilot GLRT, including negative visits and competing aliases.

The full goal remains15/30/60 original-rate fine PSS, canonical15 coarse,
independent2.5MS/s IIO pilot, eight targets/120ms valid visits/300s, qualified
physical timing and `.18` then Ethernet/PPU `.17`. This budget closes none of
the live, RF accuracy, clock, IIO or deployment gates.
