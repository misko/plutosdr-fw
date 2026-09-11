# Private replay versus actual publication — DO NOT MERGE

Baseline: completion/private-ROM FW `cdf68656c`, HDL `b4d092fa7`; actual FFT
and 346 tests passed, but routed timing failed at -3.134 ns. The worst path fed
publication-controller phase through preflight/current fault logic.

## Implementation contract

The controller's replay-ready input now describes private buffer capacity and
registered descriptor validity, without the current shared-fault tree. The
actual bank authorization signal still requires replay-valid, that capacity
and descriptor validity, AND no current fault. The source of public authority
is unchanged. No metadata, numerical, publication or final-reader check is removed.

On a coincident new fault, private replay may advance the controller into P_ACK
without authorizing the bank. The registered epoch abort fences the next edge.
Independently, P_ACK checks that the actual bank request transitioned from its
saved initial value before it may notify publication or issue RELEASE. If the
caller does not abort, a missing transition quarantines the controller instead.
Idle request/ACK equality is never evidence of publication. Successful publication
still retains ownership until actual final-reader acceptance/ACK and ledger release.

The controller's state-transition logic itself is unchanged; its comments now
state the observation contract precisely. Runtime changes are the separated
private-ready and public-authorization wiring inside the experimental integration.

## Evidence

Six healthy numerical/backpressure contexts and the entire previous reset/fault,
admission and completion campaign remain. Five new actual-FFT cases inject a
vendor fault, product-bank framing fault or duplicate status at the private
replay edge, or reset either clock side there. The first three require an
observed private P_ACK advance with no bank request change or notification;
all require no later publication/release/reuse. Actual bank authorization is
checked against its unchanged current-fault predicate throughout the run.

Actual generated-FFT verification passes in **95.81 seconds**: all **64,512
numerical records** independently match the pinned reference, and the CSV is
byte-identical to the completion baseline. Service intervals remain
3659/3659/4927/11727/3659/3659 fast clocks. All old and five new boundary cases
pass; 84 admission and 64 close receipts are observed including aborted jobs.
The existing 5215-cycle cap is unchanged, excluding only the deliberately
9000-clock-stalled reader. This is not continuous RX or RF verification.

Standalone real RAM/ledger tests exercise withheld actual authorization with
and without a caller abort, then complete a fresh authorized 512-read epoch.
Unsafe early notification/release and ignored-request-transition mutations are
rejected. The first isolated run passed eight executions with one duplicated
negative case; final regression removes that duplicate and uses seven distinct
cases. Parser controls require all actual private-step/public-veto evidence.

Initial lint/controller regression passes 16 tests in 0.38 seconds. V1 synthesis
completes in 98.34 seconds. Before/after sources remain unchanged; real FFT
wrapper, device, diagnostic clocks and route recipe are unchanged.
Frozen inventory SHA256:
`8981f0faf9a2e0b684a12eea63aa83873fb0e87be152a6f047508c1449e695d0`.
Numerical CSV SHA256:
`d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
V1 combined regression passes **360 tests in 47.62 seconds**. Source-matched
routing completes in **60.76 seconds**, improving to **-2.265 ns**, TNS
**-1021.803 ns**, **936 / 13573** failing setup endpoints, versus baseline
-3.134 ns / -1304.699 ns / 1398 endpoints. Timing still fails. Hold +0.066 ns
and pulse +1.830 ns pass; 8396 nets fully route with zero errors. Resources:
2790 LUT / 5588 FF / 21 DSP / 15 RAMB18. The worst path now runs from ledger
tag lookup through the wide writer descriptor comparison: 13 logic levels,
7.867 ns data delay including 4.677 ns routing.

V2 splits that lookup and comparison at a register boundary. Accepted completion
captures the lookup payload, expected descriptor and found/uncommitted flags,
clears public descriptor-valid and sets pending. The next edge compares held
descriptors and grants valid or latches a sticky fault. Pending validation cannot
authorize output or be overwritten. The actual bank authorization still sees
current faults; a later fault can cancel even a matching captured descriptor.

The old corrupted-lookup case now checks the capture boundary, restores the live
lookup, and requires the captured mismatch to fail on the next edge. Four added
actual cases cover vendor fault during pending validation, reset from either
clock domain there, and corruption of the held expected descriptor. This is
additional pipeline/cancellation verification, not relaxation of the lookup check.

V2 preparation/lint passes. Actual generated-FFT verification passes in **103.11
seconds**, with the same 64,512 numerical records, byte-identical CSV and service
intervals. All four pending-validation cases pass, with 92 admission and 68 close
receipts including aborted jobs. Combined regression passes **366 tests in 48.35
seconds**. Synthesis completes in 103.73 seconds and route in 53.72 seconds;
before/after source and checkpoint checks pass.

The V2 route **regresses**, so it is retained as an experiment, not promoted:
**WNS -3.251 ns**, TNS **-1733.553 ns**, **1364 / 13766** failing setup endpoints.
Hold +0.070 ns and pulse +1.830 ns pass; 8293 nets fully route with zero errors.
Resources are 2717 LUT / 5653 FF / 21 DSP / 15 RAMB18. Five critical CDC findings,
208 warnings and 114/124 unconstrained I/O remain. No clock or timing waiver
was introduced; neither V1 nor V2 meets the subsystem timing gate.

The wide combinational writer comparison is no longer the worst path. Instead,
publication phase feeds bank metadata checks and shared fault qualification,
then `output_complete_accept` drives descriptor-register enables with fanout 181.
The worst path ends at `output_descriptor_expected_reg[59]/CE`: 12 logic levels,
8.712 ns data delay, of which 6.768 ns is routing. Adding a comparison stage did
not remove this expensive capture-enable dependency.

The next bounded experiment is to separate private descriptor-data capture from
completion authorization, using a local registered ownership/capacity condition
and explicit freeze-through-publication/reader-ACK rules. The actual acceptance
receipt, validation result and current-fault publication veto must remain
authoritative. Before routing, test invalid-input churn, pending validation,
fault-edge capture, reset, held-bundle stability and real final-reader release.
Do not simply remove the capture enable: these registers also supply the reader
and must not be overwritten while a descriptor is live. Retain V1 as the better
measured replay reference; V2 is useful cancellation evidence, not a timing win.

V2 inventory SHA256:
`e56eb3ffa0c1dbe54ca0a7e21b78b84f5c84aa969d3352cbc452470e311da589`.
V2 synthesis DCP SHA256:
`bcea3aaf3f92d81e4a8b38ece9591fde82921569e145dc8807c3347a29290850`.
V2 routed DCP SHA256:
`1ac50cfab8c5e22e7b3bc9397411ab864252d04c1a56625e688cb8c90349f816`.

V1 synthesis DCP SHA256:
`ec9dfb12f9c9b26d6a839467e7954dab81ab852f82a7fc5e5be9d8e09b4a1ad5`.
V1 routed DCP SHA256:
`f8d2f9b2cb1468265ee531fde5da7c982783b960bb042a9aed6edb4fcbda6ee7`.
The V1 orchestration script is reconstructed as an additional evidence file and
matches its originally recorded SHA256 exactly:
`6a38c9695181df3ddf10881100446f72b20cb628587a3e53378e415074ae6406`.
Subsequent routes directly preserve their orchestration source as well as the
unchanged Tcl recipe. No original run result or source snapshot was overwritten.

## Unchanged release gates

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Full receiver routing, actual clocks and board delays, CDC/reset,
sustained capture and actual RX calibration precede `.18` reversible canary,
then `.17` via PPU Ethernet with pinned rollback. The final 300-second scan
uses 120 ms valid dwells and blind host GLRT comparison. No radio, PPU, main
branch or primary production HDL gitlink changes occur in this experiment.
