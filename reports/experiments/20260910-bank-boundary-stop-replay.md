# Bank-owned FFT through the existing PSMA boundary-stop interface

The default-off bank-owned composition now passes the existing reduced-geometry
actual-core boundary-stop scenario at 175 and 200 MHz. The existing shared path
also passes at 200 MHz. No detector arithmetic, PSMA RTL, AXI receiver selector,
firmware build profile, radio or PPU source changed in this step.

Frozen tested source: HDL `69f84febf0a2788f23e04f2f6b3cfec5b33b9c9a`, firmware
`249edd4b535bea7e6537e8c102f49ad1b5f8b07f`. The new code changes only the
testbench/runner and executable policy tests. The bank selector was already
implemented in the preceding phase-map experiment.

## Actual generated-core results

Each run uses a 100 MHz scoring/map/PSMA clock, canonical 15 MS/s source stimulus,
447 phase bins and two frames. All 894 admitted scores, source indices, phases
and denominators match the frozen reference; all 447 map words are read through
the actual synchronous AXI-Lite PSMA path and match the summed reference scores.

| Composition | Healthy stop source count | Negative stop source/checked-score count | Exit 0 UTC, 2026-09-10 |
| --- | ---: | ---: | --- |
| Bank 175 MHz | 1696 | 1626 / 800 | 01:46:40 |
| Bank 200 MHz | 1657 | 1587 / 800 | 01:47:46 |
| Existing shared 200 MHz | 1734 | 1698 / 845 | 01:47:47 |

These source counts measure when the stop was observed in this fixture, not
signal timing accuracy. All runs observe a genuinely started third forward FFT
whose inverse result has not yet fully returned when the healthy two-frame map
stops. For the bank path, the witness observes actual core input acceptance
in the fast clock domain, with the full original block coordinate; merely
capturing into the source bank is not substituted for execution. The inverse
return witness remains in the slow domain where that transfer actually occurs.

The healthy stop preserves exact terminal coordinates/generation/ticket, stops
coarse processing without a coarse flush, and allows the independent source
stimulus to continue. The completed map is read and released; subsequent source
tail does not publish additional maps, modify admitted score counts or leave
the coarse pipeline running. This is not a pilot-capture continuity proof.

Two negative cases execute in each run:

- A real invalid PSMA map release after the healthy stop retains terminal map
  coordinates but marks the terminal health failed.
- Following reset/replay, a raw vendor missing-TLAST event is injected while
  the actual FFT reset epoch is live and stop is pending. It aborts the partial
  map, publishes no partial map, records shared-service health bit 14 and yields
  a failed stop receipt. This is not an event injected into an already reset
  vendor instance, nor a same-edge map-publication race test.

Each run has exactly two stop ACK receipts, all required healthy/negative
markers and a successful runner terminal. The added 15 policy tests cover
literal clock/mode admission, frozen bank-source inclusion, the fast-domain
witness and missing/wrong-clock/late-failure/one-ACK receipt rejection. The
focused runner suite passes 66 tests; these policy tests do not replace RTL
simulation.

## Remaining release gates

This is reduced 447-by-2 geometry. It does not prove production map throughput,
independent domain-reset recovery, final-score/publication-edge faults, retaining
a previously complete map during a later acquisition fault, or healthy
stop/re-enable without external reset. A separate independent lifecycle study
is now allocated in `bank-map-lifecycle` to cover those boundaries explicitly.
Paired canonical/pilot bytes, DMA/IIO, native fine search, source 30/60 MS/s
calibration, real RF, physical timing and .18-before-.17 deployment remain open.
The 4,096-block coarse soak and registered-controller timing experiment run
independently on their frozen inputs and are not qualified by these results.

## Replay and retained evidence

Use `simulate_realtime_psma_stop.tcl NEW_OUTPUT VECTOR_DIRECTORY 1 175` or
substitute `200`; omit the last two arguments for the existing shared path.
The runner retains its exact seven-fixture geometry checks, pinned actual FFT
creation helper, pre-run source hashes and no-overwrite behavior. It now also
rejects explicit assertion failure text even if later PASS markers are present.

Archive `20260910-bank-boundary-stop-replay.tgz` contains the three complete
runner/simulator logs, scope and generated-IP receipts, frozen RTL/bench/helper
sources and vectors. It excludes vendor-generated IP and firmware binaries.

- Archive SHA-256: `359c3da1917b86a573ef8db5464086270b11006870a3cf15c26afb3dd918a9da`.
- Bank 175 log: `3d430c1d1526746fad9891c1d09b5a2becb59ba1db6f2b7535b0578c77615dc4`.
- Bank 200 log: `03873ff1a3169596bff17101e0e21b2fc974f97cb863e0f911256c3773c17459`.
- Existing shared 200 log: `ad85c8bee0f0233bd8a54390418d47093bbb2943fd07251e6fba43c5f278fb73`.
