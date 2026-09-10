# Data-only payload bubbles and balanced ROM identities: functional result

Both actual-core default/registered runs pass, and both complete control CSVs
byte-match their preceding held-preflight runs. The new independent option,
numeric, stall and mutation tests pass. The expanded oracle sweep is **752
passed, 10 explicit physical skips, seven missing-Linux-source failures**;
it is not reported as wholly green. No synthesis or route was run for this
source. The previous −1.614 ns timing failure remains immutable and unpromoted.

Tested FW `35d2a0b0d0828d7e941d77de71bb16fde6701137`, HDL
`b7dac8024d5870c9b2909188dfa0a7766c3f7a39`. All actual frozen RTL and benches
match this source, checked again after both runs. No RTL correction occurred
after the initially reviewed four-module delta or after source freeze.

## Exact scope and invariants

PRIVATE_PAYLOAD_BUBBLES defaults off in the joiner and product. The opt-in
joiner updates only captured I/Q under existing input_ready, including bubbles.
The product updates only its four numerical multiplication registers under
product_stage_ready. All validity, metadata, sum/output enables, rounding,
overflow, checker events/state, guard retirement, final commit and ACK logic
remain unchanged. Both options are enabled only by the experimental wrapper's
REGISTERED_SCHEDULING setting. A held final may sample private payload, but
cannot acquire an additional logical acceptance or valid arithmetic token.

An occupied stalled joiner has input_ready=0 and holds its payload. Any valid
joiner payload must match the frozen old joiner. On a ready product bubble,
product_valid becomes zero; a simultaneous sum consume uses the preceding
valid numerical payload. When product_valid is one, all four numerical
registers match the old implementation, including stalls. Thus every product
output bit remains cycle-exact even when output_valid is zero. Only invalid
joiner I/Q and invalid internal multiplier words may differ. Kernel words,
all other joiner outputs, and every control/reason bit are compared regardless
of validity. Epoch/reset/poison and bank ownership behavior is untouched.

BALANCED_BLOCK_IDENTITY_EQ defaults off and passes through the joiner to the
ROM. Both complete 64-bit identities use 22 kept three-bit/last-one-bit leaves,
four kept reduction groups and final AND. Current versus expected-next block
selection, all five exponent bits, ordinal, TLAST, history and original 64-bit
+447 arithmetic remain exact. No register, hash, latency or delayed check.
Strict whole-module inverse adapters restore all four modified bodies to
`7ee87258`; three frozen reference modules differ only in module names. The
whole actual bench also restores literally after removing additive shadows
and the new receipt; none of its earlier stimulus or assertions changed.

## Executed evidence

The 19 new tests plus 17 historical inverse/identity tests pass (36 total).
All eight independent joiner/product/comparator option combinations pass
2,315 chain checks, with 2,073 occupied joiner and 2,071 occupied multiplier
observations each. They include hostile/X invalid I/Q, full four-stage stalls,
drain/refill, reset/flush while occupied and last-to-next block history/wrap.
The product-only option has its own invalid-operand witness; it does not rely
on the joiner's bubble option to exercise private numerical changes.

Separate product probes compare every external bit against frozen RTL and
against independent signed 64-bit round-to-even arithmetic: 1,608 checks,
1,221 occupied-stage observations, 492 X-input bubbles and 50 positive-clipping
outputs per mode. Cases include both signs, ties, below/above half and the
negative representable boundary. No unsupported negative-overflow claim.
Each ROM mode passes all 256 bit/comparator/ready rows and 67,879 state/output
comparisons, including exponent/framing errors and original modulo-64-bit
stride wrap. Both bit63-omission mutants, joiner and multiplier occupied-
overwrite mutants, and invalid-product-token leakage are behaviorally rejected
at their required witnesses. These fast benches are not numeric FFT models.

Fresh Vivado 2022.2 actual-core runs at 100/175 MHz retain the original 44
healthy-block/10-fault numerical receipt: 24,064 forward/product words and
22,658 inverse words, including 130 explicitly provisional prefix words.
Nominal maximum admission intervals remain 4,540 default / 4,548 registered
clocks. All prior guard/reason/retirement/handoff/reset checks, 84 preflight
boundary rows, 12 expected-cache rows and 12 active-corruption cases remain.
The accepted 44/8/60 preflight private counters are unchanged.

The added independent frozen chain passes 324,592 checks in default mode
(37,580/37,803 occupied join/product observations; zero invalid differences),
and 586,260 in registered mode (70,348/70,573 occupied; 135,008 invalid I/Q and
134,753 invalid numerical-register differences). No checker event or reason
predicate in the reference uses a new option or comparator.

Expanded oracle failures all occur while opening absent files in uninitialized
Linux gitlink `4357f41a721df9d89a66be7a2a3f921a71d46bad`: five map-driver tests,
one DMA backend test and one pilot-driver test. Those tests and the gitlink are
unchanged from the pre-study pin. Exact IDs/tracebacks and all ten explicit
physical-skip reasons are retained in `full-oracle-regression.log`; no new
skip or out-of-scope dependency initialization was introduced.

Early unit runs are retained too. v1: 9 passed/10 failed due to test-task
double-send after changing READY/flush before allowing combinational settling.
v2: 17 passed/two failed solely for a missing product-only invalid-difference
witness (legacy joiner held identical operands). Settled admission and an
independent disabled-product-token lookup fixed those harness defects without
changing RTL, weakening comparisons, or discarding failed outputs. Ruff and
diff checks pass.

## Cost hypothesis and frozen receipts

No added logical FF/DSP/BRAM or cycles; invalid-cycle arithmetic switching can
increase and power is unmeasured. Two unshared balanced trees describe 54 LUT
leaves/reductions, not an additive mapped-resource estimate. Prior synthesis
changed preliminary AREG=0/MREG=1 into final AREG=1 DSP mappings; the prior
worst path ended at CEA2. A future separately approved synthesis must inventory
final AREG/BREG/MREG and CE driver nets to distinguish absorbed joiner readiness
from numerical-stage enables. Neither dead parameter-specialized nets nor
source simplification proves actual path removal. Timing/CDC/I/O, normalized
scores, full receiver, pilot export and RF qualification remain outside scope.

Original default session 12589 exited zero at 2026-09-10 04:09:49 UTC;
registered session 51297 exited zero at 04:11:23 UTC. Runs are
`/tmp/starlink-completed-input.5EaJuD/payload-default-v1` and `payload-actual-v1`.
Raw receipts are under `project/fft_bank_owned_slice.sim/sim_1/behav/xsim/`.

| Artifact | SHA256 |
| --- | --- |
| Wrapper | `5d2d72fcb8e98fd75f585e719a358b7afdc172214312f9250d97b7702c009677` |
| Registered raw log | `63304a7174b70821f3c4f6f34cf23ae582dd899826eea0dc4462223f3fa825a5` |
| Default raw log | `2e0fcdd51f410f04442459f1a54abb4079d394c7274d43075ff3a53e92b7e4aa` |
| Registered original CSV | `25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122` |
| Default original CSV | `b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d` |

Archive `hdl/library/starlink_pss_acquisition/evidence/payload-bubbles-v1/`
contains frozen sources/vectors/references, actual logs/scopes, unit and mutant
evidence, failed harness snapshots and broad regression failures, covered by
SHA256SUMS. Original full CSVs remain at their run paths with hashes. Previous
physical evidence is untouched. No physical trial, promotion, radio, PPU,
production BD, full receiver, main or remote write; stop for source/evidence
review before any new physical measurement.
