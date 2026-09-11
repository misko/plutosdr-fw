# Buffered forward FFT integration — 2026-09-11

Experimental branch: `codex/starlink-rx-only-do-not-merge-buffered-forward-integration`.
DO NOT MERGE firmware/HDL into main. This is not a radio release.

## Outcome

The real generated 512-point FFT, sealed forward-return RAM, kernel ROM,
spectrum product bank, inverse FFT and retained output bank now run together
in a separate experimental top. Numerical and protocol tests pass. **Routed
timing does not pass. Do not deploy this candidate.**

The 22 reference runtime modules and the previously qualified forward-return
RAM remain byte-identical. The added top is an exact, invertible 12-site
derivation of the reference top, not a replacement of the current receiver.
The native 60 MS/s fine-search path and independent 2.5 MS/s inspection stream
have not been removed or edited; this subsystem is not yet wired into that
receiver. No radio was accessed. `.20`, `.21` and `.14` remain excluded;
eventual deployment is `.18` canary, then `.17` over Ethernet/PPU.

## Ownership and arithmetic

Reserve the forward RAM during VERIFY_LEASE, before FFT admission. Capture all
512 real-time raw FFT returns locally. The existing guard independently checks
input completion, output ordinal/LAST, exponent/status and final fence before
sealing. Replay starts only after that seal and feeds the actual elastic
kernel/product pipeline. The forward guard acknowledges only after the real
product bank has acquired ownership. The inverse phase cannot start before
that acknowledgment. Clear the forward allocation certificate at completion,
not when the private RAM merely becomes empty.

Pre-seal readiness means exclusive owned storage, **not** raw capture capacity:
raw capture capacity legitimately falls after word 511, before the guard's
held LAST seals. Post-seal readiness still means actual product-bank validity.
Current faults veto publication; registered quarantine also stops private work.
The RAM abort input uses registered fault sources, avoiding a combinational
self-reference through its own current fault output.

## Tests and measured cost

- 1,130 regression tests passed (1,115 inherited plus 15 source-boundary checks).
- 29 evidence-auditor tests passed, including missing/duplicate/corrupt numerical
  records and incomplete fault/reset/recovery witnesses: **1,159 distinct tests**.
- Main actual-FFT run: six contexts, three blocks each, three 64-bit timestamp
  bases including high-bit patterns, with and without stalled output reads.
  All **64,512 words across seven streams** independently match the frozen
  previous actual-FFT numerical reference. Forward RAM replay is also checked
  word-by-word inside the bench.
- Actual forward-to-forward service: **4,177 clocks** in every numerical
  context, versus the reference's 3,663. At 175 MHz that is 23.87 us, below the
  5,215-clock / 29.8 us budget for 447 fresh canonical-15 samples. The extra
  buffered scheduling costs 514 clocks. This is not continuous receiver proof.
- Auxiliary actual-FFT run repeats the numerical contexts, then injects six
  faults: wrong capture ordinal, inconsistent exponent, current input fault
  on the sealing edge, corrupt replay ordinal, extra raw return, and a status
  event during replay. All reject publication/reuse and recover with 512 fresh
  correct output words after reset.
- Eight reset tests: each reset input separately during partial capture,
  captured-but-unsealed storage, mid-replay stall and held final replay word.
  All discard stale ownership and recover with 512 correct fresh output words.
- Two positive delay cases: status withheld until 17 clocks after complete
  capture, and 128 clocks of elastic replay backpressure. No premature replay,
  lost/repeated word or premature product ownership was observed.

These finite campaigns do not replace exhaustive correctness, all historical
fault scenarios on the new topology, CDC qualification, RF truth or real IIO.
The 1,115 inherited tests exercise the unchanged reference components/topology;
they are not misrepresented as 1,115 integrated buffered-mode tests.

## Routed evidence — failed gate

Vivado 2022.2, xc7z010clg400-1, two threads, unchanged 100/175 MHz OOC recipe,
generated FFT wrapper and no timing exceptions.

| Metric | Scalar-fault reference | Integrated forward buffer |
|---|---:|---:|
| WNS | -1.283 ns | **-1.559 ns** |
| TNS | -255.361 ns | **-348.591 ns** |
| Failing setup endpoints | 607 | **742 / 14,202** |
| LUT | 2,759 | 2,735 |
| FF | 5,795 | 5,800 |
| RAMB18 | 15 | 16 |
| DSP | 21 | 21 |

All 8,434 routable nets routed, zero routing errors. Hold slack +0.058 ns,
zero hold failures; pulse slack +1.830 ns, zero pulse failures. The CDC report
still has nine CDC-3 structures and 208 CDC-15 warnings, no CDC-10 entry.
There are 114 inputs and 124 outputs without OOC delay qualification. Neither
the CDC counts nor successful routing constitute full-board signoff.

Worst path: `registered_scheduling.engine_metadata_reg[42]/C` to
`completion_gate/legacy_facts.snapshot_good_reg[29]/D`, entirely in island_175.
It has six LUT levels and 7.149 ns data delay, of which 5.949 ns (83.214%) is
routing. The next reported violation reaches the inverse guard from an inverse
tag register. Buffering did not cure the remaining wide ownership/control
distribution, and it worsened this placement's aggregate timing.

Completion snapshot bit 29 maps to expanded reject bit 29, original admission
reject bit 15, i.e. the descriptor/header preflight event. That event is active
only in VERIFY_LEASE/ARM_JOB, whereas completion requests require ACK_DRAIN.
The next bounded candidate should prove and exploit that phase separation at
the **private completion snapshot**, keeping same-edge public fault vetoes,
quarantine, product identity and reuse checks intact. Also inspect whether
private fact capture can remove redundant invalid-snapshot reset/control
fanout. Do not simply delete identity checking or relax the clock.

## Reproducible identities

Evidence root: `/dev/shm/starlink-buffered-forward.mZfKEBtK`.

- Main prepared inventory: `f4b18fe4f9a10f4b1ebd69e4546d81b064863ea4894694838e1d912e52f5b860`.
- Auxiliary prepared inventory: `3c99f0896db17caf863f323dec9de6d33533556ce621d4f32c83be493e4fc3f0`.
- Main and auxiliary numerical CSV: `03f8aa63333b5aac4f2b06b02c3b794a928049075ce324423db47e12d2427e9f`.
- Synthesized DCP: `2c71d5a22284e10c9bb26781fb464a8d7a254f43edde048eb36c88a8757b563d`.
- Routed DCP: `c1c4774538511b8549f64a51c8f9de81e95241e88a730cb2d62d3ecb6f833f9c`.

`buffered_forward_experiment.py` prepares and runs main actual/synthesis;
`buffered_forward_auxiliary.py` adds the independently enumerated fault tests;
`route_buffered_forward.py` re-audits both actual runs and source identity before
routing the synthesis checkpoint. `audit_staged_fft_route.py` independently
cross-checks the route/clock-pair reports and DCP receipts.

Deployment still requires this subsystem to meet timing, full-receiver
integration/routing with actual clocks and CDC/reset contracts, native fine
and inspection regressions, 60 MS/s RF calibration, continuous capture and
sustained Ethernet/IIO validation, then pinned reversible PPU canary testing.
