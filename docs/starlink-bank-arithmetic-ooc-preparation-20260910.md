# Arithmetic bank OOC preparation — offline only

Prepared the exact actual-qualified R1/B1/O1 candidate at 175 MHz. No synthesis,
placement, routing, actual FFT replay, runtime edit, or primary-tree change was
performed. The original actual automation remains **FAIL**; admission recognizes
only its reviewed diagnostic-marker log-source failure, not arbitrary failures.

## Source and evidence identity

Preparation starts from FW `19dcc9c867c3cde285a2d9ca6c7d2a08c022f077` /
HDL `8bbfee6ebb1d77b58b33080e8a58bdcca978fd28`. All eight runtime files are copied
from the original v3 candidate freeze, byte-identical to actual-run HDL
`18aa1b6f58fe7abcf06672fccf6d93551174de54`, not from an active control alternative.
The original actual FW was `deb023b36b2780bd25aa5257eee52d905a662174`.

- Actual manifest: `6376f1fb2508f357933d4cb9cd9949d8da452d155a47084701aa29fb99df1954`.
- Reviewed original receipt: `be23853ba29f36a137b7ceba084bca0395338fbc6448dbd3a59640419cdb9c9c`.
- Separate post-hoc assessment: `a1e7eebc49fba088327109643d9beb120276eb2f6f230a885d5a9438e048da0f`.
- Original candidate WDB query: `e2150fca7a2861fc008d3962271f71c4e64b77b662aa8ebbc640d84eb8bcaf2d`.

The new read-only verifier pins these artifacts, verifies every original archived
candidate file (including the exact traceback, phase receipts, logs, generated
IP and WDB), and reruns the original frozen helper's source/vector, eleven-terminal
and ordered-event gates. It checks 76 original core-timing records and reconstructs
six qualified 119-bit comparisons from all 345 recorded values / 115 WDB paths.
The earlier external-force overflow remains visible to the bank/current veto while
the inner arithmetic/reference register remains zero. No original file is written.

The failure contract requires original `run_status=1`, `after_status=0`, the exact
archived failure receipt, and absent `results.json`. The raw HDL log must reproduce
the original diagnostic-inventory rejection; only the pinned original outer log
with the exact marker on line 448 supplies that marker. Future fixed-runner receipts
are not substituted. Numerics remain 19,456 ordered words per stream and 16,986
output-derived exact scores; the latter are oracle-only, not scorer-RTL evidence.

## Frozen recipe

Directory (relative to HDL):
`library/starlink_pss_acquisition/build/arithmetic-ooc-R1B1O1-175-prepared-v1`.

Inventory `SHA256SUMS`:
`c249a13a4e34aa393513fa955199407eef0a569484025d1e5cdb5fc83cb185ce`.
It lists 23 files: twelve synthesis inputs, three pinned assessment artifacts,
three Python helpers, original/adapted synthesis recipes, unchanged route recipe,
explicit settings, and preparation metadata. Original actual dependencies remain
in their separately archived 44-file freeze and are reverified at admission.

The synthesis inputs are the arithmetic probe, input/result guards, block mailbox,
forward joiner, kernel ROM, operand wrapper, arithmetic core, plus the factory,
kernel, XDC and thread Tcl. `PRIVATE_PAYLOAD_BUBBLES` and all current/held/late
overflow connections remain unchanged. No distributed/scratch candidate is mixed in.

The strict reversible adapter changes original synthesis recipe
`f843af0394cc680bf8344739ebe7adf7aece5d3db13e06b59b452d63372b9fe7`
only at admission/source-list/top/generic and integrity-receipt seams. It explicitly
sets and reads back `REGISTERED_SCHEDULING=1`, `BOUNDARY_ROUND_SAT=1`, and
`REGISTER_OPERANDS=1`. Its hash is
`359864493a948bab19bd0bc0079b7f7402b28fcb20caa9fb305496b4c7711183`.

Retained: Vivado 2022.2, xc7z010clg400-1, two threads/jobs, rebuilt hierarchy,
AreaOptimized_high, OOC synthesis, control-set threshold 4, unchanged factory
`0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d`,
and source_100 / island_175 constraints (10.000 / 5.714285714 ns). There are no
timing exceptions or new external delays. Diagnostic route
`0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`
is frozen byte-unchanged and remains unlaunched.

The one-shot owner preserves launch errors and independent after-integrity audits,
including a tool loader returning zero before Tcl executes. Completion requires
the unique original synthesis terminal, nonempty expected products, zero black
boxes, and clean source audits. Python children clear PYTHONHOME/PYTHONPATH/
LD_LIBRARY_PATH and use `-B`; the parent/vendor environment is preserved.

## Executed offline tests and retained attempts

Initial dedicated suite: **70 PASS / 23.85 s**, original handle 56382, exit 0,
`/tmp/starlink-arithmetic-ooc-offline-v1.A5U5mi`.

Final suite: **316 PASS / 48.62 s**, original handle 8877, exit 0, Ruff PASS,
`/tmp/starlink-arithmetic-ooc-final-v1.LZOnDD`. Preparation handle 83057 exited 0.
Both directories retain logs, XML, and cases. These are offline Tcl mocks and
Python/Icarus tests; none launches Vivado. The command uses the repository venv
Python with `-B`, `-m pytest -q`, a unique retained `--basetemp`, and these files:

```
tests/starlink_oracle/test_arithmetic_physical_preparation.py
tests/test_starlink_bank_arithmetic_monitor_boundary.py
tests/test_starlink_bank_arithmetic_actual_policy.py
tests/test_starlink_bank_arithmetic_offline.py
tests/starlink_oracle/test_payload_bubbles.py
tests/starlink_oracle/test_forward_retirement.py
tests/test_starlink_archive_parts.py
```

The 70 new tests include whole-recipe inverse, all eleven adaptation-anchor
mutations, each R/B/O omission, frozen-source identity, no-overwrite, poison-env
preservation, loader-zero/missing/duplicate completion, launch exception/nonzero,
post-failure source tampering, source/phase/late-failure/packet/FFT/WDB provenance
rejection, and actual recorded-vector/path/qualifier/transport mutants.

Before pytest, two read-only development checks failed: archive `outer/` paths
were initially treated as inside the actual directory, then literal RTL-list
anchors incorrectly assumed filename-style formatting. Both fail-closed errors
were fixed without touching original evidence. Their raw tool outputs remain in
the task transcript, not separately archived files. The initial Ruff check also
reported import/format and closure-binding lint issues, fixed before the passing
suite. No failed actual execution was retried or relabeled.

## Remaining authorization and scope

The next possible action is one source-specific OOC synthesis after parent review,
using the frozen owner and externally supplied inventory SHA. Neither this report
nor the prepared executable grants launch authority. Route is separately gated.
The inherited XDC lacks external IO delays; CDC and full-receiver timing remain
unqualified. No resource count, mapped DSP register claim, achieved clock,
receiver throughput, RF result, or timing accuracy follows from this preparation.

The full objective remains canonical 15 MS/s coarse at original 15/30/60 rates,
original-rate sparse native fine, independent 2.5 MS/s pilot, .18 before .17,
and eventually eight targets / 120 ms dwells / 300 s. This isolated step does not
substitute for those integration and deployment gates.
