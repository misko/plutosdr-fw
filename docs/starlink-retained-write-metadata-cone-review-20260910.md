# Retained write-metadata cone: read-only bounded recommendation

Status: design review only. No RTL, tested helper, observer, constraints, vendor execution or other lane was changed. Parent approved publication of this analysis and preserved counterexample evidence, not implementation. No revised RTL experiment is authorized before the separate offered-summary physical result and a new source-specific review. This report is not authorization to combine the retained and checked candidates.

## Evidence and exact scope

The reviewed route is `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-control-route-parent.rza0KS8U`. Its input synthesis DCP is `193cf14408ca768d403f1ef4bba913c07bf24a94bb88fb647941b95a03dd1482`; routed DCP is `2ec838aa9a0a6f5ee297e506a07a842a1aa597f0e08241dc5bbf93b9493c1f3f`. The [same-domain top-20 report](/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-control-route-parent.rza0KS8U/route/island_175_island_175_max.rpt:355) has SHA-256 `31d824f0f861803dbd3d9eebdfa797472b0848ea06f618623c17fe5dd059abcb`.

Five of those twenty paths launch at product-bank `metadata_in_hold_reg[14]`, rather than the fifteen read-side `metadata_out_hold` paths:

| Destination | Slack | Data delay | Logic / routing | Levels |
| --- | ---: | ---: | ---: | ---: |
| forward_committed D | -2.594 ns | 8.301 ns | 1.958 / 6.343 ns | 11 |
| ROM block_start_index[49], [50] CE | -2.422 ns each | 7.847 ns | 1.710 / 6.137 ns | 9 |
| ROM block_start_index[42], [43] CE | -2.403 ns each | 7.828 ns | 1.710 / 6.118 ns | 9 |

The in-progress read-side offered-summary candidate was neither edited nor used as the source of this recommendation. All seven source files below were compared byte-for-byte with the actual synthesis `inputs/source_snapshot`, not merely assumed to match the worktree.

## Exact dependency

1. The [mailbox hold/equality/framing logic](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_mailbox_owner_view.v:95) compares all 70 metadata bits against the first accepted word. Lines 124–130 also check ordinal and TLAST. The current fault is exactly explicit-mode accepted malformed input, not every stalled offer. Preserve that scope; do not silently replace it with an offered-bus contract.
2. [Top external and completed-input faults](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_closed_candidate/starlink_pss_fft_retained_output_impl.v:242) both include `product_bank_framing_fault_now` (lines 244 and 266). This is genuinely live while earlier product words are being written and later forward FFT returns are arriving.
3. The [result guard](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_closed_candidate/starlink_pss_result_guard_owner_view.v:213) uses that cause in completed-return/final fences and forward retirement (lines 252–262). The top feeds exact forward retirement plus actual product-bank READY into the [joiner](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_closed_candidate/starlink_pss_fft_retained_output_impl.v:352). ROM input_accept then guards the first-block metadata update at [ROM lines 138–154](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/baseline/starlink_pss_kernel_rom.v:138).
4. Independently, [top lines 505–506](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_closed_candidate/starlink_pss_fft_retained_output_impl.v:505) set forward_committed directly from combinational qualified final commit and destination READY. That retained token participates in product publication, readiness/ACK selection and handoff at lines 240–250 and 387–400.

The routed path traverses the balanced equality leaves/groups, mailbox framing/current-fault aggregation and guard retirement logic; its instance placement under epoch_barrier/retained_owner reflects synthesis optimization, not a source-level exemption.

The local final write remains the essential integrity boundary: [mailbox lines 138–174](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_mailbox_owner_view.v:138) permit private malformed RAM/cursor updates but latch fault, and only correct final framing plus explicit authorization toggles ownership. A metadata mismatch on an interior product word is not made harmless by being in the forward phase.

## Pulse-only proposal rejected: ACK timing is also part of the lifetime

The initial proposal was to set the existing forward_committed token from `guard_commit[0]` rather than re-evaluating `return_commit_valid && result_destination_ready && !next_inverse`. **That one-change proposal is rejected.** Root identified the missing ACK dependency before any implementation by this agent. The unmodified initial report (SHA-256 `b97e2804b5c22bdda2c7d213b98ef64c8a16e07a347268f8127262cdca478cdb`) is retained in `docs/evidence/retained-write-cone-review-v1/initial-proposal.md`.

This is a real sequential cut, not a delayed fault substitution: [guard line 287](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_closed_candidate/starlink_pss_result_guard_owner_view.v:287) already stores `commit_pulse <= final_commit`, where final_commit retains every original same-edge raw/write-framing veto and actual destination handshake. The top already connects that output to guard_commit[OWNER] at line 323.

Timing convention: n is the edge of the legitimate final forward retirement into the joiner. With the exact enabled REGISTER_OPERANDS=1 configuration:

| Edge | Earliest healthy final-token action |
| --- | --- |
| n | Guard final_commit; ROM/join capture; old forward_committed sets |
| n+1 | Existing guard_commit[0] is consumed; proposed forward_committed sets; operand register captures |
| n+2 | Arithmetic multiplier registers capture |
| n+3 | Arithmetic sum registers capture |
| n+4 | Product output registers capture |
| n+5 | Product mailbox can first sample that final token |

This lower bound follows the [joiner's registered ROM](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/baseline/starlink_pss_forward_kernel_join.v:63), [operand register](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/baseline/starlink_pss_spectrum_product_operand_register.v:52) and [three arithmetic stages](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/baseline/starlink_pss_spectrum_product_bank_arithmetic.v:190). Stalls cannot shorten a no-fall-through token pipeline. It is source reasoning, not a new measured simulation.

The final-product latency bound alone is insufficient. At edge n the guard sets awaiting_ack and emits commit_pulse. During n..n+1, delaying forward_committed leaves it zero, so top lines 249–250 and 316–317 select kernel_ready && product_bank_ready, commonly one. At edge n+1, guard line 378 may clear awaiting_ack while product_bank_valid is still zero. This is an actual ownership/ACK violation, not merely a private latency difference. A test must observe the exact real owner_ack_accept pulse, not just later controller phase or final bank publication.

Root independently executed the counterexample at `commit-pulse-ack-parent.xkh8BtdU`: baseline passes; pulse-only mutant fails at cycle 2736 with forward_committed=0, guard_commit[0]=1, product_bank_valid=0, awaiting_ack=1 and mailbox_input_ready=1. Its first fatal is forward guard ACK before actual product-bank publication; the later final-inventory fatal is secondary to deliberate early stopping. Root reports the diagnostic owner terminal 0 because it correctly detected the expected mutant failure, with source pins unchanged. No new design is qualified by that diagnostic.

## Smallest revised candidate: registered completion plus an independent ACK-phase fence

A plausible zero-new-state design must make **both** bounded changes, with a separate source-specific proof before authorization:

1. Consume registered guard_commit[0] for the retained forward_committed token one edge later, only in the enabled registered branch, keeping reset and new-job clear priorities literal.
2. Export the forward guard's already-existing owner_awaiting_ack observation (top line 325 currently leaves it unconnected). Consider a forward completion-phase view `forward_committed || forward_owner_awaiting_ack`. It must cover the forward destination/guard READY mux, choosing product_bank_valid rather than writable kernel/product capacity. The inverse owner READY branch remains unchanged. Do not use health-qualified combinational ACK itself as capacity.

This second seam is larger than one READY replacement. Audit **every** old forward_committed consumer: head-fault classifier at line 240, forward_handoff_ack at 246, destination READY at 250, guard READY at 317, and actual product_commit_authorized at 387, plus all resets/clears. In particular, if only READY is changed, a deliberately early bank VALID with a malformed head during n..n+1 can reach the guard while line 240's delayed forward_committed still suppresses the old independent head fault. The phase view must preserve that immediate classifier too. One candidate is to use the same registered completion-phase view at all original combinational consumers, while the delayed token is solely its persistent tail; then prove that the phase view reproduces the original token's authority exactly. No such replacement has been implemented or proven here. Do not hide this interval with an observer mask or assume an early/forced head is correct. X/Z, source/phase faults, reset and head/lease corruption require explicit tests.

At n, awaiting_ack is registered on the actual original qualified final_commit, so the selector switches to reader ownership without waiting for n+1. After the real ACK clears awaiting_ack, the retained forward_committed token keeps the selector in the ownership phase until the existing next-job clear. No extra register is required; the conceptual cost is one observation connection and a small registered-state OR/mux change. A formal/actor obligation is that this selector equals the old mux-select on every reachable edge, including faults, reset, next-job clear and the retained inverse/forward overlap. It is not enough to prove only nominal final-product latency. Four-state and forced guard/current-event cases must also be addressed explicitly; do not infer authority from a pulse that is not known to represent the correct owner's actual handshake.

Expected, not yet tested: zero added FF/RAM/DSP, one edge of private forward_committed latency, no additional healthy arithmetic/publication/ACK/service cycle. A later fault may coincide with consuming a previously valid pulse, but the unchanged current/sticky publication/ACK/quarantine fences still apply. No edit or execution of this revised design has been performed.

Do not reattach the wide current fault predicate to the new token D pin. The current fault must still veto the actual bank publication/ACK through their existing paths. The full fault cone still ends at the guard's existing commit_pulse, awaiting_ack and fault registers and public fences; a revised candidate may remove the extra combinational propagation to forward_committed only. The same limiting path may remain at existing awaiting_ack/commit_pulse D pins after optimization. It does not fix the four ROM CE paths or guarantee timing closure.

## Separate ROM CE option, not part of the first cut

Keeping exact ROM acceptance is required. Gating away write faults from forward_retirement would change arithmetic acceptance on a corrupted product edge; simply using private_valid violates the existing guard-retirement equality.

If the four metadata CE paths remain next, a narrow representation-only option is 69-bit speculative/retained block metadata plus one selector, without the word-prefetch or checked-bank union. The [already studied recurrence](/tmp/starlink-rom-prefetch.j829ht/fw/hdl/library/starlink_pss_acquisition/starlink_pss_kernel_rom_read_ahead.v:118) provides a candidate pattern, not transferable retained-lane qualification:

- Speculate {start64, exponent5} only when input_ready && at_block_start, excluding current acceptance/framing.
- Preserve the old visible tuple on all other cycles with retained storage.
- Select speculation only on the exact original nested healthy input_accept/at_block_start branch, preserving procedural X/Z behavior.
- Keep output_valid, every accepted tuple, current errors, counters, final arithmetic integrity and all ownership predicates exact.

Logical increment: +70 bits (139 versus original 69), no new RAM/DSP or healthy cycle. The wide metadata-register CE loses the upstream write-fault dependency; a one-bit selector still has that dependency, and selector-Q now precedes the ROM identity comparison. It may merely expose a new timing bottleneck. Word-only prefetch does not address these metadata-state endpoints. This option needs its own source inverse, whole-state proof and physical measurement; it is not implied approval to graft the old ROM module wholesale.

## Required bounded proof/tests before any implementation qualification

- Independent actual controller/real guard/join/product actors: exactly one registered pulse per final forward retirement, no pulse for inverse, no lost or stale token across next job/common reset/paused clocks. Assert n+1 completion token and no legal final bank take before it. On every exact forward owner_ack_accept, require real product_bank_valid plus the original independent identity/current-health conditions. Preserve the pulse-only cycle-2736 failure as a mandatory negative. Prove the new READY-phase selector matches old behavior across commit/ACK/new-job boundaries. Do not force forward_committed to prove this.
- Preserve actual exported product READY: interior/final finite stalls, status-held final, simultaneous new raw status/frame/output/input/duplicate/source faults and overflow. Check raw same-edge product framing fault, final request toggle, public ACK, lease/reuse and full numerical product tuples, including final held overflow.
- Mutate each of the 70 metadata bits, ordinal and TLAST at interior/final accepted writes; move fault onset before/on/after guard final retirement and before/on actual final product take. Distinguish VALID while READY=0 from accepted malformed writes as the old bank does. Keep explicit four-state bubble/control semantics.
- Directed counterexample to a naive global one-cycle fault delay: with forward_committed already true, corrupt the final product's metadata while VALID/READY are high and fault-Q is still zero. If current framing is removed from final publication, request_toggle may publish the poisoned bank before quarantine. Even retaining that local veto does not justify claiming old guard/ACK current-fault equivalence after changing their upstream fault timing.
- Test pulse-reuse-specific mutants: raw last/return_private_valid instead of qualified commit pulse; wrong owner's pulse; stale pulse across reset; removed actual READY qualification; early forged product final. Boundary abuse that collapses the n→n+5 lifetime must be rejected locally, not counted as healthy latency evidence.
- For ROM metadata-only work separately: unconditional old block-state/output equality, all invalid/X/Z bubbles, first/last block, rollover, occupied stalls and reset/flush; missing selector/retention/current-fault mutants. Keep independent original numerical and retirement shadows.
- Complete LS-aware combinational graph with immediate-driver alias normalization: prove the intended forward_committed cone no longer reaches raw write metadata in the proposed mode, while original current-fault reachability to final bank ownership and ACK remains. Positive backedge control restores the old D-pin connection. ROM option additionally needs positive selector reachability and negative wide-CE reachability. These are graph checks, not timing qualification.
- Actual campaign, if separately authorized, retains the original absolute 5215-cycle cap, accepted tuple/numerical/current-fault/CDC/status/reset gates. No expectation reduction or clock exception follows from this analysis.

## Lesson from the checked-lane failure

Checked route91981 still failed -8.324 ns on expected_product_metadata[0]→origin_valid, 26 levels/13.941 ns. Its producer/read validation stages did not eliminate the separate independent origin/ACK/start qualification cascade. The lesson is to preserve each real authority check, terminate its consumer at an existing registered receipt where safe, and inspect the complete resulting cone. Do not gather every healthy/lease/current-fault predicate back into one control enable. Conversely, do not replace independent origin evidence with aliases just to shorten it.

Here pulse-only reuse of final-commit Q is rejected by a real ACK counterexample. The revised completion-token plus registered ACK-phase selection is proposal-only and requires its own proof; the ROM representation change remains a separate optional experiment. None is a wholesale checked-bank/read-queue union, a claim that read-side offered-summary fixes write-side faults, or a physical pass.

## Reviewed source pins

All paths below are under the frozen retained synthesis's source_snapshot and byte-identical to the corresponding high-rate60-paired source read during this analysis.

| Source | SHA-256 |
| --- | --- |
| closed candidate implementation | 1d01972d11486772b627a3afdd594f06e41c0f98b830288e93b371af0506ef1e |
| closed candidate result guard | 53c336df4dd378a27b12f7c4d382d25290c81c0881b8e6c4f914faa67482d320 |
| mailbox owner view | de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6 |
| baseline forward join | 87e40b3cc9025502c05d2afbd6b0d9658618cd7204d4fd8ddc3f0ba74e68843a |
| baseline kernel ROM | 0b4ee87d93d61c6fa12ee9992aa517a3a8be568835075531d9af4453f4ec80e5 |
| baseline operand register | dead8e465b4bd982cebcab0c4a4e7eb4f3b20c038938f74c7663a79e0779893d |
| baseline arithmetic | 515d29534dab921601c37564ad8a9957eed9befb9dff2e1c8c5f1f79fc6b5f70 |

The separate historical ROM recurrence file read for comparison has SHA-256 d35020ea933637d96f1d197322110d4c436566e9e03870732082a55dc7d2cee4; it is not in the retained source closure. No tests or vendor runs were performed for this read-only report.
