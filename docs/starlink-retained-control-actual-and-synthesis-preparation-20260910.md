# Retained control candidate: actual result and synthesis preparation

The parent-owned vendor run **61512 passed**, terminal 0 after 57.314 s. This
qualifies the seven frozen functional contexts only. Physical timing, CDC,
continuous-rate capacity and deployment remain unqualified.

Actual source/preparation FW `77ffe5d82c2dc80a93cc6855da9c816aa56d5d53`, HDL
`3ecfd9f33a8b9cfe44dddc731c768325871f7936`; report-only FW `e021d1ec3` followed.
The runtime itself remains the four candidate files frozen at HDL `468cb764`.

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Actual owner directory: `retained-control-actual-parent.HbyLZ8I2`.
Original and copied 97-source bundle checks passed; the generated FFT wrapper
before/after SHA remains `a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.
The owner preserved the exact invocation, execution/exit, raw logs and result
receipts. No retries or gate changes were made.

## Functional evidence

All seven contexts, 40 causal frame records, 38 complete transforms, 19 complete
pairs and two aborted forward prefixes pass. All 77,953 actual CSV rows are
byte-identical to v5, SHA
`07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
The complete parsed original result also equals v5 after removing only the new
candidate result field. The parent independently verified both facts; the
collector repeated the frozen result verifier and original-result comparison.

The 44 new receipts report both options enabled; 40 exact accepted descriptors;
38 final-input edges; 49,419 pre-edge and 49,419 settled post-edge closed-predicate
checks; and 19,456 public-return uses. Forward owner: 21 admissions / 19 real ACK /
34,719 held checks. Inverse owner: 19 / 17 / 60,660. The two absent inverse ACKs
are the unchanged reset-discard cases, not fabricated transfers.

The original full predicate feeds all three old guard references. The full
136-bit forward shadow and both unconditional state shadows pass without masks.
Actual frame pulses occurred at admission+8 in these 40 jobs; this observation
does not replace the causal frame contract. Dispatch remains 8 clocks when the
next source is eligible; nominal service is 3,645 and the parked-reader case
4,912 at the existing ideal 175/100 clocks. This is not a lower-clock guarantee.

Owner preparation: 73 tests passed in 17.49 s. Independent parent repeat:
73 passed in 18.06 s at `retained-control-parent.vZVvViyX`. All 97 sources and
the 100 prepared file receipts stayed unchanged.

## Minimal synthesis preparation

Tested FW `e0f87f3239ba6bbd543421cff389d2887edf0f86`, HDL
`569e62f80f46a73f33e91c245395c4b811f329bf`.
Prepared directory: `retained-control-synthesis-prepared-v1`.
Its 110-file `SHA256SUMS` digest is
`3590d4db36dd313a1db55419f46f1897bf8b588756e8b406f55537b1d7c135ee`.

The copier and Tcl each have a strict whole-source inverse to the previous
retained synthesis preparation. Changes are limited to source-specific names,
the accepted candidate bundle/CLI, four candidate source replacements, and
`PRIVATE_DESCRIPTOR_OFFER=1 CLOSED_INPUT_CUTOVER=1` in the exact generic list
and readback. The 16 runtime files remain SystemVerilog in `sources_1`; there
are nine baseline and seven retained files, of which four use candidate copies.
No test/reference source is compiled into the synthesized top.

Factory, kernel, literal XDC, clock periods/groups, part, OOC/IP strategy,
directives, control-set threshold, thread hook and report/checkpoint ordering
are unchanged. There are no new timing exceptions. All four clock pairs retain
20 max and 20 min reports, plus constraints/clock interaction/exceptions/CDC/
unconstrained timing observations. The checkpoint is written and hashed before
reports; failures retain original status and source/IP/DCP post-checks.

Runner SHA: `767ecdfb05f7fc967855196f92a08d8f1fafc6225ea6ef871d12ac8b1e8ed8fc`.
Copier SHA: `81d418d1659a276a7a93609b44c611b669529f655d7e189b0c4856e742a28e4d`.
Test SHA: `4994cc995ce7d5205767bd1972f335c84e2de0f969509892510ab69bef2505c8`.
Clock SHA: `bac30eff84cc71d1f273104b716b388b55e51d33be10f9beaf1901232193ba3f`.
Thread-hook SHA: `aec974f2800f01285e888d1b188cd089534941922531914926a8e1b568d4c227`.

The one-file owner gate `tests/test_starlink_retained_control_synthesis.py`
passed 32 tests in 1.56 s, original 48004 terminal 0, retained under
`retained-control-synth-tests-v1.zt26L5ec`. The parent independently repeated
32 tests in 1.55 s and reported the 110 prepared files unchanged. Tests cover
exact source/parameter/clock selection, both new option readbacks, no-overwrite/
containment, absent/wrong actual evidence, and original-error/after-integrity
behavior through executed Tcl stubs. Stubs invoke no vendor tools.

The parent alone owns synthesis 56000. This report does not poll that handle or
claim a synthesis result. Route preparation/selection requires its terminal
checkpoint audit and separate authorization. No vendor invocation, radio/PPU
action, main merge or production gitlink change occurred in this lane.

## Portable proof

`artifacts/retained-control-actual-v1.tar.gz`, SHA
`8ab892b8612ea4b8673ebf991f090b3374a9ef003fd89193863163f8f04125e6`:
11,175,479 bytes, 915 safe regular members and 914 file hash/length receipts.
It includes the exact source bundle, actual numerical/log/owner evidence,
test receipts/stimuli and complete synthesis preparation. All 6,549 raw regular
files across the selected attempts are inventoried, including 246 actual-owner
files totaling 37,741,028 bytes. Large generated project/simulator payloads and
duplicate test source snapshots remain in place rather than being replicated;
omissions and symlink aliases are explicit. All before/after inventories match.
The collector is separate packaging tooling, not part of the older test claim.
