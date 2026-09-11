# Exact guard-facing fault summary — DO NOT MERGE

This independent candidate starts from private-capture FW `fcc3dc202` / HDL
`c25126a2e`, not either subsequent staged-final or private-ordinal regression.
FW and HDL branch: `codex/starlink-rx-only-do-not-merge-fault-summary`.
It is an actual FFT/buffer subsystem experiment, not a deployed receiver.

## Change and proof

Only the top-level external-fault binding of the two result guards changes.
When enabled and the current input fault is a known binary value, it uses the
existing offered-input aggregate. Otherwise it uses the original aggregate.
No register latency, checker/cutover state, public publication veto, bank ACK,
data path or FFT configuration changes. Feature-disabled behavior is original.

With input fault zero, offered input strobes equal certified strobes, making
the parallel cutover expressions equal. With input fault one, that fault
absorbs any cutover difference. X/Z input faults select the original expression
to retain exact four-state diagnostics rather than forcing a binary fault.

Tests extract the actual top expressions and compile the pinned real input
checker and cutover, not approximations. A complete inverse verifies no other
top change; seven parallel cutover formulas match after literal renaming.
The real combinational campaign covers 524,288 cases: 380,279 zero, 4,193 one,
139,816 unknown input faults; 972 masked differences and 15,218 fallback cases.
A separate 256-case scalar table checks conditional equivalence and disabled
behavior. Three unsafe aliases are rejected. Five unit tests pass in 3.30 s.

## Actual FFT and regression

Actual generated-FFT simulation passes in 111.49 s. All 64,512 records match
the pinned numerical reference, with CSV byte-identical to private capture.
Service remains 3659/3659/4927/11727/3659/3659 clocks; the deliberately stalled
reader context is excluded from the unchanged 5215-cycle service bound.
All prior reset/fault/ownership tests pass. Each result guard's full fault
accumulator is checked against the original expression for 259,384 cycles.
Five new cases cover bad mid-input identity, bad final identity plus early
status (actual cutover differs but input fault absorbs it), X and Z fault
fallback, and an independent early-output fault. None publishes or releases.

397 combined tests pass in 53.88 s, including ten evidence-parser controls.
Source/lint preflight passes two tests. The first combined test invocation
omitted the task-specific TMPDIR and Icarus preprocessing failed with
`No input files given` (153 failed, 14 errors, 230 passed). The identical
sources/tests pass with an explicit private temporary directory. Both XMLs
and logs are retained; the first invocation is not counted as verification.

## Route: regression, not promoted

Synthesis passes in 97.03 s. The first route invocation supplied relative
parent paths and was rejected by the existing absolute-path gate before
routing. The corrected absolute-path invocation routes the same checkpoint
in 45.97 s. Both attempts are preserved, with no source or recipe change.
Independent report/checkpoint/source audit passes, but timing does not.

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private-capture reference | -1.969 ns | -813.676 ns | 914 |
| Exact guard fault summary | -2.566 ns | -921.237 ns | 958 |

958 / 13780 setup endpoints fail. Hold +0.058 ns, pulse +1.830 ns; 8350 nets
fully routed, zero routing errors. Resources: 2744 LUT, 5658 FF, 21 DSP,
15 RAMB18, zero RAMB36. Diagnostic clocks remain 100/175 MHz. Board I/O delays
remain unqualified (114 inputs / 124 outputs); five critical CDC findings and
208 CDC warnings remain. No physical signoff is claimed.

The worst path is publication phase -> bank metadata mux/comparison -> guard
fault qualification -> completion acceptance -> `final_data_reg[0]/CE` in the
mailbox controller. It has ten logic levels, 7.991 ns data delay, including
6.157 ns routing. Its final enable has fanout 71. Smaller equivalent logic
did not produce better physical timing; retain the private-capture reference.

## Next gate

Inspect the complete final-data/tag capture and bank-metadata boundary together
on the better reference. Separate private payload capture/hold from small
publication authorization, with local registered ownership. Keep current fault
vetoes, exact final-word identity, reset cancellation and real reader ACK before
reuse. Prove those contracts against the existing adapter and actual FFT before
routing another candidate. Do not compose this regression merely because it
passed functional tests; do not relax clocks or waive the failing paths.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required and have not been removed. Full receiver integration/timing/CDC,
sustained capture, actual 60 MS/s RX calibration and Ethernet/IIO verification
remain before reversible `.18` canary and `.17` PPU Ethernet-only deployment.
Final verification remains a 300-second scan with 120 ms valid dwells and blind
host GLRT comparison. No radio, PPU, main or primary production HDL was changed.

## Evidence identity

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Prepared/actual/synthesis: `staged-guardfault-{prepared,actual,synth}-v1`.
Successful route: `staged-guardfault-route-v2`; rejected launch: route-v1.
Regression success: `staged-guardfault-regression-v2`; environment failure: v1.

Inventory: `5cec30567067daef19715fd16b4b50f8c56569b917063df9067bc6e49d98477b`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Synthesis DCP: `04e1391133570b09f0d40767701fcda7686173e78c849c437548cfa0dc8df2d1`.
Routed DCP: `19a0d27f9f3d17f83b9893259b7fc10cf1198f68ac7a47e06d8dfe59453a5d79`.
Runtime and copied-source hashes are unchanged before/after all vendor runs.
