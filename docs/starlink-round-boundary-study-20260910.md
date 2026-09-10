# Boundary rounding: numerical equivalence and isolated physical measurement

This is a default-off arithmetic candidate in the separate
`codex/starlink-rx-only-do-not-merge-round-boundary` FW/HDL worktree. It is NOT
promoted into the bank/receiver, not a timing-qualified bitstream and not
flashable. No radio, PPU or main-branch change occurred.

Base FW543868b6f / HDLb49553c1. Tested runtime SHA256:
`4f9046d0efc395d68caa9b63911fcf5c18ab335b1f2707ad19d3794e0cc2329b`.
Initial frozen implementation FWcbea04574 / HDL4c3d886a includes the physical
runner. Later test-only hardening does not change that runtime or runner.

## Exact arithmetic change

`BOUNDARY_ROUND_SAT=0` retains the old function. With option1, a signed
`(2D+1)`-bit sum has an exactly `D+1`-bit floor quotient after shifting D.
Nearest-even increment is guard AND (sticky OR quotient parity). Rather than
adding to a wide sign extension and then comparing, the new function decides
clipping from quotient bits before the increment:

- Prefix01 means greater than MAX; prefix10 means below MIN.
- MAX plus an increment overflows positively.
- MIN-1 plus an increment is rescued to MIN, not clipped.
- Both boundary quotients have all low D-1 bits set.

Only the D-bit payload increment retains a carry chain. The entire original
sequential pipeline, valid/ready/metadata behavior, resets, flushes and overflow
pulse timing remain literal. A whole-file inverse restores the original module
byte-for-byte. No logical register, pipeline stage, DSP or RAM is added.

Qualification is for known binary arithmetic values. Four-state function
equivalence is not claimed: a known clipping quotient with unknown remainder
can produce a known clip where the old function produces X. Invalid X/Z input
bubbles are tested for non-contamination of subsequent valid outputs. Old
default width1 elaboration is preserved; option1 requires width>=2. Invalid
option values -1/2/X/Z fail closed.

## Numerical evidence and preserved attempts

The independent oracle uses arbitrary-precision sign-magnitude nearest-even
rounding, not the new quotient-prefix construction. The bench also compares
against a whole independently renamed module from b49553c1.

- Every signed sum pattern for widths2 through6.
- Widths8/12/16/24: clipping neighborhoods, bit boundaries, six remainder
  classes and16000 deterministic random full-width values each.
- Width18: all524288 quotient buckets at six remainder classes plus16000
  random values, totaling3161728 function comparisons.
- Each of ten widths runs6000 elastic pipeline clocks with random stalls,
  busy resets/flushes, saturating operands and exact old/new public outputs.
- Wrong tie, positive/negative boundary and missing-increment mutants fail.

Initial invocation:1 PASS/18 setup errors because the chosen pytest temporary
parent directory did not exist. No numerical simulation ran for those errors.
After creating the parent, v2 passed19 tests in11.21s. v3 added source freezes
and the three existing frozen product-evidence tests:22 PASS in11.56s. v4
preserved width1 and added hostile invalid X/Z bubbles and correct source
handshake bookkeeping:23 PASS in11.16s. All old run directories remain.

The subsequent v5 bench additionally accounts for accepted/emitted/discarded
tokens against occupancy on every edge and drains the final outstanding work.
All23 tests pass in11.74s. This is still standalone product evidence, not
actual FFT/bank concurrency.

## First paired physical trial

Original processes11212(option0) and30699(option1) both completed exit0; the
runner reports MEASURED, never a blanket timing PASS. No retry or constraint
change was made between choices. Outputs:
`build/round-boundary-route-{0,1}-v1`, with original outer logs/journals beside
them. Both freeze identical runtime and runner bytes and verify them afterward.

Flow: Vivado2022.2, xc7z010clg400-1, actual synthesized DATA_WIDTH18 checked at
ports, two threads, AreaOptimized_high/ExploreArea, place, phys_opt, route.
Both use5.714ns (nominal175MHz,175.009MHz after1ps rounding), input max/min
1.000/0.500ns, output max/min0.500/0ns, no timing exceptions. These are explicit
logical OOC budgets, NOT calibrated ADC or board delays.

| Routed metric | Original option0 | Boundary option1 |
|---|---:|---:|
| Overall setup WNS | -1.577ns | +0.207ns |
| Setup failing endpoints |38|0|
| Overall hold WHS | -0.646ns | -0.685ns |
| Hold failing endpoints |176|176|
| Overflow endpoint setup | -1.577ns | +2.229ns |
| Overflow data path |7.086ns|3.380ns|
| Overflow logic depth |8 CARRY4 +4 LUT|3 LUT, no carry|
| LUT / fabric FF |99 /352|62 /278|
| DSP / BRAM |4 /0|4 /0|
| Fully routed / routable nets |483 /483|398 /398|
| Routing errors |0|0|
| Methodology violations |38 setup warnings|0|

All check_timing categories are zero, but both reports explicitly say timing
constraints are NOT met because of hold failures. The worst new hold path is
input_block_start_index[24] to its product register, with0.500ns input delay
and1.656ns destination clock insertion. The new overall setup limiter is the
resetn input to metadata reset pins. These observations are not waivers and
do not prove all remaining holds are port-only.

The overflow carry-to-compare dependency is actually absent in the new routed
path. Fabric FF reduction reflects different mapping/physical optimization,
not deletion of logical state. DSP register placement needs explicit inventory
before claiming why those FFs disappeared. No standalone port model can
qualify the bank's BRAM-to-DSP operand path, raw fault fanout or full receiver.

Original DCP hashes:

| File | SHA256 |
|---|---|
| option0 optimized |236a28980f709d28565366b16454610d702f11c233900d6e15f87ee2be51d1f1|
| option0 routed |160a38a21b464ebfa029842a9c46bece0f6afd5cb471790ad62cca8a0f44dd72|
| option1 optimized |24aeb548743fdb57a9c6679a7317a959346f8a935878dd25fbeadd386bb301e1|
| option1 routed |769518d97ae7922a6cceaab0c263fefa1b0ffb642fda75abd61189fcc25491e0|

Next: preserve this A/B evidence, integrate only after independently reviewed
bank-level active fault/ownership tests, and measure the resulting bank and
complete receiver without changing clock/accuracy acceptance. The existing
full-bank175MHz -1.907ns failure remains the authoritative bank result.
