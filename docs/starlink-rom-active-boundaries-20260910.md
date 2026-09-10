# ROM read-ahead: directed occupied-state boundary verification

Independent read-only review of FWd6ca47ef/HDL1dd76119 found no functional defect
in the retained-word/selector recurrence, but identified missing explicit
evidence for occupied-output X/Z-ready and both occupied flush states. The
20,000-cycle unconstrained stream did not prove those healthy states were reached.

This increment changes only the standalone bench and its tests. Runtime RTL,
original-source inverse recipe, unconditional old/default/candidate comparison,
all numerical words and existing assertions remain unchanged.

Each of twelve width2/18/24 × balanced0/1 × scratch0/1 configurations now proves:

- Start with a healthy occupied output, coefficient0 and selector1. Apply readyX
  and readyZ separately with input_valid1; require input_accept and stage-readyX,
  coefficient retention, no fault and no bin advancement. Then require known
  stall, known drain and healthy coefficient1 refill.
- Flush a healthy occupied output with selector0 and selector1 separately.
  Require cleared visible coefficient/output-valid/selector and healthy refill.

Every directed case has checked preconditions and mandatory completion counters.
Four negative tests remove one case at a time and must fail coverage. The original
unconditional comparison still runs before/after rising edges and at falling
observations; no field, validity or fault mask was added.

Final original3382 terminal0: **31 PASS /6.91s**, retained at
`/tmp/starlink-rom-active-boundaries-final.59q91XWV`. Ruff and both Git diff checks
pass. This is the changed standalone suite only, not a repeat of the earlier149
combined regressions and not actual FFT, synthesis, timing or RF qualification.

Preserved attempts:

- Original70802 exit1:25 PASS/2 FAIL,4.99s,
  `/tmp/starlink-rom-active-boundaries.mp19eT1S`. New internal selector monitors
  referenced a generate scope absent for illegal X/Z option values, preventing
  the negative tests from reaching the existing time-zero RTL parameter fatal.
- Original82139 exit0:27 PASS/4.98s,
  `/tmp/starlink-rom-active-boundaries-v2.8iNgvMr5`. Only illegal-option test
  fixtures replace that nonexistent monitor reference with X. They still require
  the original parameter diagnostic at time zero. Valid-option functional runs
  retain every real selector monitor. No RTL change was needed.
- Final adds the four mandatory-case negative tests above. No runtime or oracle
  changes occurred between these attempts.

Portable evidence `reports/experiments/20260910-rom-active-boundaries-v1.tgz`
contains581 source/artifact members plus embedded receipt, all three attempts,
compiler/executable/log/XML artifacts and final source. Archive SHA256
`9b49dbaa0ad62853ba7db47ae78195360509ecda2dc4cd5eb67e459c29c5508d`,
2,308,306 bytes;28 redundant pytest-current symlinks are explicitly listed as
excluded. Original raw directories are retained. Existing collector is unchanged.

Next gate remains actual forward-joiner/bank integration preserving raw
coefficient comparisons on current faults, final retirement veto, held-final
stall/reset/ownership, then physical RAM-enable/mux/DSP path measurement. This
standalone evidence does not authorize a wholesale source-snapshot promotion.
