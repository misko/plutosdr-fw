# Bank-local input identity — isolated DO NOT MERGE experiment

Parent: guard facts, FW `bf817a6bd3b1d0de948c0efe29b916a5850faf85`, HDL
`82be254db13c20eb5aed72cd2010138cf334dfe2`. Parent default route: -1.340 ns
WNS / -463.636 ns TNS / 821 failing endpoints. A separate post-route physical
pass improved same-domain 175 MHz slack to -1.167 ns, but global slack remained
-1.307 ns at a held metadata crossing. Neither parent is deployment-qualified.

## Change and frozen acceptance gates

Default-off BANK_LOCAL_IDENTITY compares both raw 70-bit held bank metadata
buses with the checker's admitted descriptor before the scheduler selects a
one-bit comparison result. All bits remain checked on the current edge. No
pipeline register, delayed fault, hash, trusted-data exemption, reset, state,
framing, actual FFT input delivery, certificate or public-output change.

For X/Z bank phase, retain equality of the original bitwise-merged selected
metadata bus. Equality after a ternary mux is not generally equivalent to a
ternary mux after equality for unknown selectors. Default mode uses the original
comparison unchanged. The top opts in only under registered scheduling and
wires both raw banks plus the original phase-selected metadata. The new checker
is a local staged-control copy; the inherited reference remains unchanged.

Complete checker/top source inverses prove the limited source delta. The prior
guard-fact inverse uses its pinned parent snapshot; live predicate extraction
tests remain. No diagnostic or behavioral check is removed.

Preflight: **13 tests pass in 16.11 s**. Each default/enabled real checker
comparison covers 446534 checks and 8227 clock transitions, including a finite
combinational sweep across all 70 bits, four-state selector/control/metadata,
three ordinals and eight metadata patterns. Sequential scenarios cover healthy
512-word delivery, malformed position/last, unknown metadata, duplicate starts,
unmet real-time demand, mid-input reset and legal core waitstate. Three mutants
(unknown-selector shortcut, swapped banks, dropped last metadata bit) fail.
This is finite differential testing, not a full formal receiver proof.

Actual FFT bench includes a default-mode real checker witness throughout the
existing numerical/fault/reset campaign. Require current outputs, identity,
certificate and diagnostic equality, at least 1000 checked cycles and at least
9216 forward and inverse beat observations. Add four cases: both owners with
selected versus unselected bank bit corruption at input ordinal 32. Selected
corruption must quarantine immediately and reject stale publication/reuse;
unselected corruption must preserve a healthy result. All four must then reset
and recover with 512 correct reads and one real release.

Require all 64512 actual FFT records and service intervals unchanged, all
regressions, source-bound synthesis and unchanged diagnostic routing. No added
receiver features, clock waivers or service-limit relaxation before closure.
The overall simulation timeout grows only to accommodate added recovery cases.

Prepared inventory: `5871d94dfa6ae322843a8d327624a21aa77ba4461a61a47f0c74ddbda4f3eb4a`.
Actual simulation passes in 167.39 seconds and synthesis in 99.12 seconds,
both first attempts with source receipts unchanged. All 64512 numerical rows
match; CSV remains
`d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Service remains 3659/3659/4927/11727/3659/3659 clocks; the 11727-clock case has
a deliberate 9000-clock reader pause and is excluded from the unchanged
5215-clock diagnostic service gate.

The original-checker witness passes 421667 falling-edge observations, including
44707 forward and 30240 inverse certified-beat observations. These are monitor
observations across healthy and aborted work, not a published-frame count.
All four selected/unselected corruption cases pass with fresh 512-read/one-real-
release recovery. Prior certificate, fault, reset, reader-stall and numerical
checks remain active. 152 admission and 105 completion receipts include aborted
work; this is not continuous receiver throughput evidence.

Synthesis DCP:
`0069854c76e26ad876beb62de5bf82fa4e020f82a08bb8cb16a8ba00046300e0`.
**480 regression tests pass in 74.88 s**, no failures, errors or skips. This
includes ten new actual-evidence auditor controls; incomplete cases, missing
coverage/equality receipts and short recovery evidence are rejected.

## Routed result: retain experiment, do not promote

Unchanged diagnostic routing completes in 49.04 s on the first attempt and
passes the source/checkpoint/report audit. The physical timing gate fails:
**-1.940 ns WNS / -579.273 ns TNS / 785 of 13864 failing setup endpoints**.
Compared with parent guard facts, WNS worsens 0.600 ns and TNS worsens
115.637 ns despite 36 fewer failing endpoints. This is not a timing-reference
promotion. Keep the parent and private-certification references.

Resources: 2805 LUT / 5687 FF / 21 DSP / 15 RAMB18 / zero RAMB36. 8431 fully
routed nets, zero routing errors; hold +0.062 ns and pulse +1.830 ns pass.
The unchanged isolated build still has 114/124 unconstrained I/O. No board,
CDC, continuous receiver, physical signoff or deployment claim.

Worst path starts at source-bank held metadata bit 67 and reaches output-bank
request toggle through preflight identity comparison and shared guard/fault
logic. Eight logic levels, 7.602 ns data delay, 6.019 ns routing (79.2%). The
next path (-1.863 ns) reaches sticky fast fault from the same source. The
refactor verified the intended checker behavior but did not remove the broader
preflight-to-publication control dependency.

Routed DCP:
`008ccdbdbaad3b89791eca4366655b6da621af571fe39ded26b97deb22b76d4d`.

Next investigate preflight validation and publication together on a retained
reference. Establish the reachable phase/ownership relationship before claiming
preflight faults cannot coincide with an outstanding inverse publication.
Core reuse and mailbox reader release are different events: no phase-based
exemption is justified without that proof. Keep current reset/fault cancellation,
all diagnostics and real reader ACK. A revised registered validation boundary
must account for every added cycle, reject stale work and pass original/fault/
reset tests before actual FFT and unchanged routing. Do not stack comparator
changes or remove more TX functionality merely because a different endpoint
became worst. Preserve this result and its full evidence as a tested alternate.

## Required end state

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection.
Subsystem timing/CDC, full receiver route/reset/board I/O, sustained capture,
actual 60 MS/s RX calibration and Ethernet/IIO qualification precede `.18`
reversible canary, then `.17` PPU Ethernet-only deployment with pinned rollback.
Final gate remains the 300-second scan, 120 ms valid dwells and blind host GLRT.
No radio, PPU/main or primary production HDL change. This worktree excludes
large historical HDL evidence copies; no existing worktree was deleted.
