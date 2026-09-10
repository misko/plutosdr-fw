# Combined R1/D1/S1 actual run passes the qualified scope

Original actual handle **79656 exited0**. Both complete main CSVs match the
historical R1 golden exactly; both extra fault/reset tasks and the literal
runner plus independent qualified-observer audit pass. No raw217 pass,
single-knob attribution, physical timing closure or RF claim is made.

Measured FW `6a8bce26b7ecc408a610efc139b60fb0d3c97414` /
HDL `5c18664368eeaf1bf2f76a2a672dfbd3f78c167f`. Runtime ae50 unchanged;
candidate R1/D1/S1, independent dec20 reference R1 with neither new knob.
Both extras1/175/QUICK0, unchanged runner496a3ed4...,2022.2/two threads,
one launch/no retry. Start08:40:10UTC, exit08:50:04UTC; wall593.59s,
user609.66/system8.99s, peak RSS1132592KB. All27 original warnings remain.

Both main CSVs:589950lines, SHA256
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`.
Both extra CSVs:33180lines, SHA256
`b965d12603a64111fa9c6ea36cb0f12189945ad4d9be7cf4fbd883980c4ec4a0`.
Each pair is byte equal. Both extra receipts assert two final faults,
three held stalls, two one-sided resets and four healthy recoveries.

Final whole-module shadow:1246258checks,780367activechecks,
36identityconsumptions,270permitted unconsumed scratch differences,
two final-fault edges,99936owned-stall edges,143reset-owned edges.
Original registered84preflight/12active-input/12expected-cache cases and
84raw-bank rows complete, with unchanged reason/retirement/ownership
shadows. Scheduler8fault/4reset boundaries,106completion consumptions and
44healthyblocks complete. Actual inverse-current/sticky-forward counters
remain0; no coverage of those fault categories is inferred.

The frozen observer audit accepts1246258=953795raw-equal+292463invalid-only
samples. Every invalid-only row has both valid bits0; complete four-state
categories are `x1x00101/00000101`148rows,
`x1x00000/11z00000`99179rows, `zzz00000/00000000`193136rows.
Every row and per-epoch count is retained; baseline29 is not an expectation.
Driver origin is unresolved. All216 other fields remain unconditional and
all8status bits remain checked when either valid is not exactly0. Earlier
strict failures stay preserved; this is explicitly the qualified scope.

Run `/tmp/starlink-completed-input.5EaJuD/extra-edge-combined-prepared-v1`.
Before/after full freeze verification passes:
`8e9251fe06e41917e9e0b5ebceef36db444bc39770efe7acb940dbfcc4ed7906`.
Archive `hdl/library/starlink_pss_acquisition/evidence/exact-control-combined-actual-v1/`
retains full sources, logs/rows/receipts, warnings/timing, complete CSVs and
WDB with lossless compression and original hashes. The105807603-byte WDB
gzip is transported as three ordered<=40MiB parts, with a no-overwrite
reconstruction helper and per-part/assembled/raw SHA+sizes. The original
monolithic gzip and project remain local and intact. Missing/reordered/
corrupt/unsafe parts and overwrite are rejected; full reconstruction is
tested. The original72-entry inventory is retained separately.

Original unpublished HDL67795ad3/FWa1707a59 are preserved under
`refs/local-only/exact-control-combined-oversized-20260910` in each repo.
Only these own unpublished tips are amended; the local-only refs must not
be pushed. No original source, simulation result or failure is replaced.

No physical trial was launched. The existing synthesis script forwards
only REGISTERED_SCHEDULING and expects scope.txt; it cannot directly use
this exact freeze. Any next physical preparation must explicitly verify
R1/D1/S1, successful actual receipts and exact seven-source closure while
preserving100/175 clocks and all existing constraints/directives. Only
offline adapter preparation has been separately authorized so far.
