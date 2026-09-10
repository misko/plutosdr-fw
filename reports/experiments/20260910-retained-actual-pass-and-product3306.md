# Retained-output actual FFT PASS; independent checked-product integration PASS

The retained-output implementation now passes its seven-context actual vendor
FFT simulation. The parallel checked-product implementation passes independent
full controller integration regression. Neither result establishes FPGA routing,
continuous receiver capacity, 60 MS/s calibration, IIO operation or deployment.

## Retained-output: independently qualified actual simulation

Frozen FW `e1fa85a290e60c40bc16cc13608f48f1239e7ab2`, HDL
`28a822025a3ba5e47608b8875ff252baf73e8f42`.
External v5 bundle SHA:
`c3936f7e8552d7d377ca1e6fc5ba220d0667b68d00a24e24f524de33e75cbae8`.

Parent18820 exits0: **251 tests PASS in46.48s**, 80 source pins unchanged.
Compared with the prior logging-only preparation: 70 old files unchanged,
seven changed, three added. The change corrects the testbench's erroneous
first-input frame assumption; runtime, FFT factory, numerical vectors, clock
settings, detailed guards and service limits are unchanged. A strict complete
inverse reconstructs the old witness, expanded bench and result parser.

Each of40 jobs now requires its own admitted/configured reset epoch, at least
one physically accepted input, exactly one sampled one-cycle frame event,
known-zero closure, and frame strictly before the first raw output. Receipts
join frame identity and before/on/after input counts to numerical CSV rows.
Reset release is uniquely tied to admission+2 and configuration to admission+3.
The production verifier cannot accept a legacy log without frame receipts.
Directed script tests exercise first-input, idle-gap and later frame events;
these are checker tests, not fitted vendor-delay expectations.

Parent13931 actual vendor invocation exits0 in56.16s, without timeout. Its
prelaunch audit joins all80 tested sources, checks the complete old-bench
inverse, and verifies unchanged compiled runtime, profile and eight vectors.
Both post-run source-copy checks exit0; generated FFT wrapper is unchanged.
The terminal owner receipt and full simulator output accompany results.json;
the parser's standalone result is explicitly not execution proof by itself.

Actual coverage:

- Seven contexts: normal, periodic output readiness, parked consumer, ACK
  during forward output, held final prefetch, and both overlap-reset directions.
- 21 forward and19 inverse admissions, 38 complete jobs /19 complete pairs;
  two forward jobs aborted after64 and65 inputs, with fresh recovery checked.
- 40 frame events, 38 status events, 19,585 physical input words and19,456
  raw output words; 1,024 old unread output words intentionally discarded.
- 77,953 numerical CSV rows. Independent full-file SHA equals the frozen
  scripted reference exactly:
  `07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
  This covers all logged payloads and clock coordinates, not selected peaks.
- All40 observed frame events occur at admission+8 with before=2/on=1/after=3.
  These are measurements, not a newly imposed universal event-latency rule.
- Measured service:3645 fast clocks normally,4912 for the parked consumer,
  within the unchanged5215 cap. Eligible next-forward dispatch remains8 clocks.
- Unconditional shadow receipts:179446 input pre and179446 input post checks,
  89465 arithmetic and179446 retirement checks.

Clock configuration remains approximately175 MHz fast /100 MHz slow. The
service measurements are conditional on the supplied source windows and these
seven scenarios; they do not prove continuous acquisition or lower-clock use.
Prior compilation, startup, logger and frame-assumption failures remain intact.
The first independent post-audit used incorrect logical CSV stream labels and
stopped before data checks; only that audit inventory was corrected. Its failure
note is retained; actual data and the qualified checker were never changed.

## Parallel checked-product controller integration

Frozen FW `ed1d85745779e2ac9d324efdb6ed2618569edd76`, HDL
`65cff8a983b2fd8489634939c363f2de230fc512`.
Parent14525 exits0: **3306 tests PASS in143.69s**, all179 pins unchanged;
all154 previously qualified source pins remain byte-identical. This includes
554 top-integration tests plus the unchanged2752 primitive/interface tests.

Independent post-audit verifies104 compiled manifests /1404 file receipts.
The integrated graph contains8676 nodes, including172 LS nodes, and no cycle.
Five complete inverse patches preserve the reviewed original implementations.
Both reset directions check512 independently computed fresh complex products;
all512 expected products differ from the old epoch's products. The parent
uses a separate magnitude/remainder ties-to-even integer implementation.

This test uses an explicitly identified identity/control actor, NOT an FFT.
The estimate of558 additional logical state bits and eight additional actor
clocks is not mapped-area or actual-FFT performance evidence. The inherited
source-bank handshake accepts only two fresh words while the fast clock is
paused after reset, then requires the producer to hold the next word until
ready returns. The rejected full-prefill assumption remains an executed
negative test. Continuous ADC capture needs upstream retention or explicit
gap/expiry behavior; no uninterrupted-capture claim is made.

## Next release gates and scope

1. Prepare/run retained-output synthesis and routing with the same comparable
   175/100 MHz constraints, all cross-domain paths reported, no clock/fault
   waiver. The last physical P1 result remains WNS−1.492ns, not a passing build.
2. Independently qualify the parallel checked-product implementation with the
   actual FFT before making any physical-performance comparison.
3. Integrate the selected passing implementation into the full receiver;
   prove causal acquisition/fine scheduling, continuous data handling, CDC,
   resets and board-I/O timing. Then perform actual60 MS/s RX calibration.
4. Verify independent2.5 MS/s CI16 IIO evidence and the eight-target scanner
   with120ms valid visits over300s; compare blind host GLRT with FPGA results.
5. Reversible `.18` canary, then `.17` PPU Ethernet deployment and RF verification.

No radio, PPU, production HDL gitlink, synthesis or routing operation occurred
in this increment. Firmware development stays on DO-NOT-MERGE branches.

## Portable evidence

All archived regular files were read back and compared byte-for-byte with
their originals. Corresponding `.members.json` files enumerate SHA256, sizes
and exclusions (cache files and symbolic links); original recovery data remains.

- `20260910-checked-product-top-parent.tgz`:
  `089a068dd7936c6b6fc21b7ea91cf2f624ee1ff818f8eda4b4253485f91420a6`.
- `20260910-retained-frame-parent.tgz.part-00` and `.part-01`: concatenate in
  that order to obtain the43 MiB archive, SHA
  `73ebece958895ce408a026bfe08409952fec603cc20bddc4a44d2d0000eb6335`.
  Exact part sizes/hashes are in `20260910-retained-frame-parent.parts.json`.
  Splitting followed successful full archive verification and changed no data.
- `20260910-retained-frame-actual-parent.tgz`:
  `3e83a10a4d016edfe0d55c3a43ada272d5985ca1a6d89f2ae771bfae17c0d4ae`.

Recovery root `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:
`checked-product-top-parent.tQnaKlfk`, `retained-frame-parent.mgnSs5jw`, and
`retained-actual-frame-parent.2nhHxm1Q`. All original root execution handles
for these three runs are terminal and consumed.
