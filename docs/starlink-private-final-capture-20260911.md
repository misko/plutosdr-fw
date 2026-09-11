# Private final-data capture — DO NOT MERGE

Independent candidate on private-capture reference FW `fcc3dc202` / HDL
`c25126a2e`, not composed with the staged-final, ordinal or fault-summary
regressions. Branch: `codex/starlink-rx-only-do-not-merge-private-final-capture`.
This is an actual FFT/buffer subsystem, not a complete receiver release.

## Implemented contract

The adapter's 69-bit bundle (32-bit tag, 36-bit final word, initial request bit)
has a separate capture always-block. With the default-off PRIVATE_FINAL_CAPTURE
enabled, it tracks input payloads while the registered phase is EMPTY. On the
original qualified completion handshake, the same inputs are captured and
the original phase transition locks the bundle. It remains frozen through
COMMIT, final-word replay, publication, real reader ACK and descriptor RELEASE.
An idle capture, including during a fault, grants no publication authority.

Only the experimental FFT top opts in. The default retains qualified capture.
The public handshake, fault predicates, ledger, replay authorization, bank
request observation and reader ACK checks are unchanged. No register latency
or payload bank is added. Invalid replay tag/data have no meaning and may
now change while EMPTY. That deliberate private difference is excluded from
public equivalence comparisons; every accepted and held bundle must match.

## Executed functional verification

25 adapter tests pass in 0.99 s: twenty complete candidate/original comparisons
using the actual dual-clock payload bank (enabled/disabled, five cancellation
positions, 1/37-cycle stalls), and five unsafe mutations that fail. The original
adapter is pinned by SHA256, not reconstructed. The comparison checks complete
public outputs and command/phase state each cycle, and accepted/owned payloads.
Invalid completion payloads churn between numeric and X/Z values while idle
and throughout replay/reader backpressure. Three successive transactions and
fresh-epoch recovery verify reuse. Mutations cover continuous loading, qualified-
only loading, missing acceptance capture, early unlock, and wrong final data.

Source/lint preflight passes two tests. Actual generated FFT simulation passes
in 109.88 s. All 64,512 numerical records independently match the pinned reference;
the CSV is byte-identical to private capture. Six contexts retain service
3659/3659/4927/11727/3659/3659 clocks. The intentionally stalled reader context
has no 5215-cycle service claim; the others pass that unchanged bound.

The full previous reset/fault/admission/completion/replay/writer/capture campaign
passes. The new per-cycle monitor checks 196,225 loads, 60,251 holds, 43 accepted
completions and 1,171 loads during fault conditions. Every owned bundle matches
the original qualified capture, including reset and fault tests. Existing
current-fault publication-veto and real-reader release assertions remain active.
These counts include aborted jobs, not just the eighteen healthy outputs.

## Evidence and scope

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Folders: `staged-finalcapture-{prepared,actual,synth,route}-v1` and
`staged-finalcapture-{unit,preflight,regression}-v1` with XML receipts.
Source-matched synthesis completes in 102.72 s. Actual/synthesis before/after
source checks pass; routing and full regression results are recorded below.

## Routed result: mixed improvement, still FAIL

417 combined regression tests pass in 52.67 s: 382 baseline tests, 25 complete
adapter/mutation tests and ten actual-evidence parser controls. The parser
rejects missing/duplicate receipts, low coverage, disabled original-payload
checks, missing parent evidence and errors after a success marker.

Route completes in 56.70 s. Independent audit verifies original sources,
synthesis/routed checkpoints, routing status, clock-pair reports and summary.
All actual/synthesis/route runs and tests succeed on their first invocation.

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private-descriptor capture reference | -1.969 ns | -813.676 ns | 914 |
| Plus private adapter final capture | -2.005 ns | -634.847 ns | 856 |

Total negative slack improves by 178.829 ns (about 22%) and 58 fewer endpoints
fail, but worst slack is 0.036 ns worse. This is not a timing pass or an
unqualified improvement. Retain both references. 856/13801 endpoints fail;
hold +0.070 ns and pulse +1.830 ns pass. 8412 nets fully route with zero errors.
Resources: 2785 LUT / 5668 FF / 21 DSP / 15 RAMB18, zero RAMB36. Unchanged
diagnostic 100/175 MHz clocks; no exceptions or timing waivers were added.
Five critical CDC findings, 208 warnings and 114/124 unconstrained I/O remain.

The worst path now starts at product block-start metadata and passes through
bank metadata comparison, shared fault qualification and forward acceptance
to kernel `expected_bin_index[8]/CE`. Ten levels, 7.430 ns data delay,
5.734 ns routing. The next path (-1.907 ns) feeds expected-next-block metadata.
The final-data capture enable is no longer the reported worst endpoint.

## Next implementation gate

Inspect the forward/kernel ordinal and next-block identity boundary together,
not just the nine-bit index. The prior private-ordinal experiment alone routed
worse and is not automatically promoted. A source-matched composition with
this capture change is a possible bounded test, but must preserve public
per-bin/next-block identity checks, final qualification and fault quarantine.
Alternatively partition the shared metadata/fault dependency with registered
ownership. Compare complete timing metrics against both retained references,
and rerun actual FFT/stalls/fault/reset tests before accepting a composition.
Do not relax clocks, remove current publication vetoes or add receiver features
before this subsystem passes its physical gate.

Inventory: `49b2b174d13007264b6d4f6b9733a6f2930a7ecd8cff942d02ef9c8bd5496f44`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Original adapter: `1f971b4a50421ac4162ba4ff9a30f42431e29ff926881e343a321a3519d95343`.
Synthesis DCP: `21b12f88aaf6d6bce9cddd6a903411b279cfdc957ead0fa26c384494ab64e641`.
Routed DCP: `d0ad74cb1150d6ef75939e170d196eb72255316940abcd1d74cb4f3c5d61b1be`.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Full receiver timing/CDC/reset/board I/O, continuous capture, actual
60 MS/s RX calibration and Ethernet verification remain deployment gates.
Then use `.18` reversible canary, followed by `.17` PPU Ethernet-only deployment
with pinned rollback. Final verification remains a 300-second scan, 120 ms
valid dwells and blind host GLRT comparison. No radio, PPU, main or primary
production HDL gitlink has changed in this experiment.
