# Local completion facts — functional equivalence, timing regression

2026-09-11. Branch `codex/starlink-rx-only-do-not-merge-local-completion-facts`.
DO NOT MERGE into main. This candidate is **not deployment eligible**.

## Exact change

Preserve all 24 buffered-reference runtime modules. Add a derived experimental
top with three exact substitutions: module name, completion certificate
configuration, and its check-vector connection. The private completion
certificate now stores 36 facts instead of 42 and uses the already-tested
private payload-capture mode. The six omitted facts are the preflight events
at expanded rejection bits 31:26. They are inactive outside VERIFY_LEASE and
ARM_JOB, whereas completion requests require ACK_DRAIN. Retain the original
42-bit expression for simulation comparison; no current public-output veto,
sticky fault, admission check, product identity check or reuse check is removed.

Only invalid snapshot payload values may differ. A read-only original 42-fact
certificate observes the same actual request, reset, quarantine and consume
signals and compares every valid fact and authority signal against the candidate.
This proves the sampled private-certificate relationship for the tested states;
it is not an exhaustive formal proof of the entire receiver.

## Verification

**1,191 distinct tests pass:** 1,165 regression tests plus 26 evidence-auditor
tests. The regression includes 1,159 inherited tests and six new source/unit/
mutation tests. The separate six-test component run is a subset, not another six.

The certificate test performs 72,338 before/after-edge comparisons, including
all 16 known FSM encodings, each fact at 0/1/X/Z, selected single-X/Z state bits,
held/consumed/cancelled snapshots and 20,000 seeded random cycles. It checks
2,394 owned snapshots and 240 permits; 69,824 differences occur only in invalid
private payload. Four mutants (omitted real fault, quarantine, request, or wrong
fact expansion) are rejected. Do not extrapolate this to every arbitrary unknown
FSM encoding or every physical upset.

Actual generated FFT simulation:

| Run | Certificate comparisons | Owned snapshots | Permits | Invalid payload differences |
|---|---:|---:|---:|---:|
| Main | 88,548 | 36 | 36 | 88,476 |
| Auxiliary v1 | 224,178 | 68 | 68 | 224,042 |
| Auxiliary v2, route gate | 326,948 | 103 | 101 | 326,746 |

All three actual runs independently re-audit 64,512 numerical words across
seven streams against the frozen original FFT reference. CSV bytes are also
unchanged from the buffered parent. All six numerical contexts retain exactly
4,177 service clocks (23.87 us at nominal 175 MHz), below the 5,215-clock
canonical15 budget. This remains a subsystem schedule measurement, not
continuous 60 MS/s receiver/750 Hz measurement proof.

Both auxiliary runs pass six raw/replay/current fault cases, eight reset
boundaries and delayed-status/backpressure tests. Auxiliary v2 additionally
ports ten historical completion cancellation cases to the new buffered top:
current status faults at snapshot, permit and receipt for each FFT phase;
corrupt forward product metadata and position at permit; and either reset
input during inverse completion. Each checks cancelled core reuse/publication
and recovers with 512 correct fresh words and one actual reader release.

## Routed result: do not promote

Same Vivado 2022.2, xc7z010clg400-1, 100/175 MHz OOC clocks and routing recipe;
no timing exceptions or relaxed clock. Actual main and extended auxiliary
results are source-matched and re-audited before routing the exact synthesis DCP.

| Metric | Buffered reference | Local completion |
|---|---:|---:|
| WNS | -1.559 ns | **-1.655 ns** |
| TNS | -348.591 ns | **-504.761 ns** |
| Failing setup endpoints | 742 / 14,202 | **1,163 / 14,131** |
| LUT | 2,735 | 2,719 |
| FF | 5,800 | 5,787 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

All 8,427 nets route without errors. Hold +0.058 ns and pulse +1.830 ns, with
zero failures. CDC observations remain nine CDC-3 and 208 CDC-15 warnings;
114 inputs and 124 outputs are still OOC-unqualified. This is not board signoff.

Worst path: `output_bank/metadata_in_hold_reg[20]/C` to
`output_descriptor_pending_reg/D`, seven LUT levels, 7.245 ns data delay,
5.725 ns / 79.021% routing. The same metadata-validation source reaches many
other failing endpoints: inverse commit, descriptor validity/fault/lock,
completion staging, bank request toggle and global sticky fault. The design
remains dominated by broad current metadata-to-control dependencies. A smaller
private certificate alone does not cure them.

Retain this as tested simplification evidence, **not** as a timing improvement.
The buffered parent remains the better measured integrated timing reference.
Next budget and prototype an explicitly buffered/registered inverse-output
identity-validation boundary. Capture payload and identity together, validate
locally, and delay publication until the validated final word and actual bank
ownership are confirmed. Reuse existing identity-stage patterns where suitable.
Keep current error fencing at the real publication boundary; never substitute
a stale generic permit. Require stall, final-word, late-fault, reset, metadata,
and real-ACK tests plus actual arithmetic before routing it. Added latency must
be measured against the existing 4,177/5,215-clock budget, not assumed free.

The native 60 MS/s fine-search and 2.5 MS/s inspection receiver sources remain
unchanged. No radios or PPU were accessed; `.14`, `.20` and `.21` are excluded.
Full receiver integration/timing, real clocks/CDC/reset, calibration, continuous
RX and Ethernet/IIO remain required before reversible `.18` canary and `.17`
Ethernet/PPU deployment.

## Identities

Evidence root: `/dev/shm/starlink-local-completion.NLEj23MI`.

- Main inventory: `32bf941c35383d534bebb2c0d9d0e38c38d2c4d6c9e705d1c344a83f3ccd83cd`.
- Auxiliary v1: `556de300bbb087f99cace7c9e521b486cf0de21576ab06f86037881e59bd4e33`.
- Extended auxiliary v2: `0260df5108960e6a5e8ebbee6c0e04e05478ace6637ea2642adedbc4f2f3e07c`.
- Numerical CSV: `03f8aa63333b5aac4f2b06b02c3b794a928049075ce324423db47e12d2427e9f`.
- Synthesized DCP: `c7342a2d762fd6641d638db84845c34bed4494a63475df2acf4ee9a4a47a36c9`.
- Routed DCP: `f6a0e7ddc6ce49f74cbe725d3d4b98774a71ee47c4a1e315d6d78ac547f0d095`.

Use `local_completion_experiment.py`, `local_completion_boundaries.py`,
`route_local_completion.py` and `audit_staged_fft_route.py` for the respective
source-pinned stages. Evidence includes all prepared versions, original and
extended actual logs/CSVs, generated wrappers, routed/synthesized checkpoints,
raw reports, test sources and receipts. No source was edited during a live run.
