# Private kernel ordinal — DO NOT MERGE

This experiment starts from the better measured private-capture reference,
FW `fcc3dc20205243adf4fbfcf6a43312b35d7a3aa6`, HDL
`c25126a2ecf391344c6d50b483aef2ee5217ba26`, routed at -1.969 ns. It deliberately
does not combine the later staged inverse-final experiment (-2.379 ns).
That work remains preserved on `codex/starlink-rx-only-do-not-merge-rom-prefetch`.

New FW/HDL worktree branch: `codex/starlink-rx-only-do-not-merge-kernel-ordinal`.
Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/kernel-ordinal-reference-worktree-v1`.
No main branch, production HDL selection or radio is changed.

## Implementation contract

The result guard exposes a private forward offer from its owned, held return.
Nonfinal returns retain the existing completed-input qualification; final
returns must also have the original full structural final qualification,
including status/exponent/final fence. A last word cannot advance early while
waiting for a legal first status. Current faults still independently veto the
original public forward-retirement signal.

The joiner passes this separate offer to the ROM, with the same actual capacity
and registered epoch-quarantine gates as public input. Default-off
`PRIVATE_ORDINAL_ADVANCE` is enabled in the experimental registered integration.
Only the hidden nine-bit expected-bin counter uses the private handshake.
Its increment wraps at 511. Public input acceptance, coefficient output-valid,
per-bin sequence/metadata checks, error flags, block completion, expected next
block identity and real-backpressure behavior retain their qualified paths.

Every public acceptance must have a private offer. In a healthy epoch both
handshakes must agree. A current fault may reject the public beat while the
private counter advances; this divergence requires quarantine until common
reset/flush. The caller's registered fast-fault gate prevents any following
offer, and immediate product/output bank authorization fences still prevent
publication. This is not permission to use private offers as public validity.

## Verification

Initial source/lint and ROM controls pass **11 tests in 0.66 seconds**. The ROM
test compares the original pinned implementation, both private-payload settings
and the ordinal candidate cycle-by-cycle: all public flags/readiness/validity
and every valid/stalled payload agree across 4096 lookups, invalid-input churn,
four malformed cases, backpressure and flush recovery. A separate private-only
offer advances the counter without acceptance, valid output or block completion;
the modeled caller withholds further offers until flush, then a fresh lookup
matches the reference. Four mutations (no advance, ignored backpressure,
private publication, missing flush) are rejected. Full caller quarantine is
verified separately below, not inferred from that local model.

Actual generated-FFT verification passes on the first attempt in **116.52
seconds**. All **64,512 numerical records** match the pinned reference, and the
CSV is byte-identical to the private-capture baseline. Six service intervals
remain 3659/3659/4927/11727/3659/3659. The unchanged 5215-cycle cap applies to
the five qualifying contexts; the deliberately 9000-clock-stalled reader has
no real-time service claim. Every earlier reset/fault/admission/completion/
replay/writer/capture case passes.

Five added actual cases cover vendor fault, product-bank framing fault and
duplicate status on a nonfinal private offer, late first legal forward status,
and 16 clocks of held-final kernel backpressure. The three fault cases observe
exactly the private counter advance with no public acceptance/valid/completion,
then no offer, publication, reuse, reads or release after quarantine. The two
healthy cases wrap bin 511 to zero only at actual acceptance and each complete
512 correct reads/one real release. Every healthy cycle checks private/public
handshake agreement, and every live cycle checks exact counter advance/freeze:
**9216 healthy advances and 98,246 holds**. Receipts including aborted jobs:
105 admissions, 77 completions. Descriptor checks remain 32,616 loads, 74,846
holds and 18 healthy accepted captures. Full-width timestamps and both stopped-
reader resets pass with a fresh 512-word result.

Source-matched synthesis completes in **100.07 seconds**, sources unchanged.
**397 combined regression tests pass in 51.74 seconds**: the 382-test private-
capture baseline plus five new ROM tests and ten ordinal evidence-parser tests.
The separately retained staged-final branch has a different test inventory;
its tests are not silently claimed as part of this baseline experiment.

Source-matched route completes in **52.15 seconds**; the independent audit
verifies sources/checkpoints, all clock pairs, summary, routing and resources.
Measured timing **regresses** and this candidate is not promoted:

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private-capture reference | **-1.969 ns** | **-813.676 ns** | **914** |
| Private ordinal on that reference | -2.347 ns | -967.661 ns | 1093 |

1093 / 13765 endpoints fail setup. Hold +0.071 ns and pulse +1.830 ns pass.
8347 nets fully route with zero errors. Resources: 2748 LUT / 5653 FF / 21 DSP /
15 RAMB18. Five critical CDC findings, 208 warnings and 114/124 unconstrained
I/O remain. Device, actual FFT, diagnostic 100/175 MHz clocks and route recipe
are unchanged. No timing waiver or full receiver/board signoff is claimed.

The worst path is now held phase → input metadata selection/comparison →
certified input beat → cutover current fault → inverse guard
`fault_reasons_reg[0]/D`: 10 levels, 8.009 ns data delay, including 6.313 ns
routing. The forward guard's corresponding fault bit follows at -2.315 ns.
The kernel index is no longer the worst endpoint; that does not establish
timing closure of every kernel path or a benefit from this composition.

Next investigate source-local fault aggregation. Existing offered-input fault
summaries avoid some certified-input feedback for the common control summary,
but the detailed guard fault bank still sees the full chained external fault.
Any replacement must prove equivalence to the original predicate, preserve
exact fault-reason accumulation including unknown-input handling, and retain
current publication/ACK vetoes. Do not simply delay the complete fault signal
or clear private state to hide a fault. Use the better private-capture reference
for the next isolated comparison, then actual FFT verification and routing.

Inventory: `727eaacff7b4781dbf04672bdd90681033906c9591d7cd669378e5c50c4ac1ed`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Synthesis DCP: `0929abdda3a30213837631513905a02c4b364075004dfe25ab766a700b19a23f`.
Routed DCP: `8ecbf98aa360e8d0849259bc8b8243a36ea85a1c1578fe33f453bddebfdfe9d6`.

## Unchanged full release scope

Native **60 MS/s fine search** and independent **2.5 MS/s CI16 IIO inspection**
remain required. Full receiver route/CDC/reset/board constraints, sustained
capture and actual 60 MS/s RX calibration precede `.18` reversible canary, then
`.17` PPU Ethernet deployment with pinned rollback. Final verification remains
the 300-second, 120 ms valid-dwell scan and blind host GLRT comparison. This
isolated FFT/buffer experiment does not establish those deployment gates.
