# Split product capacity: exact actual FFT behavior, improved failing route

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-split-product-capacity`.
FW `1d0cd4b03`, HDL `c0200466c`. DO NOT MERGE or deploy this candidate.
Parent FW `d499446693de5f26fc16bd6b0ac183ae156b74e7`, HDL
`44cf696a9d78701246e2d309b1cd1befd3eea216`.

## Implementation

Separate the private product stage's nonfinal capacity input from its
publication-qualified retirement input. Capacity comes directly from actual
bank ownership/READY and the existing fault fence, not predicted credit or a
delayed fault. LAST retains the original qualified retirement and cannot refill
on the same edge. Nonfinal capacity must equal actual retirement readiness;
the exact top-level caller guarantees this and actual-FFT monitors check it.

The specialized stage replaces the compiled stage, retaining 21 runtime modules
and adding no RTL state. Only its module name, new input and nonfinal READY term
change; top wiring changes only stage type and that input connection. The
original stage remains the independent component reference. This avoids adding
the more elaborate block-credit controller suggested as a possible alternative
in the parent report. All public framing/identity/fault/ownership gates remain.

## Verification and timing

- **631 distinct regression/evidence tests pass**: 622 regression plus nine new
  source-bound split-audit tests. Focused 17-test preflight and seven archive
  tests overlap. An initial test import error was corrected and its evidence
  retained; it was not an RTL failure.
- Component comparison checks 1374 before/after-edge observations, full-block
  refill, held LAST, bank stalls, four-state control combinations, faults and
  resets. Four unsafe mutations fail. Exact source inverses constrain the edit.
- Main actual FFT: 204.28 s; **64512 numerical records and complete CSV match**,
  unchanged 3662/3662/4929/11729/3662/3662 service clocks. The intentional reader
  stall remains excluded from the unchanged 5215-clock gate. New witness checks
  **500595 clocks / 50761 nonfinal transfers**, exact acceptance/retirement.
- Auxiliary actual FFT: 107.99 s; original six ACK, 12 forward receipt and 12
  product fault/reset cases pass, with fresh recovery. New witness checks
  **243356 clocks / 25001 nonfinal transfers**. Both actual runs and synthesis
  use the same pinned sources; routing rejects absent or altered new evidence.
- Synthesis 99.90 s; route 46.99 s, unchanged clocks/constraints/recipe.

| Routed measurement | Previous capacity edit | Split interface |
|---|---:|---:|
| Worst setup slack | -3.252 ns | **-1.938 ns** |
| Total negative slack | -2279.503 ns | **-541.200 ns** |
| Failing endpoints | 1330 | 981 |
| LUT / FF | 2804 / 5780 | 2777 / 5788 |

All 8450 nets route without errors. Hold +0.072 ns and pulse +1.830 ns pass.
21 DSPs, 15 RAMB18s, no RAMB36s. No RTL state was added, but implementation
produced eight additional flip-flops. **Setup still fails** and remains worse
than the older forward-receipt reference (-1.567 / -497.191 / 681). This is
progress over the immediate parent, not a new overall best or deployment pass.
114 inputs and 124 outputs remain unconstrained in this OOC diagnostic.

Worst path now runs from `output_control/phase_reg[0]/C` through output metadata
selection, output-bank equality/framing faults and inverse result control to
`owners[1].result_guard/active_private_reg/D`. 11 logic levels; 7.645 ns data
delay, 5.687 ns routing (74.4%). The next path reaches the inverse commit pulse.
Movement of the worst path does not prove every product-side path now passes.

## Next boundary and deployment

Investigate stable output descriptor/identity certification before replay-phase
selection reaches the wide output-bank metadata predicate and inverse completion
control. First establish descriptor lifetime, original mailbox behavior, first/
nonfinal/final corruption, replay edges, unread output, real ACK and both resets.
Retain immediate current-fault/framing vetoes and ownership; do not just assume
the metadata is constant or delay a fault. Repeat actual numerical/service and
corner-case campaigns before routing. Keep the better older physical baseline.
This next output-boundary change is not implemented in this checkpoint.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO remain untouched.
No radios, PPU/main or primary production HDL changes. Full receiver timing,
CDC/reset/board clocks, real 60 MS/s calibration and sustained Ethernet/IIO
remain before reversible `.18` canary, then `.17` PPU Ethernet-only deployment
with pinned rollback. Final verification remains 300-second scans, 120 ms valid
dwells and blind host GLRT. No continuous RX or RF accuracy claim here.

## Preserved evidence

[Archive](20260911-staged-splitcapacity-evidence.tgz),
[read-back receipt](20260911-staged-splitcapacity-evidence.json):
13976942 bytes, 5453 members; every archived member verified.
SHA256 `d798f7d03becf9cc78a94e16987f0b10c8f31cfb643e8a1e4257c4e04e3cf7f2`.
Prepared RTL/Tcl, actual numerical/fault logs, synthesis/routed checkpoints,
independent timing audit, tests/results and implementation notes are included.
Historical fixtures remain an explicit pinned parent-archive dependency.

Prepared inventory `d60c44681da7625f756b05315b626577a165eb29da9761d528e126508c9155f4`.
CSV `210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44`.
Synthesis `1d104ec7d70759ea2657c91269f7e2babc64abc03c8535db6b8b40e70a805e8d`.
Route `0d9c2db85313c132ea50b58056aa0bc89d9d9eda568acb2d0cd5536bc5b244e5`.
RAM work area `/dev/shm/starlink-split-capacity.URCQhd`; the archive is the
durable handoff, not RAM alone.
