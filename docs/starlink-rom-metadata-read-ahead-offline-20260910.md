# Exact block-metadata read-ahead: offline alternative

The separate additive ROM prototype now has a default-off
`PRIVATE_BLOCK_METADATA_READ_AHEAD` option. **60 tests pass**: the retained
31-test word suite and 29 new tests. No canonical ROM, forward joiner, bank
wrapper, numerical contract, actual FFT run or physical implementation changed.
This is not evidence of timing closure or approval to integrate the prototype.

Tested source pins: FW `4e61c9dbda24a4a437f1d00b596c366edd267b3b`,
HDL `32b20cb750caeede27561193728f088bc249195e`.
Parent baseline: FW `80fbb1434eaa39dc37c560389b0b356e411afde4`,
HDL `b83a45267a8cb8039eb7c7b4eaed5e5d6c3bb489`.

## Exact recurrence and intended dependency cut

The 69-bit tuple is `{block_start_index, block_exponent}`. A speculative
register captures it only when `input_ready && at_block_start`; that enable
does not include current `input_valid` or framing/identity validation. A
retained register copies the previous speculative tuple when the previous
selector was one. The new selector defaults to zero, becoming one only inside
the original nested `if (input_accept)`, non-taken `if (protocol_error_now)`,
then `if (at_block_start)` branch. Reset/flush clear the retained tuple and
selector. The checker-visible tuple selects speculative versus retained data.

If the old tuple updates, that same event necessarily permits speculative
capture, so the mux exposes the new tuple on the same edge. Otherwise, the
previous visible tuple is retained, including the first stall/bubble after an
update. No added cycle, validity mask, fault exemption, or delayed checker is
introduced. The nested procedural tests are not rewritten as strict binary
comparisons: an X/Z error expression follows the old Verilog `else` behavior.
The default branch keeps the old tuple reset/update recurrence. Other state,
word-read logic and all public outputs retain their original expressions.

This targets the measured product-bank current-fault → kernel block-metadata
CE path, unlike word-only prefetch. The wide current-fault dependency now
controls the private selector rather than the 69-bit capture enable in RTL.
That is a structural hypothesis, not a mapped result: synthesis may absorb,
duplicate or transform registers and muxes. Selector fanout, tuple mux delay
into the current-beat identity checker, and separate held-phase/input-guard
paths may still dominate. No physical dependency is claimed removed yet.

Logical cost is 139 tuple/selector bits instead of 69: **+70 bits and a 69-bit
mux** before optimization. Together with word read-ahead at DATA_WIDTH18,
the two options add 107 logical bits and 105 mux bits. No LUT/FF/BRAM/DSP
mapping, dynamic-power or timing measurement has been performed. Invalid
first-slot bubbles can switch the speculative tuple and consume power.

## Independent comparisons and coverage

`rom_metadata_contract.py` has a literal full-module inverse to the frozen
b83 additive ROM; the previous canonical-source recipe then remains exact.
The only old Python-suite changes import and compose this strict inverse.
A further whole-file check restores that old test file literally. Its bench,
stimulus, assertions and mutation criteria are byte-identical to the baseline.
The canonical ROM is independently checked byte-for-byte unchanged.

The new generator starts from the frozen entire old bench, adds two shadow
instances and extra epochs, and compares word/metadata options 00, 01, 10 and
11 concurrently against the independently frozen canonical ROM. All old
public outputs, coefficient bits, checker predicates and old private state
remain unconditional four-state comparisons, including invalid cycles. The
12 width2/18/24 × balanced0/1 × scratch0/1 runs each record 24,708 cycles and
74,124 observations; the 20,000-cycle randomized portion is explicitly an
unconstrained stream, not 20,000 healthy jobs.

Each run retains the old three healthy blocks, 64 identity faults, two accepted
unknown-metadata cases, 296 stalls, occupied X/Z-ready cases and both occupied
word-selector flush states. Additional checked epochs cover every one of the
69 tuple bits on an interior fault; three invalid/X/Z-valid first-slot captures;
two accepted X/Z first tuples; both occupied metadata-selector flush states;
two X/Z first-framing expressions; malformed first ordinal/TLAST; two continuous
blocks spanning modulo-64 `+447` wrap; and a subsequent bit63 identity fault.
Private selector first-event compliance is checked separately.

Ten mutations fail the unconditional old/public comparison, including lost
retention, wrong selector, wrong capture enable, bit63/exponent-bit4 corruption,
wrong reset, reversed first-slot selection, omitted fault veto and X/Z
sanitization. Invalid new parameter values −1, 2, X and Z fail at time zero.

Two equivalent alternatives are labeled honestly. Replacing speculative
capture's `input_ready` with `input_accept` passes the old state comparison but
retains the unwanted current-valid dependency. Removing only the selector's
first-slot qualifier also passes public comparisons because speculative data
still changes only at first slots. It fails the selected private update rule;
the positive-control run excludes **only that new private selector assertion**
and retains every old/public comparison and other assertion. Neither result
is reported as a public semantic counterexample or selected implementation.

## Executed attempts and immutable evidence

- V1 `/tmp/starlink-rom-metadata-v1.LKDkmKZf`: exit2, two collection errors
  from unqualified local imports; no simulation executed.
- V2 `/tmp/starlink-rom-metadata-v2.lD7zuBe5`, original handle94187: exit1,
  55 passed/4 failed in15.78s. Two source checks used a nonunique reset inverse
  anchor; one old word mutation anchor also matched the new selector name;
  one intended negative was the publicly equivalent broader selector above.
  All 12 four-option functional runs passed. Logs, generated sources and the
  complete V2 changed-source snapshot remain intact.
- Final `/tmp/starlink-rom-metadata-v3.gDuKQb42`, original handle29657:
  exit0, **60 passed in16.11s**, Ruff clean, both Git diff checks clean. Fixes
  narrowed the inverse anchor and renamed only the new metadata selector;
  no old stimulus/assertion was weakened. Final sources were copied before
  committing and remain frozen.

Portable package `reports/experiments/20260910-rom-metadata-read-ahead-v1.tgz`
contains 835 source/artifact members plus its embedded receipt, all attempts,
compiler/executable/log/XML artifacts and all final source dependencies.
Archive SHA256 `10390700c7d77202e35ae3b1d3fb019e5a62fc67bb42ca12687d795895e1b8fe`,
4,113,301 bytes. Its companion JSON records every inner file hash; 29 redundant
pytest-current symlinks are explicitly excluded. The existing collector is
unchanged. Original raw attempts are retained.

Next work requires separate review and authorization. In particular, actual
joiner/bank fault, ownership and retirement proof must preserve every raw
coefficient and metadata observation before any source-specific physical
trial. No automatic integration, synthesis, route, promotion or radio action
follows this offline result.
