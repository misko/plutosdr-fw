# Private forward capture: standalone internal timing closes

DO NOT MERGE firmware into main or deploy this component alone.
Branch `codex/starlink-rx-only-do-not-merge-private-forward-capture`;
FW `3557f9c270e37a13aae7ea2542946b7a59f94358`,
HDL `fa314a25f3ab2ef85bf3db39066c5e6020aefed8`.

The forward-return bank's write counter and first-word exponent now advance
with its already-private RAM write. Wide descriptor/fault qualification no
longer gates that private progress. A bad beat can change private values on
its rejection edge, but current fault still immediately fences replay and
same-edge registered quarantine prevents any reuse before reset. No added
latency, storage, timing exceptions or clock changes.

## Verification

**1115 distinct tests pass:** 1099 regression (118.59 s) and 16 new guard/bank
contract tests. The 53 component/equivalence tests are included in regression.
An exact inverse reconstructs the parent bank. Across 21 existing scenarios,
85038 before/after-edge comparisons preserve controls, faults and valid payload.
All 72 observations of differing private values are behind quarantine.
Invalid payload outputs are not asserted equal. This is finite scenario
coverage, not exhaustive formal proof.

Both exact-source actual-FFT observer campaigns pass, unchanged from the parent:
71/73 complete blocks, 37689/37455 checked words, 109/92 reservations, 98/81 seals,
15077/15008 stalled-valid cycles. Counts include private prefixes cancelled by
intentional faults, not public detector results. Main/aux elapsed 209.61/186.89 s.
All 64512 original numerical rows and original service clocks remain identical.
The original 22 receiver modules and bench stimulus are unchanged; the observer
does not drive the DUT. This does not prove the new buffered receiver schedule.

## Standalone physical result

| Metric | Parent bank | Private capture |
| --- | ---: | ---: |
| WNS (ns) | -0.181 | **+0.186** |
| TNS (ns) | -7.073 | 0 |
| Setup failures / endpoints | 59 / 167 | **0 / 167** |
| Hold / pulse slack (ns) | +0.167 / +2.357 | +0.195 / +2.357 |
| LUT / FF / RAMB18 / DSP | 75 / 111 / 1 / 0 | 72 / 111 / 1 / 0 |

Same Vivado 2022.2 / xc7z010clg400-1 / 5.714 ns standalone recipe. All 151 nets
route without errors. Replica-inclusive queries find all 70 descriptor and
ten counter registers in both checkpoints. Parent descriptor-to-counter CE
slack is -0.181 ns; the candidate has no combinational path from those
descriptor registers to the counter's data, enable or reset pins. The new
worst internal path is write-count bit 3 to state enable, seven levels,
5.239 ns data delay. Capture readiness and complete SDP writer controls remain
independent of downstream READY.

**Only standalone internal timing has passed.** The 197 input / 127 output
ports remain unqualified by that recipe. The actual FFT subsystem, full
receiver, CDC and board-clock signoff remain open; their failing route is not
fixed by this local result.

## New guard/bank contract and next integration

The real guard and bank RTL are connected in a separate fixture with synthetic
FFT events and fixture-driven product ownership. Both unrestricted guard mode
and known completed-input/forward-retirement mode pass six scenarios each:
normal completion, delayed status, delayed fence, delayed product ACK,
final-edge abort/recovery and held-replay reset. Two unsafe readiness mutations
are rejected in both modes.

The key contract is now tested: after 512 raw words the bank's capture-ready
falls, but the guard still holds the final word pending independent status and
fence qualification. Its final handshake must use **exclusive ownership**, not
raw write capacity; the latter deadlocks. After commit, it must await actual
qualified product ownership. Buffer drain alone is not a product ACK.

One initial fixture assertion sampled before combinational settling after
raw-valid deassertion; the failed run is retained and the bench was corrected.
The first assessment also rejected pytest's latest-case alias as a duplicate;
the final recorder counts only real case directories. Neither correction
changed bank or guard RTL or weakened an acceptance condition.

Next reserve the bank before core start, capture raw forward returns locally,
seal on guard qualification, and feed sealed replay to the kernel/product
stage. Join actual product ownership into inverse admission; re-prove caller
fault/reservation contracts for the changed wiring. Measure complete sustained
service, then route the actual FFT plus buffers. The 3663+512 versus 5215-clock
planning estimate remains unproven. Keep native 60 MS/s fine search and the
independent 2.5 MS/s CI16 IIO stream.

Full receiver timing/CDC/reset/real clocks, actual 60 MS/s calibration,
sustained Ethernet/IIO, blind GLRT, 120 ms dwells and 300 s scans remain gates.
Then qualify pinned PPU/rollback on .18 before .17 Ethernet-only deployment.
No radios, PPU/main or primary HDL gitlink changed; .14/.20/.21 excluded.

## Evidence

[Verified archive](20260911-private-forward-capture-evidence.tgz),
[read-back receipt](20260911-private-forward-capture-evidence.json):
21,078,567 bytes / 6702 members, SHA256
`b968abd9ccb3e602f89e405127533de6e484897f0b4eb2b3183b9859830b3217`.
Includes frozen actual sources/logs/CSV, component/equivalence/guard tests,
failed/corrected fixture evidence, standalone synthesis/routed checkpoints,
matched parent/candidate paths and complete write-port checks. Duplicate
vendor VHDL and historical regression artifacts have an explicit hashed
omission inventory; raw evidence remains retained.

Raw root: `/dev/shm/starlink-private-forward.hbi1EUk2`.
Prepared SHA: `99af4fda00461dce42479a9d8ff6b053af08d0d5ada504877f2957d204b24114`.
Bank SHA: `6fc9efc9c34a890e0b450bbd071417bf3e7ef933397ff4637d4eff8519173bbd`.
Routed DCP SHA: `eb3b18c3a00610a4985526bf2f9cb0a63dc3dfb02e90bfec6f60e90247e3c1e3`.
[Parent bank experiment](20260911-forward-return-bank-actual-observer.md).
