# Inverse-output identity stage — 2026-09-11

Branch `codex/starlink-rx-only-do-not-merge-output-identity-stage`.
DO NOT MERGE firmware/HDL into main. **Timing still fails; do not deploy.**

## Implemented boundary

Start from the buffered forward reference, not the regressed local-completion
variant. All 24 parent runtime modules remain unchanged. Add a derived top and
output-mailbox variant; reuse the existing product identity stage unchanged.

The new stage captures each word with its identity and registers the identity
comparison. The mailbox checks that held certificate, position and LAST at the
actual write/publication edge. Original RAM, ownership toggles, reader ACK and
reset receipts remain intact. Identity uses the bank's first-word metadata,
including write-through when word zero retires as word one is captured. The
existing 70-bit stage interface is padded with zeros for the 37-bit metadata.

Only nonfinal inverse words enter the private live stream. The sole final word
comes through retained replay with its descriptor. Replay acknowledgment waits
for the held validated final word to reach the actual bank. A final slot cannot
refill on publication. Current fault vetoes remain on actual publication; the
pipeline intentionally changes private-offer checking/storage latency. This is
not identical raw-offer fault latency to the unstaged implementation.

## Functional evidence

**1,200 distinct tests pass:** 1,171 regression (1,159 inherited + 12 new
source/component cases) and 29 evidence/mutation tests. The separate 12-test
component run is a subset, not another 12. Inherited tests exercise reference
components/topology, not every old fault case on this new integrated top.

Component cases cover stalled output, bad middle/final metadata, incorrect
ordinal/LAST, 0/X/Z final certificates, abort/reset with an unpublished held
final, and fresh recovery. Four mutants are rejected: early publication,
ignored certificate, missing first-word write-through, and dropping a held
unpublished final. Evidence tests reject missing/duplicate/incomplete witnesses.

Both actual generated FFT campaigns pass all **64,512 words across seven
streams** against the frozen original numerical reference. Six contexts include
high-bit timestamps and stalled output. Service is **4,178 clocks**, one above
the buffered parent: 23.874 us at 175 MHz, below the 5,215-clock / 29.8 us budget.
This is not continuous native RX proof. The CSV hash changes with event ordering;
every numerical field is independently matched by stream/job/position.

| Actual comparison | Main | Auxiliary |
|---|---:|---:|
| Fast cycles observed | 88,545 | 324,016 |
| Actual bank words checked | 9,216 | 25,800 |
| Final writes checked | 18 | 47 |
| First-word simultaneous refills | 18 | 52 |

At every actual write, the observer reconstructs original framing from the held
word and actual bank header and compares it with the certificate path. It also
checks that replay acknowledgment cannot precede a validated final RAM write
and that unqualified live finals never enter the stage. Counts include private
writes in cancelled work, not just publications.

Auxiliary tests retain six forward/raw/replay faults, eight reset boundaries
and two status/backpressure delays. Nine new actual cases corrupt live/replay
metadata, held ordinal/LAST, inject status on the would-be publication edge,
and assert either reset before final publication or after publication with the
reader stopped. Every case fences cancelled outputs and recovers with 512
correct fresh words and one real reader release.

## Routed evidence: improvement, not closure

Same Vivado 2022.2, xc7z010clg400-1, 100/175 MHz OOC recipe and FFT IP; no timing
exceptions or relaxed clock. Actual source/numerical/fault evidence is re-audited
before routing the exact synthesized checkpoint.

| Metric | Buffered reference | Output identity stage |
|---|---:|---:|
| WNS | -1.559 ns | **-1.406 ns** |
| TNS | -348.591 ns | **-324.725 ns** |
| Failing setup endpoints | 742 / 14,202 | **763 / 14,471** |
| LUT | 2,735 | 2,712 |
| FF | 5,800 | 5,891 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

WNS/TNS improve, but the failing endpoint count rises slightly. All 8,554 nets
route without errors. Hold +0.034 ns and pulse +1.830 ns, zero failures. There
remain 114 unqualified input and 124 unqualified output ports.

CDC reports nine CDC-3 and 210 CDC-15 warnings (parent: 208). The extra entries
are replicated source-bank metadata receivers at bits 20 and 54; descriptor
payload bit 36 also uses a replicated source. This is not a waiver: all physical
replicas need eventual bundled-data ownership/constraint qualification. No
critical CDC-10 is reported. Full board/CDC signoff remains open.

Worst path: `owners[0].result_guard/fault_reasons_reg[2]/C` to `fast_fault_reg/D`,
nine LUT levels, 6.978 ns data delay, 76.583% routing. It traverses guard/control
logic and the output ledger before returning to the global fault register.

Next investigate cascading fault propagation. The forward return bank and new
output stage feed registered guard faults into private abort inputs, then
report derived faults through global control. Test a consistently registered
global abort for private work while retaining local reports and same-edge
current publication vetoes. Any additional private work on a newly faulted edge
must be proved unable to publish, ACK/reuse, or survive reset. Preserve this
candidate; rerun actual arithmetic, cancellation, fault-source checks and route.
Neither Boolean equivalence nor timing improvement may be assumed.

## Identities and remaining release gates

Evidence root: `/dev/shm/starlink-output-identity.zBgwcqOX`.

- Main inventory: `3e808c99ca9f3b68c39d69ff1313af824cdc01b0997958b80e4cd5f88818eeb1`.
- Auxiliary inventory: `93fc1df123749381c5add4aeccde5685f4ee8ecd8e6f69a26a47337e5ffcc8ce`.
- Main/auxiliary CSV: `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
- Synthesized DCP: `74b2be9c5156dfcae9352bd7752885a14b1d2d3d4ee4c67c882147f8ab34489f`.
- Routed DCP: `83838aaa913f86bf32487f734042eedf8e6b005f77e8b2db7e8674006a88a36e`.

Use `output_identity_experiment.py`, `output_identity_boundaries.py`,
`route_output_identity.py` and `audit_staged_fft_route.py` for the pinned stages.
Sources, actual CSV/logs, generated wrappers, synthesis/route DCPs, reports and
tests are retained in a read-back verified archive.

No radio or PPU access; no main-branch change. `.14`, `.20`, `.21` stay excluded.
Native 60 MS/s fine and independent 2.5 MS/s inspection sources are unchanged.
Full receiver timing/CDC/reset with real clocks, calibration, continuous RX and
sustained Ethernet/IIO remain open before reversible `.18` canary and `.17`
Ethernet/PPU deployment. This subsystem result does not complete those gates.
