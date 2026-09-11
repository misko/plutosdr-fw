# Parallel output metadata comparison — DO NOT MERGE

Branch: `codex/starlink-rx-only-do-not-merge-split-output-metadata` (FW and HDL).
Parent FW `1d0cd4b03c44f2dd0c67a2740d8efbfe18c34f0a`, HDL
`c0200466c06dae37907c467926935bc3ae379fa6`.

## Runtime

The output mailbox receives live metadata, replay metadata and the existing
phase selector separately. It compares both sources against its actual held
first-word descriptor in parallel, then selects the one-bit current comparison.
The selected metadata vector itself remains the original ternary mux for first
capture and reader delivery. No descriptor is assumed constant, no certificate
or fault is delayed, and no state or pipeline latency is added.

Both equality trees retain three-bit leaves and six-way reductions. For an
unknown selector, selecting equality results is not equivalent to comparing the
original bitwise-merged metadata. An explicit fallback retains the original
four-state comparison. For example, live=0, replay=3, held=1, select=X gives X
in the original, whereas simply selecting the two mismatch results gives 0.

The specialized mailbox is an exact copy of the pinned original apart from
its name, split input ports, original internal mux and comparison block. All
framing, private RAM/cursor writes, explicit publication, reset and real reader
ACK logic remain literal. Source and product mailboxes remain unchanged.
The compiled inventory adds this output variant: 22 runtime modules, 39
prepared files. Top-level edits only change the output mailbox type and metadata
connections. The old mailbox remains the independent component reference.

This is a combinational restructuring, not the registered output certificate
suggested as a possible next architecture in the parent report. Measure this
lower-latency alternative before introducing another ownership boundary.

## Tests and caller fidelity

Initial component V1 omitted the caller's current-framing authorization fence:
it forced explicit authorization high even when metadata comparison was X.
The original mailbox can publish under that invalid premise. V2 corrects both
reference and candidate connections to request authorization AND NOT current
framing fault. It is not a runtime fix or a claim that the original mailbox
alone fails closed for all X inputs. Both failed/corrected test receipts are
retained, and the actual top-level authorization is unchanged.

Final component/preflight comparison checks **9098 observations**, including
**444 selected-bit corruptions** (37 bits × live/replay × nonfinal/final ×
known inversion/X/Z), nonselected corruption, unknown selector cases, an
unpublished held final, actual publication/read/ACK and reset/fresh recovery.
Four unsafe comparator mutants fail. The internal comparison is checked only
when its first-word reference is meaningful, or in explicit forced-reference
four-state cases. Exact source inverses constrain all other runtime edits.

Focused preflight: **23 tests pass in 0.33 s**. Full regression:
**637 tests pass in 82.93 s**. The preflight overlaps, not additional tests.

The actual bench compares selected current metadata against the original held
descriptor at every real output-bank acceptance. It adds six auxiliary cases:
corrupt live tag at nonfinal/final acceptance, corrupt replay tag/exponent, and
fast/slow reset at replay. Corruption must assert immediate framing fault and
veto publication; cancellation must stay unpublished and each case must finish
with 512 fresh reads and one actual reader release. Original cases and both
3 ms deadlines remain. Main/auxiliary/synthesis must be source-matched and
freshly audited before routing.

Actual V1 main passes in **211.25 s**, all 64512 numerical records and service
intervals matching the parent. V1 synthesis completes in 99.54 s. V1 auxiliary
fails on the first new injection assertion and is **not routed**. V2 moves
the new cases before the inherited auxiliary cases for faster failure reporting
and prints the actual selected/reference metadata. Its diagnostic shows the
force at the split concatenated input port did not reach the input: both values
remain `0000000003`, equality stays 1 and framing stays 0.

V3 injects at source tag/exponent signals instead, verifies that selected
metadata actually differs, then checks current framing/publication behavior.
The four corruption cases show known mismatch, framing=1 and replay_accept=0;
both reset cases and all six fresh recoveries pass. This corrects the stimulus,
not the runtime. All 22 compiled runtime modules remain byte-identical in
V1/V2/V3. The new cases run first, but the inherited cases retain their relative
order and the same deadlines. All three source snapshots and their terminal
results are retained, not overwritten.

Corrected V3 preflight: 11 tests pass in 0.26 s. Final regression:
**637 tests pass in 82.51 s**. Auxiliary V3 completes in **128.21 s** with all
six new cases and all inherited cases passing. Its output metadata witness
checks **23597 acceptances: 23554 live and 43 replay**. Because new cases run
first, inherited cumulative witnesses now include them: split capacity checks
303655 clocks / 31133 nonfinal transfers, and the original ACK comparison
checks 121046 clocks with 306 private quarantine differences. These counts are
not RF events or additional numerical contexts.

V3 synthesis completes in **99.69 s**. Main V3 passes in **196.44 s**:
**64512 indexed numerical results**, complete CSV and all service intervals
remain identical to the parent. Service is **3662/3662/4929/11729/3662/3662
clocks**; the intentional 9000-clock reader stall remains excluded from the
unchanged 5215-clock gate. Main output witness: **39485 acceptances, 36352 live
and 3133 replay**. These include held-final replay checks, not distinct frames.

The final evidence suite adds 15 tests for source identity, complete actual
proofs, missing/altered branch and recovery receipts and route-gate bypasses.
Together with the 637 regressions this is **652 distinct tests**; the seven
archive-writer tests in the evidence invocation overlap the regression suite.

Routing V3 completes in **48.97 s**. **Setup still fails: -1.258 ns WNS,
-328.306 ns TNS, 692 of 14165 failing endpoints**. Parent:
-1.938 / -541.200 / 981. The worst same-domain 175 MHz path improves to
**-1.215 ns**, versus -1.938 ns in the parent. No constraints or timing exceptions
changed, and the failing build is not promoted or deployed.

All 8422 nets route without errors. Utilization: 2747 LUTs, 5793 flip-flops,
21 DSPs, 15 RAMB18s, no RAMB36s. The implementation uses 30 fewer LUTs and five
more flip-flops than the parent, despite no added RTL state. Hold +0.062 ns and
pulse width +1.830 ns pass. 114 inputs and 124 outputs remain unconstrained
in this isolated diagnostic.

The worst overall path is now a bundled-data crossing:
`output_bank/metadata_in_hold_reg[17]/C` to
`output_bank/metadata_out_hold_reg[17]/D` (175 MHz to 100 MHz), zero logic levels,
1.146 ns data delay, -1.258 ns slack. It must be audited against actual ownership
and metadata stability, not dismissed or false-pathed merely because it is CDC.

The worst same-domain path still reaches
`owners[1].result_guard/active_private_reg/D`, now from
`output_bank/metadata_in_hold_reg[5]/C` through the live equality tree, selected
current framing fault and inverse completion control. Eight logic levels,
6.876 ns data delay, 5.366 ns routing (78.0%). The next path reaches inverse
commit. Phase selection no longer precedes the wide comparison on this path,
but the comparison/current-completion chain still exceeds the clock budget.

## Next gates

Treat same-domain timing and bundled-data CDC as separate work items. For the
logic path, investigate a private output validation boundary with an exact
descriptor/word lifetime and publication receipt; prove any added latency against
the real FFT return slot, final private write and replay handoff before routing.
Keep the current corruption tests and every immediate public fault veto. Do not
simply delay a fault or clear a public completion early.

For CDC, establish and test first-write-to-publication stability, synchronized
request-to-reader capture, actual ACK-to-next-write ordering and both reset
epochs. Then derive scoped implementation constraints from those proven
requirements and validate them with CDC/physical reports under real board
clocks. No CDC exception or new validation stage is implemented in this
checkpoint. Full receiver integration and hardware qualification remain open.

## Evidence and deployment scope

Prepared inventory:
`dc97c80ce1999e9a18053524c3dcd325d029705560c2425aef2e0fe05f20d1b7` (V3).
V1: `a9656c0346a5c3125fbe230b2ef3875e4feba94333721b7b912f06b1ed014b65`.
V2: `70140af367445b965a596ea53562145eb957fbd6410ce6de654c6a943c8039fa`.
RAM root: `/dev/shm/starlink-output-metadata.MB5fY8`.
Synthesis DCP:
`bfdfd17a2bbea030937148187b73a621e6bf65c044468f0c7876cde295c257a1`.
Routed DCP:
`ee65ba286ece8625b60af30490ee33960f28e3eb93be60ac78e759968d8afcb1`.
Numerical CSV:
`210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44`.
Parent inventory:
`d60c44681da7625f756b05315b626577a165eb29da9761d528e126508c9155f4`.
Pinned historical evidence dependency:
`d798f7d03becf9cc78a94e16987f0b10c8f31cfb643e8a1e4257c4e04e3cf7f2`.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
untouched. No radio, PPU/main or primary production HDL changes. OOC 100/175 MHz
results do not establish full receiver/board timing, continuous 750 Hz RX,
native calibration, sustained Ethernet/IIO or RF accuracy. Those remain gates
before reversible `.18` canary and `.17` PPU Ethernet-only deployment with pinned
rollback, 300-second scans, 120 ms valid dwells and blind host GLRT comparison.
`.17` remains outdoor LNB RX-only, not a bench transmitter.
