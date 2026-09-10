# Retained control refactor: actual FFT PASS, physical gate next

Root's original process **61512 completed with exit 0 in 57.31 seconds**.
The combined private-descriptor-offer and closed-input-cutover candidate passes
the actual vendor FFT seven-context campaign. This is functional qualification
of the isolated candidate, not continuous 15/30/60 MS/s, routed timing, receiver
calibration, IIO, RF or deployment qualification.

## Independent evidence

Before launch, root fully reviewed the additive helper, witness, result checks,
bundle/CLI/runner and tests. Independent replay passed **73 tests in 18.06 s**
(original 12462, exit 0). All 97 source pins and 100 prepared file receipts
remained unchanged. The four runtime candidates are identical to the earlier
39-test qualified versions; the original 80-source reference stays frozen.

The actual campaign used Vivado 2022.2, the unchanged generated 512-point,
18-bit real-time block-floating FFT factory, two tool threads and the exact
original seven scenarios and eight vectors. Both options were read back as 1.
The three reference guards use the original unrestricted completed-input fault
expression. Original full output/state shadows were not masked.

After consuming the original process to terminal exit, root verified:

- Original and execution-copy source checks both return 0; the generated
  synthesis wrapper matches known SHA256
  `a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.
- An independent invocation of the frozen result CLI returns 0.
- Removing only the additive `candidate` result field leaves a result object
  exactly equal to the previous passing v5 actual result, including all seven
  contexts, aborts, service measurements and numerical counts.
- All **77,953 actual CSV rows are byte-identical** to v5, SHA256
  `07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
- 21 forward jobs and 19 inverse jobs yield 19 completed pairs; two forward
  jobs are interrupted at 64/65 accepted inputs and recover through resets.
- All 40 frame events occur eight fast cycles after admission. The original
  before/on/after physical-input witness remains 2/1/3.
- All 44 new receipts pass. Owners have 21/19 accepted jobs, 19/17 real ACKs,
  and 34719/60660 held-descriptor comparisons. The two missing inverse ACKs
  are the original intentional unread-bank reset cases, not lost results.
- Closed-predicate equality has 49,419 pre-edge and 49,419 post-edge checks,
  with 38 final-input checks and 19,456 original-authorized public-return uses.

Measured service is unchanged: 3645 fast cycles in ordinary contexts and 4912
in the deliberately parked-reader context. These conditional-source simulation
measurements do not establish continuous acquisition throughput.

## Next gate

Reuse the existing retained synthesis/routing recipe with exactly four frozen
runtime substitutions and both options enabled/read back. Preserve part,
factory, constraints and directives so the physical comparison is meaningful.
The latest prior route still fails at **WNS -4.068 ns**; this actual PASS does
not supersede it. Full receiver integration, 175 MHz clock integration,
CDC/reset/I/O closure and actual RX calibration remain open, followed by
continuous acquisition/native fine and independent 2.5 MS/s IIO verification.
The complete 120 ms-valid-visit/300 s scanner remains required before `.18`
canary testing and `.17` PPU Ethernet deployment.

No radio/PPU operation, main merge or production HDL gitlink change occurred.
The parallel checked-product candidate still has its separately preserved
[sampled-drain boundary failure](20260910-checked-actual-drain-boundary.md).

## Sources and recovery

Tested FW `77ffe5d82c2dc80a93cc6855da9c816aa56d5d53`,
HDL `3ecfd9f33a8b9cfe44dddc731c768325871f7936`.
Manifest SHA256:
`7a9b32f10241d22c3f5a6d3967ca9841e2646bb94d714f4935c05f5e8d03635e`.

Under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`:

- `retained-control-actual-prelaunch-v1`: frozen 97-source/100-file bundle.
- `retained-control-parent.vZVvViyX`: independent 73-test gate, source snapshot,
  XML, generated tests and unchanged-source audit.
- `retained-control-actual-parent.HbyLZ8I2`: one-shot owner, actual project,
  original/copied source verification, generated-IP receipts, tool logs,
  independent result CLI, and root raw/reference `audit.py` and `audit.json`.
