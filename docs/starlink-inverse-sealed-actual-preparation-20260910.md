# Inverse sealed actual-core preparation (offline only)

Status: draft source-specific preparation, not an actual FFT run or physical
qualification. The published252-test inverse composition remains unchanged.
No product-bank/ROM/control/CDC experiment is merged into this candidate.

The proposed single future evaluation is **R1/B1/O1/L1/E1 at175 MHz**, source
domain100 MHz. R is registered scheduling, B boundary rounding, O the operand
register, L local first admission, E the new inverse sealed output. E remains
default0 in the additive derived test top and is explicitly bound to1 only in
the prepared profile. No execution is authorized by creating a preparation.

## Exact seam and unchanged reference

The accepted original is original6473, L1v4 manifest
`1717107b5be08b9ff72e7a224cbf20a1354ddd215270a7cd1923b62e12b5d858`,
with original automation PASS, not the earlier22656/14041 failures. Its49
frozen inputs, full bench, arithmetic and local guard observers, and8 immutable
numerical vectors are preserved byte-for-byte in the new closure. Their older
v3 arithmetic automation failure/post-hoc history is also preserved as history,
not used as a generic failed-run admission exception.

Runtime is the reviewed inverse composition: top2f988a16, issuer8ad9c2e7,
CDC bankea27c4e2 plus the original L1 arithmetic/guard/source/product/core
dependencies. The10 runtime modules and21 compiled modules are explicit. The
immutable generated FFT factory remains0795ea7e; no behavioral FFT replacement
may appear in any source. Icarus `-i` elaboration omits the unavailable vendor
module and is only a syntax/hierarchy check; its output is never executed.

The distinct generated bench has a strict10-anchor inverse to the accepted
L1 bench. Besides naming/parameter/include/terminal additions, three semantic
interfaces are explicitly rebound:

- The inverse adapter sees the unqualified old private return. Its bank input
  additionally requires inverse phase and the admitted producer reference.
  Both connections are checked; forward offers must not write the inverse RAM.
- The unchanged result-guard shadows receive actual transport/publication/ACK
  readiness (`output_destination_ready`), not scheduler free/reusable capacity.
  Every old155-bit guard and119-bit arithmetic comparison remains active.
- The inverse preflight destination-loss injection targets the owned reservation,
  not free capacity. An additional admitted-lease witness requires reservation
  to remain held while reusable is0 on the two following admission edges.

These changes preserve old fault intents and numerical expectations, not literal
identity of obsolete overloaded READY expressions. The whole-source inverse
makes every other original stimulus/check/wait/fatal recoverable exactly.

## Timing and publication contracts

All76 accepted historical nominal/stalled jobs have configuration+3,512 input
beats at offsets5 and7..517,512 raw results+1298..1809, and one status at+1300
(third raw word). Forward publication remains+1810. The new inverse is predicted
to qualify and privately take its final word at+1810, capture its certificate
at+1811, seal+1812, and publish+1813. All stages must be witnessed separately;
certificate receipt is not publication, reader ACK, release or reusable.

The fixed old CSV SHA is
`e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71`.
The new whole CSV is not expected to equal it. Nothing simply strips timestamps:
forward/product event cycles are FAST, inverse event cycles are SLOW. The old
arithmetic checker still verifies19456 ordered exact words per stream and16986
output-derived sample scores (oracle only, no scorer RTL). A separate clock
model checks every absolute event time against the admitted job and actual
publication, including the unmodified `slow_cycle % 17 < 13` READY schedule.

The immutable actual bench has1fs precision, fast half-period2857143fs, first
slow rising edge6300000fs and slow period10000000fs; counters increment on
falling edges. A published request is sampled at the first strictly later slow
edge S1, with first possible acceptance S1+4. The entire historical38-block
inverse schedule, including all stalls, matches that model; parent independently
verified it without importing this helper. This validates the reference clock
model, not the future candidate trajectory.

The absolute canonical15 budget stays5215 fast clocks/pair (29.8us at175 MHz).
Nominal planning ceiling is4549+8=4557; <=8 is not a bound on all stalled deltas.
For example, moving first slow acceptance from phase8 to10 changes the512th
acceptance675→681 (+6 slow clocks) before idle/release. Guard8192, drain25000,
whole-bench1500000, fault observation24 and provisional-prefix[128,132] limits
are unchanged. No post-run widening is permitted.

The additional protocol CSV checks every admitted lease,512 private values and
all75 metadata bits, qualification/certificate/seal/publication, actual reader
ACK, tagged release and reuse. Current certificate-loss, raw-orphan and common
fault veto assertions also run during the original negative epochs. Held final
VALID must never cause a second private take. Existing source-reset barrier
and source-fault purge behavior are unchanged from the252-test composition.

## Launch and evidence policy

The generated runner is a strict adaptation of the accepted f76090eb runner.
It preserves2022.2, two threads, explicit repository Python with child-only
LD_LIBRARY_PATH/PYTHONHOME/PYTHONPATH removal and `-B`, exclusive absent-output
launch admission, and source verification after success **or failure**. No
results.json is published until both run-body and post-integrity statuses are0.
All11 old terminal receipts, the full local guard receipt, new protocol receipt,
generated-IP pre/post/live hash, full source inventory and independent numerical
and dual-clock event checks are required. Known failed originals stay failures.

Existing115 arithmetic and14 guard diagnostic paths remain. Nineteen explicit
inverse ownership views are added to the same observed actual root; plain and
escaped parameterized roots are checked without discarding observed paths.
Each inventory/receipt is exclusive and closed before unchanged `run all`.
Inventory success alone is not recorded-history proof; any future WDB must be
retained for separate read-only history verification.

## Retained offline attempts

All paths below are under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

- First read-only clock parse rejected epoch0 startup `x` before scoping healthy
  rows. The tool-output traceback is retained as an observation, not a fabricated
  raw archive file. Parsing now validates cycle/epoch first and rejects unknowns
  inside healthy running rows; common-reset private state is not qualified.
- Original51815 then verified all76 historical jobs and every forward/product/
  inverse timestamp. Subsequent retained policy runs repeat that check.
- `inverse-actual-prep-tests-v1.qMUJcbIK`: original22073 EXIT0,17PASS1.73s.
- `inverse-actual-prep-tests-v2.MQ8uRcGh`: original90371 EXIT1,17PASS/1FAIL;
  elaboration rejected `bank.staged.checked_seal`. That signal is an output port
  at `bank.checked_seal`; only the additive monitor binding was corrected.
- `inverse-actual-prep-tests-v3.1Vm2RIcX`: original85362 EXIT0,46PASS2.63s.
  A subsequent narrow safe-path check on accepted history inputs is a later
  source revision, not retroactively part of this run.
- `inverse-actual-prep-tests-v4.H5VPZTWB`: original89578 EXIT0,60PASS3.88s,
  including complete synthetic protocol-model receipts and specific mutations.
  Synthetic protocol data are labeled model-only, never an actual run receipt.
- `inverse-actual-prep-tests-v5.onXkG1eN`: original65052 EXIT0,65PASS3.91s,
  RuffPASS. Exact plain/escaped-root waveform discovery reaches the unchanged
  mock run-all trap; missing, duplicate and mixed-root leaves fail beforehand.
  The protocol fixture independently enumerates raw slow/fast clock edges for
  reader idle/ACK and uses an independently enumerated falling-edge list for
  slow counters. It never calls the verifier's reader_ack_cycle/read_cycles.

Exact final offline command (new output directory required for repetition):

```sh
env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest \
  tests/starlink_oracle/test_inverse_sealed_actual_policy.py -q --tb=short \
  --basetemp /absolute/new/output/cases \
  --junitxml /absolute/new/output/results.xml
```

All65 results are preparation tests; there is no successful candidate actual
result available to feed the full collector. Its numerical and protocol models,
strict receipts, source gates and failure paths are independently tested, while
actual execution and complete candidate service remain explicitly pending.

No vendor FFT simulation, synthesis, route, receiver build, deployment, radio
or PPU action occurred. Full receiver capacity/timing, canonical15 at original
15/30/60, native fine concurrency, independent2.5MS/s pilot, RF accuracy and the
eight-target300-second visit remain outside this offline preparation evidence.
