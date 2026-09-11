# Local fault pipeline: rejected before route — 2026-09-11

Branch `codex/starlink-rx-only-do-not-merge-local-fault-pipeline`.
DO NOT MERGE. **Functional boundary gate failed; no routing or deployment.**

## Implemented experiment

One separately derived top adds a 33-bit private capture of the already exposed
fault facts, before their guard/global OR reductions. A subsequent original
scalar `fast_fault` register retains the direct CDC source. Already registered
guard faults retain their immediate route to that scalar; unsupported profiles
retain the old fallback. Current public expressions otherwise remain literal.
All 27 parent runtime modules are unchanged.

The intended tradeoff is one extra clock before global fault indication for
new current events. Safety requires current publication vetoes to cover that
interval and common reset to purge pending facts before reuse. This is not
cycle-exact global fault equivalence and has not passed that safety gate.

## Passing evidence and explicit failures

The final regression has **1,306 passing tests**: 1,241 inherited, 27 new
source/witness cases and 38 extracted-register RTL cases. The register cases
exercise all 33 fact bits, supported/fallback profiles, pending reset and X/Z
capture semantics. They validate that register block, not every integrated
source fault or publication boundary. The earlier regression had 1,266 passes
and two failures due to the v1 marker parser; retain both XMLs.

The healthy actual generated FFT run matches all **64,512 numerical words**
against the frozen reference. All six contexts retain 4,178 service clocks.
The v1 Python parser incorrectly double-escaped its digit regex and rejected
the valid local-fault marker. Frozen sources and failed receipts are unchanged.
`audit_local_fault_v3.py` rechecks source pins, actual arithmetic and original
observers, and writes a separate passing healthy receipt. That is a re-audit,
not another simulation. Earlier audit source/receipt remain retained as well.

Synthesis completed on the same frozen main source. **No route was launched.**

The auxiliary actual run passes the previous 31 fault/reset/delay boundaries
and new local boundary 0 (input fault at product publication). It then fails
new boundary 1: unexpected status at that publication edge does not immediately
close the product-publication permission. Boundaries 2–5 were not reached.
The auxiliary outcome remains failed; it cannot be converted into a pass by
the corrected parser. The complete delayed-fault campaign is not proven.

## Actual-FFT parent/candidate reproduction

Two separately pinned, single-forward-job diagnostics inject status VALID with
data `8'h80` while the actual staged final product word is ready to write.
They use the actual generated FFT and actual banks, not a behavioral substitute.
The reader is held. The original main/auxiliary campaigns are not overwritten.

| Observation | Registered-abort parent | Local fault pipeline |
|---|---:|---:|
| Before fault: product request / position | 0 / 511 | 0 / 511 |
| Current combined fault after status injection | 1 | 1 |
| Current external / vendor fault | 0 / 0 | 0 / 0 |
| Product commit permission / RAM accept | 1 / 1 | 1 / 1 |
| Product request after fault edge | **1** | **1** |
| Global fault / guard fault after that edge | 1 / 1 | 0 / 1 |
| Settled fault / host reads / reader releases | 1 / 0 / 0 | 1 / 0 / 0 |

Thus this is an inherited internal-publication gap exposed by the stronger
boundary test, not a newly established host-output leak. Both designs quarantine
and produce no host output in these held-reader probes. The new pipeline does
delay the global indication exactly as expected. Neither observation excuses
the no-new-internal-publication contract; keep the test and fix the gate.

Root cause: `product_commit_authorized` checks `external_fault_now` and the
latched `result_fault`, but not the guards' current local fault view. Here
`vendor_fault_now` includes input halt/TLAST events, not current FFT status.
The combined current fault is already true, but the guard's latched fault only
changes on the same edge as the erroneous internal ownership transfer.

## Next implementation gate

Derive a new candidate with current guard-local fault vetoes on actual product
publication. Check for combinational feedback through READY/framing and reject
unknown authority. Extend boundary coverage to unexpected status, raw output,
frame and input events at the actual final write, as well as both completions,
retained faults, pending reset and fresh recovery. Do not weaken these tests
or rely on the later global abort to retract a publication.

Then rerun actual numerical/service and the complete auxiliary campaign, and
only after both pass route the exact source/DCP. There is no measured timing
improvement for the local-fault pipeline yet. The parent's -1.414 ns all-path
and -1.357 ns same-domain timing failures remain the last routed evidence.
Mailbox CDC/real clock qualification and full receiver timing remain open.

Native 60 MS/s fine and independent 2.5 MS/s inspection sources are unchanged.
Full receiver integration, calibration, continuous RX and sustained IIO/Ethernet
remain mandatory before pinned reversible PPU deployment: `.18` canary, then
`.17` over Ethernet. No radios/PPU/main were touched; `.14/.20/.21` remain
excluded. Primary HDL is not promoted.

## Identities

Evidence root: `/dev/shm/starlink-local-fault.jK1iY7XV`.

- Main inventory `55f381e1950ed92a36f0af44d07d5e087d6b3d467597524e13004ccb71c7c394`.
- Auxiliary inventory `faa4b4a29a3a1261f691351652ce3c1fa5a61784c0ac2b32c90eb7b621b8985c`.
- Synthesized DCP `ef080ea555fcf21abf6cffb1ef0fac6a61249d42a9aacbf1cff5661734bce92d`.
- Parent probe inventory `78b7c743caeae67646b61b82ed7ab85ec3814839941f1bf5a6f1f45ca728f985`.
- Candidate probe inventory `7ba74fe41d342d19ba81b641153b8de9974ac373d232a505559006371ec5c627`.
- Healthy CSV `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

Use the explicit v3 re-auditor for healthy logs; the frozen v1 runner retains
its parser defect for provenance. The failed auxiliary run is intentionally
not accepted by any re-auditor. `probe_product_status_boundary.py` reproduces
the diagnostic on parent/candidate. It is not a functional acceptance test.
