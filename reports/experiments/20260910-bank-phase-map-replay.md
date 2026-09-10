# Buffered scorer through the real phase-map path

Implemented an additive, default-off `USE_BANK_OWNED_XFFT` selector in
`starlink_pss_iq_to_phase_map`. It requires the explicit shared/realtime modes;
the existing shared and dedicated hierarchies remain unchanged when it is off.
The AXI receiver wrapper does not expose the selector, so no receiver build
profile or radio configuration changes. Map arithmetic, phase tagging, health
encoding, publication and stop logic are retained.

## Executed actual-core evidence

All three Vivado 2022.2 runs use frozen HDL
`e7a47ed64adf7ce32e47202a279129497bc0c0f3` and firmware `4ff52c1e0`.
The actual generated FFT is used, with a 100 MHz map/score clock. Each run
replays 1,406 CI16 inputs, checks 1,341 exact scores and reads all 447 exact
map words for a reduced three-frame tile. Peak is phase 0/value 264, maximum
candidate FIFO occupancy 356, healthy flags zero, bounded map payload 894 bytes.
These reduced dimensions are intentionally not production geometry.

| Run | Transform clock | Exit and completion UTC |
| --- | --- | --- |
| New bank-owned path | 175 MHz | 0, 2026-09-10 01:37:29 |
| New bank-owned path | 200 MHz | 0, 2026-09-10 01:38:24 |
| Existing shared/realtime path, bank selector off | 200 MHz | 0, 2026-09-10 01:38:26 |

After reading/releasing the healthy map, each run starts a new partial tile
and injects a raw vendor missing-TLAST fault in the selected actual engine.
The partial tile is aborted, no partial map publishes, detector fault is sticky,
and shared-service health bit 14 is recorded as exactly one detector episode.
The new bank injection runs on the fast clock. Runner admission freezes all
inputs before project creation and rejects invalid clock/mode combinations,
missing inputs, existing evidence and failed assertion text even with a PASS
marker. The 17 new policy tests include malformed/missing terminal receipts.
The combined phase-map/long-soak/evidence policy suite passes 160 tests.

This verifies reduced map integration and the stated fault path, not continuous
production map throughput, bank boundary-stop behavior, AXI/IIO pilot pairing,
native fine search, RF detection or physical timing. The long 4,096-block coarse
soak is separate and remains running. Native source-rate and deployment gates
are unchanged.

Independent read-only review verified the three runs' frozen source/wrapper
hashes and found no regression in selector/default wiring. It did not execute
additional simulations. Important uncovered boundaries remain explicit: the
injected fault is after 100 accepted scores in a fresh partial tile, after the
old map has been released, and the bench waits 40 slow clocks before asserting
quarantine. This does not prove a fault on the final-score/publication edge,
retaining/reading/releasing a previously completed map during a later fault,
or clean restart after that fault. The bench ties both reset inputs together
and disables boundary stop. Those are next integration tests, not implied by
the present PASS markers. Production 20,000-by-64 maps, independent resets,
source gaps/hops, slow-reader bank turnover, lower/upper coefficient identity,
and native-counter/visit support under concurrent pilot/fine traffic also remain.
The existing stop/paired-stop policy and map/PSMA/health suites additionally
pass 172 tests on the merged tree. These are regression checks of their existing
scope, not actual-core bank-owned stop qualification.

## Reproduction and identities

Run `simulate_iq_to_phase_map_xfft.tcl NEW_OUTPUT VECTOR_DIRECTORY 1 1 1 175`
or substitute `200`; omit the last two selectors for the existing shared path.
The actual-core creation helper retains the same generated arithmetic contract.
The different simulated clock does not claim that the physical design meets it.

Archive `20260910-bank-phase-map-replay.tgz` retains full runner logs, simulator
logs, scopes and frozen sources/vectors, without vendor-generated IP or firmware.

- Archive SHA-256: `508ddf60ce6d2fefaf4d975c433e8f95a31949788053328e074df8edcd9b92ed`.
- Bank 175 runner log: `3b0dabbb16e0d10984204ebcfac4d85b236064fef2240bc50c5f88f8ae6e7ab6`.
- Bank 200 runner log: `611aa6b69b29a3b11130a896695e790970b41313c730e2fb3d05e94c940e36ac`.
- Existing shared 200 runner log: `99d6573271750af4e3b6360138243b235dd3a1438a28d7c223fb42e967449062`.
