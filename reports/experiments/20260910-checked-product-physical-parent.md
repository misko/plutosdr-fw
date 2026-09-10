# Checked-product physical comparison: timing FAIL, lane held

The functionally accepted checked-product v2 candidate completed synthesis and
diagnostic routing with the unchanged P1 recipe. **It fails timing and is not
deployable.** Root independently audited the original route reports, checkpoint
hashes, clock constraints and terminal result; successful tool execution is not
a timing pass.

| Measurement | Checked product | Retained control |
|---|---:|---:|
| Worst setup slack | -8.324 ns | -2.697 ns |
| Total negative setup slack | -7913.583 ns | -981.622 ns |
| Failing setup endpoints | 2309 | 848 |
| Worst hold slack | +0.039 ns | +0.037 ns |
| LUT / FF | 2592 / 5103 | 2333 / 4764 |
| DSP / RAMB18 | 21 / 15 | 21 / 15 |

Both are isolated 100/175 MHz diagnostics, not full receiver qualification.
The retained result is preferable within this pair, not a claim that it beats
every previous candidate: the older P1 route was -1.492 ns.

## Verified execution and critical path

Root synthesis63808 completed exit0 in119.15s with2507LUT5099FF21DSP15RAMB18
and no black boxes. All25 prepared and45 live source pins remained unchanged.
The accepted actual vendor FFT run58385 and its unchanged runtime source remain
the functional prerequisites; the drain correction changed only the bench.

Root route91981 completed exit0 in67.59s. All7597 routable nets are fully routed
with zero routing errors. Hold and pulse-width checks have no failing endpoints.
The source checkpoint and original/copied runner hashes remain unchanged.
The independent root audit reproduces all numerical values above from raw reports.

The worst same-clock path is:

`expected_product_metadata[0] → reader identity/start validation → bank/reader
fault and lease logic → checked_product_bank.origin_valid/D`.

It crosses26 logic levels (six CARRY4 and20 LUTs), with13.941ns data delay:
4.034ns logic and9.907ns routing. Registered validation elsewhere did not remove
this remaining combinational dependency. This measured result does not support
promoting the checked-product candidate or combining it wholesale with retained
output ownership.

Same-clock setup/hold:100MHz +1.758/+0.102ns;175MHz -8.324/+0.039ns.
Cross-clock setup/hold:100→175 -0.504/+0.145ns;175→100 -1.426/+0.073ns.
The report also has an asynchronous control path group at -0.947ns.

The routed CDC report has **one critical finding**,139 warnings and17 information
entries. This differs from synthesis's13 critical findings; neither count is a
CDC qualification. The remaining critical path is slow_purge_seen to the first
slow_purge_fast stage. There are still114 unspecified input delays and124
unspecified output delays. Only the original100/175 probe clocks are present;
no false-path, multicycle or clock-group exception was added. Board-derived
clocking, reset and real AD9361 RX timing remain unqualified.

## Next implementation boundary

Hold the checked lane, preserving its successful functional test and failed
physical result. Continue the retained candidate with a separately testable,
default-off fault-summary view: metadata-independent offered input events may
be used only to shorten redundant fault evaluation, never to certify actual
FFT input or publication. Original input current faults remain a direct veto.
Require known-input equivalence, explicit X/Z fail-closed behavior and tests
for simultaneous malformed input, ACK, publication, reset and raw events.
OR factoring alone is not a promised timing improvement; a new route is required.

Full15MS/s coarse from15/30/60, original-rate fine search, independent2.5MS/s IIO,
continuous buffering,120ms visits and300s blind comparison remain the objective.
No radio access, flash, PPU modification or production HDL gitlink promotion.

## Evidence

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

- `checked-synthesis-parent.q1cr3TZZ`: owner, source checks and synthesis audit.
- `checked-route-parent.3lJAqEWe`: original route owner/execution, raw reports,
  checkpoint and independent `audit.py`/`audit.json`.
- Synthesized DCP SHA256:
  `62ea84c5d09ac3e41b00157d8761a1834d11540c28566196148b8e74bb70ba52`.
- Routed DCP SHA256:
  `0707432cca72c25e71ba35d7fa6968a5cbd413449ca40c425506f9ab56338aaa`.
- Unchanged route runner SHA256:
  `0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.

Actual and synthesis packages are pushed and exact remote heads verified in
the checked DNM lane: FW1e83f661a96f4b0e7ac4766a21e9de8b98140f92,
HDL2fe70f8425b3eb7f0715625053bb1337be402a11. The lane's committed Git-object
checks cover308 payloads; route packaging follows separately.
