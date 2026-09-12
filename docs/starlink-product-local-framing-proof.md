# Product-local framing publication — experimental, DO NOT MERGE

This candidate removes the product bank's own same-edge framing fault from
only that bank's separate final commit permission. It retains the original
global fault expression, original public permission, guard-local vetoes,
other-bank publication veto, diagnostics, sticky faults and quarantine.
Native 60 MS/s fine search and independent 2.5 MS/s inspection remain mandatory
full-receiver release requirements.

## Exact change and four-state argument

All 41 private-replay parent runtime modules are byte-identical. Two derived
modules replace the instantiated top and product bank (43 runtime modules).
No clock, pipeline state, FFT arithmetic, coefficient, cursor, RAM access,
descriptor, reader or ownership synchronization is intentionally changed.

Let A be input acceptance, F local framing-valid, and O all other original
publication conditions. The original actual publication requires accepted
final framing and O with the bank's current framing fault A AND NOT F absent.
When publication is possible, A and F must both be known one, so its own fault
is zero and removing it from O changes nothing.

There is a Verilog four-state caveat: an "if (!F) ... else" enters the else arm
when F is unknown. The original full permission then becomes unknown and
prevents publication. A naive removal could publish. The derived bank
therefore explicitly requires F === 1 before publishing, alongside O. The
original diagnostic behavior is retained even for unknown framing.

The original full permission remains connected and observable; every other
consumer still sees its original expression. The separate product-only permit
is not public evidence of success. Only the real request toggle transfers
ownership. This is source-derived cofactoring, not delayed fault suppression.

## Completed checks before routing

- Exact forward/reverse transformations constrain both source changes.
- 4,096 four-state combinations on a four-word bank cover both position bits,
  LAST, metadata certificate, external permission and input-valid.
- 2,304 native-width cases exercise all nine position bits, good/bad/unknown
  positions, LAST/certificate and external permission.
- Every existing bank control/register is compared with an original reference.
  Fresh blocks/ACKs verify recovery. Removing known-good framing or bypassing
  other authorization is rejected by the mutation tests.
- Healthy actual FFT simulation: 64,512 numerical words, unchanged CSV
  df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8,
  4,178 service clocks, 18 actual product publications.
- The independent actual observer executes the original bank's nested
  procedural publication predicate and compares the resulting real request
  register every edge; it also checks global fault decomposition.
- Focused actual simulation: six current local framing/reset cases pass with
  144,549 checks, 24 publications, six local rejections, fresh 512-word recovery.
  Bad final position/certificate/LAST and both raw reset inputs are covered.
- Final version-2 regression: 2,232 tests pass, including auxiliary-witness
  rejection and matched-stimulus tests.
  Full inherited actual campaign and physical results are recorded separately.

Initial component test construction failures remain in the evidence: overly
broad parameter-token replacement, exact trailing-newline differences, and
missing good-framing/external-veto vectors in the native-width mutation test.
These were corrected before preparing any actual FFT/synthesis source. No
fault predicate was weakened to pass them.

The first full actual campaign stopped at the inherited delayed-publication
case: that bench forced only the original permission low, leaving the new
cofactored permission undelayed. The original actual-ownership assertion caught
the mismatched stimulus at 3,479,800,288 ps. Version 2 adds precisely one paired
force/release to the new permission; it changes no RTL or observer assertion.
Strict inventory tests reject missing/additional injection sites. A focused
rerun exercises the original 128-clock hold plus all six new cases and passes:
150,694 checks, 25 actual publications, six local rejections. The failed full
run and both prepared harness versions remain preserved.

## Pins and deployment policy

Source FW c8cd81e6dbcdb2025c10ec2e0ca02bc96699e4d2;
HDL 37b485b5b8e25d14e468ec222b16f64b7e71c8cb.
Branch codex/starlink-rx-only-do-not-merge-product-local-framing.

Main inventory 4ec0871824ac7f60583ee184be0c886611be508661e81143c2ef5ee2baa9ce24.
Accepted-harness auxiliary inventory
84f9bea889dbbbaf2cb8abca67bf7f3d2794da48f6e575397a37e0babd97581f.
Failed original-harness inventory
78a8f7e6c6100a2dfa3558f64889ed103c26c6124ecd0f7c2f0871d2213dbe75.
Synthesis DCP 9325b0e7a8711756c5b6106ae225ca21c1e707cf4fce16e4829a4109d5dbd47e.

Do not infer timing closure from these functional results. Require complete
source-matched actual qualification, route the frozen 100/175 MHz subsystem,
and assess all relevant endpoints and aggregate timing. The board still uses
100/200 MHz, including the 200 MHz IDELAY reference; a short island service
measurement does not establish continuous receiver throughput or justify
lowering the board clock.

Keep the primary HDL gitlink unchanged. No radio or PPU/main changes.
Full receiver/CDC/reset/timing, calibration, continuous native RX/IIO/Ethernet,
and real-world comparisons remain open. Deployment remains reversible PPU to
.18 canary first, then Ethernet-only .17. .14/.20/.21 remain excluded.
