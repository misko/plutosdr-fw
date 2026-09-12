# Phase-specific quiet publication — DO NOT MERGE

**Functional checks pass; routed timing improves but remains unclosed. Not deployable.**

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-phase-publication`.
Parent is the guard-pulse experiment, FW d4cc1ace6623cbd538dc5157343182270000d0af,
HDL 7dfec6bb118bb42c4bb2522327bda893bf4be7a4. All 45 parent runtime files
remain byte-identical; one selectable top brings the inventory to 46.
No PRIMARY promotion, main merge, PPU change or radio access.

## Exact change and proof

Quiet output publication already requires !preparing; preflight events are
phase-gated to zero when preparing is false. Only this quiet-publication fault
view drops preparation_fault_now. Original complete fault predicates,
acquisition/preflight checks, sticky diagnostics, all other current vetoes,
nonquiet/invalid configuration branches, storage and datapath remain unchanged.
This is logic factoring, not a delayed permission or timing exception.

An independent observer compares the actual acceptance against the original
complete predicate before and after every fast edge. It separately compares
the unforced contextual full and reduced expressions, even during faults.
The inherited intentional force of output_replay_accept low is mirrored only
to its original acceptance oracle, never to the unforced expression comparison.
All original fault targets, assertions and deadlines are retained.

Tests include exact source delta, missing/duplicate-delta rejection,
262,144 four-state phase combinations and 1,048,576 combinations using the
actual full/reduced RTL fault expressions with an independently varied fault.
Mutants removing phase context or another fault are rejected. Missing, duplicate,
weak and fault-vacuous witnesses are rejected; conditional/adjacent mirrored
force/release layouts compile.

## Verified execution

- **2,411 scoped tests pass**, 170.818 s: 135 inherited modules plus one new
  21-case module. This is not the whole repository suite.
- Healthy actual generated FFT/buffers: **64,512 exact numerical words**,
  **4,178 clocks**, 64.147 s. No added service latency.
- Healthy publication observer: 177,346 comparisons, 18 accepts.
- **All 92 inherited actual FFT fault/reset/stall cases pass**, 370.027 s.
- Fault campaign publication observer: **1,851,082 comparisons**, 118 accepts,
  five active-preflight observations, three full/reduced fault differences.
  Contextual acceptance remains exact in those differing cases.
- Both original guards match 1,851,082 comparisons each; forward/inverse
  completion pulses remain 171/129. All 316 job admissions still match the
  original certificate across 1,841,886 comparisons.
- Healthy/synthesis and auxiliary preparations have the same 46 runtime files.

CSV SHA256: `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

These are FFT/buffer simulations, not continuous ADC, DMA/IIO, RF calibration
or real reception verification.

## Routed measurements

Same frozen 100/175 MHz actual-FFT OOC recipe, no exceptions.

| Metric | Guard-pulse parent | Phase publication |
| --- | ---: | ---: |
| Worst setup | -1.236 ns | -1.203 ns |
| Same-175 MHz worst | -0.998 ns | -0.881 ns |
| Total negative slack | -299.750 ns | -234.465 ns |
| Failing endpoints | 764 | 655 |
| LUT / FF | 2,747 / 5,911 | 2,769 / 5,915 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |
| Output publication | -0.998 ns | -0.623 ns |
| Product publication | -0.772 ns | -0.881 ns |
| Guard active / ACK | -0.549 / -0.580 ns | -0.127 / -0.287 ns |
| Guard commit | -0.533 ns | -0.099 ns |
| Admission valid / consumed | -0.471 / -0.523 ns | +0.173 / +0.124 ns |
| Admission good D / CE | -0.684 / +0.506 ns | -0.540 / -0.244 ns |

Some paths regress; this is not universal improvement. All 8,574 nets route
with zero routing errors; hold +0.048 ns and pulse +1.830 ns. There are still
114 unqualified inputs and 124 outputs. Overall worst is a held metadata
175-to-100 MHz crossing, not waived. Same-domain timing independently fails.

New same-175 worst: engine metadata bit 24 through handoff identity equality,
handoff_fault_now, current product authorization and the product request toggle.
Seven levels, 6.540 ns data delay, 76.8% routing. Next path is fast_fault through
forward-buffer state enables (-0.810 ns). Output publication no longer contains
the removed preflight term but still fails at -0.623 ns.

The initial route_starlink_staged_fft invocation was rejected before routing:
that older harness expects a different receipt contract. Its failure log is
retained. The matching phase probe validates source-matched healthy FFT,
synthesis, component XML and DCP, then uses the identical frozen route Tcl.
The complete fault campaign is independently required and re-audited by the
archive recorder, not inferred from this early physical probe.

## Next work and deployment gates

Keep this measured candidate and the parent comparison. Inspect the product
publication handoff dependency: the handoff checker concerns an already
reader-owned bank, while final publication needs writer ownership. Any
phase/ownership simplification must first prove that the corresponding states
cannot overlap under supported reset, stall and fault behavior. Preserve the
complete handoff check for reader ACK, quarantine and diagnostics. Do not simply
remove the comparator or suppress existing fault assertions.

If that separation cannot be proved, introduce an explicit registered
ownership/validation boundary with a measured latency and sustained-throughput
budget. Also address forward-buffer fault/state-enable paths; one improved
endpoint does not establish closure.

Full receiver route at actual board clocks, CDC/reset/I/O qualification,
sustained native and inspection DMA/Ethernet, actual 60 MS/s RX calibration,
and receiver continuity remain open. Preserve native 60 MS/s fine search and
independent 2.5 MS/s CI16 IIO inspection, causal acquisition/CFO/fine, eight
high/low targets with 120 ms valid dwell over 300 s, and independent host GLRT.

Deployment only after qualification:
1. Serial-verified .18 canary: 1040007c4a94000211000b009186843ef2.
2. Pinned reversible Ethernet PPU deployment to outdoor .17:
   104000bac4950008230026001b440a003a, powered LNB on RX1, no TX.
3. Real reception/replay comparison and clean stop/restart.

.14/.20/.21 remain excluded. PRIMARY HDL remains
0b4bf2f0fd8c58c79852266b07f9e95770f75f36. No deployment date is established.

## Reproducibility

Artifacts: `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/phase-publication-artifacts.OREllUKA`.

Main/synthesis pin:
`cb49e4c50c9638abc3537b7ba956f45fa8515deb09562a730769ff1d0841a9f2`.
Auxiliary pin:
`6bbbc5828510db161b93d2699592647fc06554a52ea914d9c009cadce883ee8f`.
Synthesis DCP:
`ad28c78131cfa863c5386e879a760e4c6ed7562be5c18f995f949477553d7762`.
Routed DCP:
`2e0a8438ea7eb610071f44fcd05d9491cb754e846a4631150036a8d88c6cd03d`.

Archive: `reports/evidence/20260912-phase-publication-evidence.tgz`,
8,863,631 bytes, 424 verified members.
SHA256: `aa12e4e288ba8a9023892a9942dae997df69a17a8b95a9194a36abb018c3bfbb`.
Archive includes frozen sources, witnesses, numerical data, DCPs, physical
reports, curated regression/component evidence and rejected runner launch log.

