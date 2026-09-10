# Producer-local product publication: independent offline review

Firmware experiment only; DO NOT MERGE. No receiver promotion or radio access.

The routed ROM-prefetch experiment still fails setup at -1.360 ns. Its worst
reported path starts at product metadata, crosses input checking and reaches
product-bank publication. This alternative changes only the authorization
sampled by the producer's final write; it does not delay the global fault tree.
It remains separate from the inverse sealed-bank/dual-clock alternative.

## Reviewed implementation and limits

Two additive modules default off. The original top, mailbox, input/result
guards, FFT, joiner, ROM and arithmetic remain unchanged. Whole-source inverse
tests restore the exact original modules at HDL
`efc97d8ac92578e1e37eb0bb28c64780b86cf76a`.

The new final predicate retains duplicate-start, sticky input fault, synchronized
source fault, vendor, fast, kernel, overflow, product-bank current/sticky and
result faults. Original global reasons, authorization, handoff ACK and completion
remain literal. No register, RAM, DSP or nominal cycle is added by this cut.
That source-level observation is not a mapped-resource or timing result.

Source review of the actual wrapper and guards supports the conditional argument:
`forward_committed` follows a qualified forward final; closed input cannot have
new framing/delivery errors, but duplicate-start and retained faults still matter.
Product producer readiness excludes consumer VALID, making the handoff check
irrelevant to that producer-final edge. Handoff checks remain live during ACK.
The complete controller must still execute these invariants in the actual-core
test. The local bench manually assigns `forward_committed` after naturally
completing the real input checker, so it is not full-controller reachability proof.

## Parent repeat

Original process **20741 exited 0: 26 tests passed in 24.70 s**. All five reviewed
source hashes matched before and after execution. Artifacts:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-fence-parent.DYMqfY0D`.

| File | SHA-256 |
| --- | --- |
| New top | `8923b42b3574fc1418eee99c5f5819f173c73fbf7b8bb65726a7ab3a5d8a6f7c` |
| New mailbox | `e4f4c56ddab8f05d0f9b9da9a75f975e11cb8ad441581c904bfb094f3013982f` |
| Testbench | `56fe0f3f86c91370607a6fe51377e2ee52ebd014a9d3ea54b7b0eab797cbc9a6` |
| Python tests | `dc6cef6cb587366531319c5ee72ae4f5204ab24aeb4cad86cc6eda11e70e0f07` |
| Inverse recipe | `816cc8e19ebb16ad21f964a06173d2c829c3c8751df61fbdcc4f34465e7d72e0` |
| Parent log | `d616955badf08675ffc7dbaed2e79060e98cba914a3c640456866a7f3faf51d6` |
| Parent JUnit | `e768169d19e1fbe64fa71cb4fcf0204ae399eb0a3398f61fc8fbc72904f1f9af` |

Portable parent receipts are in adjacent `20260910-product-final-fence-parent/`.
The source inventory and log are byte-exact copies. The XML copy adds only a
trailing newline (independently compared after excluding that final byte); its
archived hash is `e2e919c74cbe3a8a4e7bc9747750ce468ce76e1383f1b089fac8c25d81980537`.

At depth 512, both disabled and enabled modes execute 89,228 public-state/RAM
checks, 15 sampled final authorizations, 512 inverse reads and 515 stalls.
They retain all 70 active-input bit checks, 71 malformed-final cases, seven
current-fault rows, four X/Z final rows and two epoch resets. Three deliberately
nonsampled private-authorization differences are permitted; public comparisons
remain unconditional. The four-word variant is deliberately too short for the
512-word guard: its final word stays poisoned/owned, not a healthy inverse pass.

Parent review found a missing sticky-only witness. The corrected bench pulses a
real duplicate after completed input, deasserts that pulse, then offers the valid
final while the real checker retains its fault. All other local veto terms are
checked clear. Removing that sticky term now fails the sampled-edge assertion,
as do six other missing-veto mutants. This isolates the local term; the full
wrapper would additionally latch its global fast fault after the duplicate.
Earlier 25-test and 85-test results are retained, not substituted for this repeat.

Additional tests reject unconditional publication, an intentionally broken
active-input caller, invalid -1/2/X/Z options and lost top-to-mailbox flag binding.
The full-top reset shadow uses a parked FFT stub: no active/paused-clock reset,
vendor arithmetic, capacity, physical CDC or board qualification is implied.

## Next gate

Authorized next: additive offline actual-core preparation and observer tests.
Preserve all old numerical vectors, status/CDC/ROM observers and acceptance
criteria. Attach the sampled-final and controller invariants to the real top,
verify complete hierarchy binding and exact source closure, and reject weakened
observers through directed mutations. Freeze and independently review preparation
before any vendor execution. No synthesis, route, receiver image or flash is
authorized by this local result. The main runtime HDL gitlink remains unchanged.
