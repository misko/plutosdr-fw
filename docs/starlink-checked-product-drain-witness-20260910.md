# Checked-product v1 final nominal drain: bounded bench correction

The original root-owned actual30484 failed. Its owner, complete traces, source
inventory and result remain unchanged. Frozen `verify_terminals` passed; root
separately reports the original full ownership ledger passed. This document
does not relabel the run or qualify any RTL/physical result.

## Exact failure

The literal `verify_cycles` final predicate has epoch1 pending forward142157:
32 forward admissions but31 completed drain samples. Epoch2 has all6 services.
The two traces contain591025+33208=624233 data rows; the final cycle624232 agrees
with owner.pre624233. Thus observer accounting is not the failed term. Nominal
intervals4555/4556 and observed nominal drains4553/4554 are below5215; observed
stall intervals4828–4836 and drains4826–4834 also remain below5215.

Frozen CSV boundary, fields named by the unchanged24-column header:

| Cycle | Running | State | Inverse | Result busy | Output bank ready |
|---|---:|---:|---:|---:|---:|
|146706|1|ACK_DRAIN|1|1|1|
|146707|1|ACK_DRAIN|1|0|1|
|146709|1|RESET0|0|0|1|
|146710|1|RESET1|0|0|1|
|146711|0|WAIT_BANK|0|0|0|

The real ACK preceded reset, but no live pre-edge WAIT_BANK/forward/ready sample
was retained. The original `await_results` observes post-NBA state at+1ps;
the caller enters `reset_epoch` on a slow falling edge before the next CSV
sample. The parser correctly does not count reset as a completed drain.

## Additive offline correction

`hdl/library/starlink_pss_acquisition/prepare_checked_product_drain_witness.py`
SHA f64d6e96f1d2fa3f8d0af856c495ae9e6f88182893e949ec0d14a99006797d79
transforms only the exact d9080893 v1 bench. It adds one task and a call after
each of the two original service-profile `await_results` calls. The entire
original task and both call expressions remain literal; reversing the three
edits restores the complete d908 source. The a04c result parser is untouched.

The new task samples a live fast positive edge requiring published=count,
WAIT_BANK, forward phase, result_busy0 and output_bank_ready1. Reset, current
fast fault or public fault, including unknown values, fail explicitly. It
completes the existing+1ps settling interval and rechecks reset/fault before
allowing the subsequent reset. Its deadline is the same final forward-admission
service budget: `0 < fast_cycle-previous_admit <= 5215`, not an extra5215-clock
allowance. QUICK_MUTATION0 is the admitted profile; calls are inactive in quick
mode. No runtime state, clock, numerical vector, raw fault stimulus, original
fatal, CSV predicate,32/6 count, or service threshold changes.

## Executed scheduler evidence

Tests `tests/starlink_oracle/test_checked_product_drain_witness.py`
SHA40c7ef6df39a06f5ee32fe5734d5b1d01ef6fda7d78507edfbd36a0213dcaee0:
35PASS0.30s, original terminal0, retained in
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/checked-drain-scheduler-v2.dQWCZjOG`.
Prior30PASS remains separately in checked-drain-scheduler-v1.Ro2Ln7vl.

Two declared slow-reset phases reproduce the old post-NBA sample omission and
show the new live pre-edge sample. Directed cases check5215/5216, held owner/
phase/count/READY, X/Z reset/current-fault/control states, and fault/reset in
the post-sample NBA interval. Eleven executed mutants remove independent
owner predicates, pre-edge wait, reset/fault fences, post-sample delay, or bound;
each fails its independent fixture assertion. These are scheduler/observation
tests, not a vendor simulation or a substitute for actual controller evidence.

Replay from this FW tree, using a new non-overwriting `--basetemp` and JUnit path:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH -u PYTHONOPTIMIZE \
  PYTHONDONTWRITEBYTECODE=1 /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
  -m pytest -p no:cacheprovider tests/starlink_oracle/test_checked_product_drain_witness.py
```

## Source-specific successor preparation

After parent independent35PASS0.34s and source review, an additive v2 preparer
was authorized offline. No original frozen files were changed. New helper
`hdl/library/starlink_pss_acquisition/prepare_checked_product_drain_actual.py`
SHA bcd3c96b3f784b6ef7a12c5750e976d6d50c8eb19d13e4c6a3de3f08bcacfe6a
copies all84 original members, changes only the bench above and the two runner
CLI targets, and checks the full84-file inverse. It includes the pinned35-test
scheduler source as provenance. The a04c result parser remains byte-identical.

Its additional result check runs only AFTER the complete original result gate.
Exactly two typed drain receipts must identify profile0/count32 and
profile1/count6, in order. Each marker must match the final forward admission,
an actual live pre-edge CSV row, and the unchanged parser's final service value,
including the5215 cap. Missing, duplicate, incorrect, non-live, or reset-derived
markers do not pass. This is additive evidence, not replacement acceptance.

Fresh89-member preparation:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/checked-product-actual-prepared-v2`.

- Inventory55288860074df8107d142c97bd69cb67bc71815f13bbb8bacc3b664b9547f5ea.
- Bench1b07267832f563354fc651a53e0f1ab869f1aac4644424a067820d271bdd2843.
- Runner e991428acafae4fc30ef27a2457dbc4ef82d37fe82408da51eab632ebf8d2394;
  reversing only two CLI filenames restores93476635 in full.
- Tests `tests/starlink_oracle/test_checked_product_drain_actual.py`
  SHA b0f99e5e77e2a6a3f48bf69694ef637d5f6730583a4088b85f7632bcf918b0a3.

Own complete41 preparation/receipt plus35 scheduler tests:76PASS0.58s, terminal0
at checked-drain-actual-v1.eO3DtB2O under the persistent recovery root. Copied
helpers verify successfully from `/`;89-file inventory closes. All original84
files and30 root-pinned live sources were separately rehashed unchanged after
preparation. The41 new cases cover complete inheritance, mutated policy/runtime/
vectors/observer, absent/false markers, non-live rows, original-gate ordering,
and no-overwrite/symlink targets. Add the new test filename to the replay above.

No vendor command was executed and no physical launch is enabled. Root review
and a separately authorized one-shot owner remain required for this successor.
