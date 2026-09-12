# Final product-publication experiment — rejected; DO NOT MERGE

**NO-GO. Incremental timing-closure work is aborted.** This is evidence closeout,
not authorization for another experiment. See [stop decision](../../PSS_DEPLOYMENT_GO_NO_GO.md).

Branch: `codex/starlink-rx-only-do-not-merge-product-publication`.
HDL checkpoint: `2e7b8cdcc`.
All 46 phase-publication parent runtime files are byte-identical; the selectable
new top makes 47. No bank, guard, FFT, arithmetic, RAM or clock RTL was changed.

## Runtime change

The product bank uses the same fast clock and common reset on both sides.
During writer readiness, reader output-valid must be zero. New publication
authorization explicitly requires known-zero reader-valid and uses the original
external-fault aggregate minus the reader handoff term. The complete original
authorization remains available for comparison. Full handoff equality and
faults remain on reader ACK, quarantine, diagnostics and other original users.

Raw authorization is now conservatively lower while reader-owned or unknown,
when the bank cannot accept a new writer publication. It is not claimed to be
identical at every idle/private point. The integrated observer compares the
original and new authorization whenever writer-ready, checks ownership
exclusion and separately rejects reader-owned/unknown publication. The existing
intentional forced authorization veto is mirrored to the original oracle;
original fault injection targets/assertions/deadlines are unchanged.

## Completed functional evidence

- **2,431 scoped tests pass**, 180.471 s, from 136 inherited modules plus one new
  20-case module. Not the entire repository suite.
- Actual generated FFT/buffers: 64,512 exact words, 4,178-clock service, 61.343 s.
- Healthy product observer: 177,346 comparisons, 18 publications, 19,116 reader
  observations and 540 conservatively different raw authorizations.
- **All 92 inherited FFT fault/reset/stall cases pass**, 368.253 s.
- Fault campaign: 1,851,082 product comparisons, 140 publications, 141,178 reader
  observations and 4,065 raw authorization differences, with exact writer
  authorization and no ownership overlap.
- Original output-publication, guards and admission observers also pass:
  118 output accepts; guard completion pulses 171/129; 316 original admissions.
- Same 47 runtime files in healthy, synthesis and auxiliary campaigns.

New component tests compare two unmodified actual bank modules, with original
and conservative authorization, for depth 4 and full depth 512. Each runs
16 complete frames, delayed final authorization, stalled reads, resets and
20,000 randomized four-state control cycles. Full-size case: 81,424 state/data
checks, 8,192 reads, 16 publications, 12,352 raw authorization differences.
This is simulation evidence, not an unbounded formal proof. Its testbench uses
the simulator default time unit; these checks establish event/state behavior,
not physical timing.

Source-derived authorization tests enumerate 65,536 four-state vectors:
16,384 known-idle writer comparisons and 49,152 reader/unknown vetoes.
Deliberately removed current-fault and reader-idle protections fail. Exact RTL
delta, evidence nonvacuity and force/release generator syntax are tested.

CSV SHA256:
`df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

## Failed physical gate

Unchanged frozen 100/175 MHz OOC route, no new exceptions:

| Metric | Parent | Final candidate |
| --- | ---: | ---: |
| WNS | -1.203 ns | -1.210 ns |
| Same-175 MHz setup | -0.881 ns | -1.067 ns |
| TNS | -234.465 ns | -344.221 ns |
| Failing endpoints | 655 | 880 |
| LUT / FF | 2,769 / 5,915 | 2,765 / 5,909 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

8,563 nets route, zero routing errors; hold +0.052 ns, pulse +1.830 ns.
Still 114 unqualified inputs and 124 outputs. Worst same-domain path is
engine metadata bit 56 through forward-buffer identity/fault and kernel-ready
control into kernel-ROM output_valid: seven levels, 6.774 ns delay, 78.4% routing.
Overall worst remains an unqualified held metadata crossing, not waived.
No extra endpoint probes or timing attempts were launched after the stop decision.

## Final disposition

No PRIMARY promotion, main merge, PPU change or radio access. No firmware flash.
.18 bench deployment and .17 outdoor deployment were **not reached**.
Native 60 MS/s sustained acquisition/fine search, independent 2.5 MS/s IIO,
full-receiver timing/CDC/reset/I/O, actual calibration, DMA/Ethernet continuity
and RF/replay comparison remain unqualified by this experiment.

The implement/test/deploy/verify objective is not achieved. Further development
requires explicit approval of a materially different approach with a fixed
deadline and the unchanged end-to-end release gates. There is no automatic next
timing variant and no current deployment ETA.

## Evidence

Artifact directory: `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/product-publication-artifacts.wq8KFULp`.
Main/synthesis pin:
`8322a02ba1223fe0de019cbf7aabc38e53af2c40ec9a1ec3926461a21089ebb3`.
Auxiliary pin:
`9979fb94c7407c35843eb5cd1cf0394c0e2eae108c5c7c8ae95a727e57d514a9`.
Synth DCP:
`bf84246cce8ec12307bb312a3ed900fdda5434ef7eb00ab16662c2e459dfd32f`.
Routed DCP:
`259a284f5761f8ca527bea1ae888bd429b5015e5ea58032e77e4ec08b436cc08`.

Archive: `reports/evidence/20260912-product-publication-evidence.tgz`,
8,827,702 bytes, 414 individually verified members.
SHA256: `8fd70b83c3bada6b9a22bfa59b728ab517ef44e9d53120d835c6ef22bd7b0a36`.
Frozen sources, simulations, numerical data, synthesized/routed DCPs, component/
regression evidence and the stop decision are included. Archive readback checks
member payload hashes, inventory, gzip CRC and unchanged source files.
