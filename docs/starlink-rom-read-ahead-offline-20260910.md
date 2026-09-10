# ROM read-ahead with exact visible coefficient retention

Standalone prototype only: **149 tests passed in 27.76 seconds**, original
handle15568 terminal0. No actual FFT, synthesis, routing, full receiver or radio
execution has been performed for this candidate. Its timing benefit is unproven.

The previous control route fails on metadata/framing logic feeding coefficient
ROM clock enable. This prototype decouples the memory read from that current
validation, without changing any accepted sample, coefficient, output timing,
fault predicate or existing private control field. It is an additive module;
all canonical production modules and callers remain byte-identical.

## How the stored values overlap

The private memory register reads whenever the original `input_ready` is true.
The original nested acceptance/error conditions separately register a selector.
On a healthy acceptance, the selector exposes that cycle's synchronous lookup.
On every other cycle it exposes a retained last-visible word instead. When the
previous cycle exposed the memory register, the retained register captures its
old value on the same edge that may start another speculative read. Thus an
invalid read, a stall, or a malformed beat cannot change the visible word.

Reset/flush clears retained data and the selector; it need not reset speculative
memory data. All original metadata, ordering, completion, fault and output-valid
updates remain literal. The nested procedural `if(error) ... else` is preserved
even for X/Z inputs; this is exact legacy behavior, not improved sanitization.

At DATA_WIDTH18, the old36-bit memory output becomes a36-bit speculative output,
36-bit retained word and one selector: **37 additional logical state bits**,
plus a36-bit mux. Nominal latency and maximum acceptance rate are unchanged.
Whether these become fabric registers or BRAM output registers is unmeasured.
The new selector and ROM-output mux can themselves become critical paths; the
prototype must earn its place through physical evidence, not this circuit sketch.

## Executed evidence and limitations

The independent reference is the complete original kernel module read directly
from HDL597a8ab65ce9d4ee68b4ca0fe4a98ab48604beb7. A strict whole-source edit
recipe checks the additive module and unchanged canonical source. The bench
compares the original, default-off candidate, and enabled candidate before/after
clock edges, including every existing public output, visible raw coefficient,
history register and combinational predicate. There are no invalid-data masks.

Twelve configurations cover widths2/18/24, both balanced-identity settings and
both private-next-start settings. Each has one continuous512-acceptance block,
two additional healthy blocks with stalls/invalid speculative reads, all64
single-bit block-identity faults, two explicit accepted X/Z metadata cases,
20,000 deterministic unconstrained input cycles, flush and recovery. Every
healthy coefficient is also checked against the independently loaded memory.
The unconstrained cycles are not described as20,000 healthy transactions or
formal exhaustive proof. No analog timing or metastability model is present.

Nine semantic mutants reject, including missing retention, wrong mux branch,
missing acceptance-time memory read, wrong address, reset corruption, changed
four-state error handling, output-valid removal and sticky-fault removal.
Invalid and literal X/Z option values fail at time zero. The legacy regression
adds unchanged payload, retirement, exact-control and CDC tests.

Retained attempts:

- Initial52746:25PASS/1FAIL,5.23s, `/tmp/starlink-rom-read-ahead-v1.jICW4m`.
  The failure was an incorrect test expectation: using `input_valid` instead
  of `input_ready` for a private read also includes every accepted lookup and
  passed the visible-state comparison. It is now a positive equivalence control,
  not falsely credited as a killed mutant. It is not the chosen timing cut:
  `input_valid` still carries the metadata dependency. Initial RTL/tests remain
  at HDL0fe2ca5f5 and FWcaf9f92fc; no runtime correction was needed.
- Second9500:27PASS,5.15s, `/tmp/starlink-rom-read-ahead-v2.8z9Fp4`.
  Two initial lint findings were fixed with explicit subprocess `check=False`.
- Final15568:149PASS,27.76s, `/tmp/starlink-rom-read-ahead-final.76jGL7`.
  Includes the added continuous block. Ruff and both Git diff checks pass.

Final tested HDL is1dd76119a681b5aa0b6d9f0d5f5d32f974e81342. Module SHA256:
`6fd319b0c6571f96b32a0b5b14e629721fed04ffc994a66a3e4dd07a952b799d`;
bench SHA256:
`e780033bc6fec57969ac2ccbb8ac936b6a71f617d89a1a7567fb4b776edc4e44`.

The archive `reports/experiments/20260910-rom-read-ahead-offline-v1.tgz`
contains2332 regular data/source members plus its embedded receipt. It retains
all three attempt logs, XML, generated source, compiler output and executables;
only pytest's48 redundant `*current` symlink aliases are excluded and listed.
Compressed size13,057,863 bytes; SHA256
`b0c2c425cecfe6fd26ea784a2096c4146198a43f638c3e3c0bba4595dc71b660`.
The archival collector is separate from the149-test scope and is not a test
qualification mechanism.

## Next gate

Independent circuit/test review, then a source-frozen joiner/bank integration
test preserving the old raw coefficient observations. Measure ROM inference,
extra registers, selector/mux paths and full timing under unchanged constraints.
Do not silently combine with arithmetic, CDC or descriptor-enable candidates.
Do not promote this module until it demonstrates a useful physical result and
passes the actual bank numerical/fault/ownership suite. The full15/30/60 native
fine search, independent2.5MS/s IIO pilot,120ms/eight-target/300s scanner and
`.18` then PPU Ethernet `.17` deployment remain the unchanged objective.
