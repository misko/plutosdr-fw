# Private output-slot retirement — DO NOT MERGE

This experiment keeps current output replay acceptance, framing checks, actual
bank publication and retained-controller receipts unchanged. Only private final
slot consumption changes: it waits for known registered output request/ACK
ownership. Nonfinal consumption/refill stays unchanged. No new logical register
or payload buffer is introduced. All 38 parent runtime modules stay identical;
one derived top is added.

The final word is held privately for one extra healthy edge after the real bank
publishes. Bank ownership prevents further RAM writes, and the held final slot
cannot refill on its retirement edge. Common reset cancels pending ownership
and the private slot. Unknown ownership never authorizes retirement. The private
receipt does not authorize publication, job completion or reader release.

## Verification contract

- Exact forward/inverse transformation limits RTL changes to module selection,
  the private readiness expression and its connection.
- 1,024 four-state readiness/ownership combinations, plus unsafe mutations.
- Real output mailbox plus unchanged split-capacity stage: 12 good blocks,
  6,144 checked reads, 420 metadata failures, six framing failures and eight
  resets. Component geometry uses 70-bit metadata; the actual FFT uses the
  production 37-bit output metadata. This is not formal equivalence.
- Read-only actual observer checks request transitions against actual checked
  bank publication, extra private hold, receipt retirement, no same-edge final
  refill and no post-publication bank writes.
- Six new actual boundaries: shared descriptor readiness withheld 128 edges, both raw resets
  during the published private hold, late unexpected FFT status, and a rejected
  final-word certificate, plus publication vetoed despite private replay acceptance.
  Each requires 512 fresh reads and one real release.
- All 65 inherited fault/reset/delay cases and numerical observers remain active.
- Routing requires fresh source-matched main, auxiliary, synthesis and witness
  receipts. Unit tests of route admission are not arithmetic or hardware proof.

Initial component run: 25 passed / one exact-transform failure. The test caught
a truncated source-copy artifact in the new, not-yet-frozen top. Recreating the
complete derived top fixed it before preparation or any actual run. Component
v2 passes all 26 tests; both test results are retained. No parent RTL changed.

Healthy actual generated FFT simulation passes all 64,512 numerical words;
CSV SHA256 `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
Service remains 4,178 clocks / 23.874 us at 175 MHz, below the 5,215-clock budget.
The output observer checks 88,545 cycles, 18 publications, 18 extra holds and
18 retirements. Synthesis passes. Fault-campaign and routing results must be
recorded below before any claim of integrated timing benefit.

## Source pins and release scope

The first auxiliary run is rejected and retained. Its preparation helper inserted
`run_product_retirement_boundaries` at the descriptor terminal rather than the
new output task, creating recursion. It reached the existing 6 ms simulation
deadline after 390.481 seconds wall time; the audit correctly rejected the run
despite Vivado returning zero. No timing qualification uses that run.

`output_retirement_receipt_experiment_v2.py` changes only that preparation call.
The original helper and inventories remain frozen. The corrected auxiliary
inventory is `2849dc5f6915ce16a91640fd74a4081e5e3f9d8f960ffcf58c5f83da1cb41ccb`.
Its 39 runtime modules match the healthy main/synthesis sources byte for byte.
A new preparation test traverses the auxiliary task graph to reject recursion
and verifies entry to the new output task. The first 1,850-test regression
predated this check. Regression v2 passes 1,850 tests but fails the new check
because it counts both the task declaration and call. The corrected test checks
only task bodies and explicitly rejects a mutation recreating the recursion.
Component v3 passes all 28 tests; the final regression contains 1,852 tests.
These harness failures and their fixtures are retained alongside passing runs.

The corrected auxiliary-v2 campaign then reaches the new delay test and is
rejected at 272.618 seconds. The test forces only `output_replay_accept=0`,
while the existing `output_replay_private_ready` still consumes the private
controller receipt. Its P_ACK check correctly faults when the real bank request
does not transition. Treating that deliberately inconsistent handshake as a
healthy pause was an invalid test expectation, not a timing or arithmetic pass.

Focused actual-FFT parent/candidate probes reproduce identical four-line traces:
replay is consumed, output request stays zero, then the existing output-control
fault drives retained/external fault. Both reject at the same simulated time.
The first focused probe forgot auxiliary monitor mode and failed a timestamp
assertion before injection; it is retained but supplies no protocol evidence.
The corrected probes select the actual parent and candidate tops respectively;
the output-only candidate observer is omitted from the parent probe.

Auxiliary-v3 tests a consistent pause by withholding descriptor validity, which
gates both private readiness and actual publication. It also retains the original
inconsistent permission injection as sixth boundary, requiring quarantine and
fresh recovery. No RTL or current publication veto is changed. Its inventory is
`cdfad613915000b25c0c4dec8dd51e7d75fc6ec85a1ca57b3db5937fb1d954eb`.
Fourteen protocol tests pass, including required six-boundary evidence and the
acyclic prepared campaign. Final regression contains 1,866 tests.

Auxiliary-v3 times out with fault still zero: releasing a forced stored
`output_descriptor_valid` register does not restore its old value without a
new procedural assignment. The pause injection is therefore moved to the
derived `output_stage_final_valid` wire, whose release restores its driver.
An executable four-state simulator test reproduces and rejects the stored-
register mutation. No hardware register behavior is changed.

A shorter six-case actual-FFT smoke campaign was added before another full run.
Its first version passes delay, both pending resets and late fault, then the
independent output identity observer rejects direct certificate-only corruption:
the held data still matches its header, so deliberately forcing a bad certificate
contradicts that oracle. The observer remains enabled. Boundary v5 instead
corrupts the final metadata at the stage input; the real identity arithmetic must
produce the bad certificate, and both old/current framing views must agree.

Current helper is `output_retirement_receipt_experiment_v5.py`; final auxiliary
inventory `3abec4b232d23c3c6cbe40f886fa13167c3053d110e7fae50becf047581ac29b`.
All runtime RTL still matches the original healthy main and synthesis inventories.
The final protocol suite has 17 tests (passing); the corresponding full regression
has 1,869 tests. Smoke/full campaign and routing results are still pending here.
Prepared auxiliary-v4 was never launched; failed earlier runs and all helper
versions remain retained. These test-harness corrections do not qualify deployment.

Branch `codex/starlink-rx-only-do-not-merge-output-retirement-receipt`.

- Main inventory `10f92347fddc5e2a150f1fa852418211b58a3f168bc07b782fdf2bb2c10ac767`.
- Rejected auxiliary-v1 inventory `1841e664338af0bfc7ab2cd37042ff2fe6299ecd41285cd14efa1fc7ade0023a`.
- Synthesized DCP `e7b9b489fc84ec05e1a3ef456ae2686d37487a30fda1cb62e4e8853077d26abb`.

Native 60 MS/s fine search and independent 2.5 MS/s inspection remain required
and their receiver sources are unchanged. No full receiver timing, CDC/reset,
actual calibration, continuous RX or real IIO/Ethernet qualification is claimed.
No radios or PPU/main were touched. Primary HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`; deployment remains .18 canary then
Ethernet-only .17, with .14/.20/.21 excluded.
