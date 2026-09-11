# Actual FFT replay publication fence — DO NOT MERGE

## Decision

The opt-in quiet-phase publication fence is integrated with the actual FFT and
source/product/output buffers, simulated, synthesized and routed. The former
FFT-status-payload-to-output-request path is absent for all five synthesized
status payload registers. Whole-subsystem timing is improved but **still fails**;
this is an experimental candidate, not a deployment or full-receiver signoff.

Keep native 60 MS/s fine search and the independent 2.5 MS/s CI16 inspection
stream in scope. No TX removal, arithmetic changes, radio operations, PPU/main
changes or primary receiver HDL promotion were performed.

## Exact change and behavioral checks

Parent FW `476a32b89e18d982dc70a089e090ec1b4684b6a0`, HDL
`ae352b231f10b2abc415735416a08d94dc525bfe` remains the reference.
Branch: `codex/starlink-rx-only-do-not-merge-replay-quiet-fence` in both repositories.

Only the top-level publication wiring changes among 22 compiled runtime modules.
`REPLAY_QUIET_PUBLICATION=0` retains the original predicate. Opt-in mode requires
the registered scheduling, input summary, contextual destination summary,
private descriptor and closed input profile; unsupported profiles fail closed.
Both the actual FFT bench and synthesis enable the same option.

Publication now requires ACK_DRAIN, the completed inverse producer, no preparation,
and both producer guards inactive. The reduced current fault predicate retains
external faults, mailbox faults/framing, preparation faults and any newly offered
status, output, frame or summary event. No delayed permission or new clocked
state is added. Active-job validation and the real request/ACK release stay intact.
The existing final-word metadata validation is unchanged.

Tests compare the actual publication predicate against the original unforced
predicate and an independent quiet-phase model; explicit forced stalls are
checked separately, not skipped. Their `accepts` counters count predicted accepts,
including forced-stall observations, not actual buffer publications.

## Verification

- 820-test full regression: PASS, 94.30 s. Includes 42 new RTL/profile/source tests.
- 12 new actual-evidence/configuration tests plus seven existing archive tests:
  PASS, 1.78 s. Thus 832 distinct regression/evidence tests, not 839.
- 71 focused preflight tests: PASS. An initial audit command used a nonexistent
  test filename and ran no tests; the corrected 19-test invocation passed.
- Main actual FFT: PASS, 200.776 s; auxiliary fault/ACK campaign: PASS, 197.902 s.
- 64,512 indexed numerical records and CSV bytes match the parent exactly.
  CSV SHA256 `7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d`.
- Service clocks remain `3663/3663/4929/11729/3663/3663` for the six contexts.
- Main quiet witness: 500645 checks, 3136 offers, 3132 predicted accepts,
  including 3075 forced-stall observations.
- Auxiliary quiet witness: 435888 checks, 588 offers, 311 predicted accepts;
  512 status-byte/valid combinations and ten clocked late-event rejection / fresh
  reset recovery cases. No publication/read/release on rejected jobs; fresh jobs
  recover with 512 reads and one release.
- Synthesis: PASS, 101.437 s. Route execution: PASS, 51.204 s, but setup FAIL.

Prepared SHA256:
`74a8ab46a668e51ee3d9b7e3f8a8f4e7a83180b7c9c3168b3ea4b71ab60800a9`.
Synthesized DCP:
`99d6f9dc18ded7856b55ed4cef8f65dddef4b36e67f97cf38fd5b5d0f6c95d20`.
Routed DCP:
`52822300aeea2cba032328efda2c40db032ccb93a6a22385c0e359f9166c7bec`.

## Physical result under unchanged constraints

| Metric | Parent | Integrated fence |
| --- | ---: | ---: |
| WNS, ns | -1.661 | -1.241 |
| TNS, ns | -474.560 | -274.139 |
| Setup failing endpoints | 944 | 572 |
| 175 MHz same-domain WNS, ns | -1.661 | -1.235 |
| LUT | 2819 | 2825 |
| FF | 5804 | 5796 |
| DSP / RAMB18 | 21 / 15 | 21 / 15 |

8502 routable nets are fully routed with zero routing errors. Hold slack +0.082 ns,
zero hold failures; pulse slack 1.830 ns, zero pulse failures. The route recipe,
100/175 MHz OOC clocks and exceptions are unchanged. No multicycle/false-path
waiver was added. Placement effects mean this is one measured candidate, not a
guarantee that every placement improves.

Read-only path queries find no combinational timing path from any of the five
actual FFT status FIFO payload registers to `output_bank/request_toggle_reg/D`.
The original bit-zero path was -1.661 ns. This is a real removed dependency, not
merely a better slack number for a different endpoint.

The remaining worst same-domain path is
`owners[1].result_guard/fault_reasons_reg[3]/C` to that guard's
`commit_pulse_reg/D`: -1.235 ns, ten logic levels, 6.803 ns data delay
(5.107 ns routing). It traverses guard fault, return/publication validation and
common fault feedback. The related fast-fault endpoint is -1.228 ns.

Global worst is a separate held metadata crossing, output-bank input bit 8 to
output-bank output bit 8: -1.241 ns, zero logic levels, 0.894 ns data delay,
under a 0.002 ns inter-clock edge requirement. This needs a justified bundled-data
CDC contract and physical bounds, not arithmetic pipelining or a blanket waiver.
The report still has 114 unconstrained inputs and 124 outputs because this is OOC.

Reset structure remains intact: ASYNC_REG synchronizer first stages drive only
their second stages, and purge crosses from a registered source without logic.
CDC inventory remains nine CDC-3 information items and 208 CDC-15 warnings;
this is not full CDC qualification.

## Next bounded step

Keep this result pinned. Before further features, derive a phase-specific local
guard commit/fault contract for the newly limiting same-domain cone. Prove current
fault rejection and reset/expiry behavior against the reference before replacing
any shared feedback; do not blindly register a fault and permit a bad publication.
Repeat the exact actual FFT, evidence, synthesis and route gates for that change.

Separately qualify each held CDC payload and request/ACK lifetime, then propose
specific physical delay/skew bounds against the real board clock plan. Keep that
change separately measured; neither it nor removal of CDC report entries would
resolve the -1.235 ns same-domain failure.

Only after subsystem timing/CDC gates: full receiver integration and route,
continuous native 60 MS/s fine + 2.5 MS/s IIO verification, actual RX calibration,
sustained Ethernet, pinned PPU package and rollback, .18 canary, then .17 Ethernet
deployment. No present evidence establishes continuous reception, native timing
accuracy or deployment readiness.

Evidence is assessed by `tools/record_replay_fence_evidence.py`, binding prepared
sources, actual logs/CSV, synthesis/route receipts, DCP, test XML and read-only
inspection receipts. Its archive writer verifies every member after read-back.
RAM source evidence remains under `/dev/shm/starlink-replay-fence.I2dOca4T`;
the durable archive/report are in the primary DNM branch's `reports/experiments`.
