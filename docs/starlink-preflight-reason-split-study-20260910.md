# Preflight reason-only split: tested, not physically measured

The default-off registered scheduling path passes actual-core numerical,
publication/reason equivalence and preflight boundary tests. No synthesis or
route was run for this change. The prior failed route and244/8 regression remain
unchanged at FW `9b3249798` / HDL `ba000e48` and in `registered-scheduling-v1/`.

Tested source: FW `8d0663780b4682b04e7f5dc7953b3e532eff46de`, HDL
`cee639e43db062b8618b8d66fb26c2078ed0d2b3`. Both actual runs froze and hashed
the source before compilation; the seven design RTL files byte-match that pin.
Their scope's git field records the pre-commit base, not a substitute for those
source hashes. Evidence is
`hdl/library/starlink_pss_acquisition/evidence/preflight-reason-split-v1/`.
Complete runs: `/tmp/starlink-completed-input.5EaJuD/preflight-{actual-v1,default-v1,regression-v2,reason-v1}`.

## Contract change, narrowly bounded

`USE_PREFLIGHT_REASON_ONLY=0` preserves the default result guard. The registered
wrapper opts in: raw preflight faults feed `any_fast_fault`, an epoch-owned
six-bit ledger and ONLY the guard's reason-register bit0 OR. They no longer feed
its combinational external/admission predicate. A strict source-delta test
removes exactly the new parameter, port, range check and reason-register OR,
then requires the entire guard to equal prior `ba000e48`. All active input,
result, mailbox and final publication veto logic is unchanged.

The ledger records owner, framing, lease, descriptor/header, destination and
timeout causes independently, accumulating combinations until the common epoch
reset. The existing three input reasons retain their separate epoch ledger.
Current preflight cause is captured on its original edge, so a following status
is classified as orphan; merely delaying the external cause would lose that
reason if the guard had privately admitted on the mismatch edge.

The private start-token register is distinct from emitted `input_job_start`.
Registered quarantine qualifies the emitted token. A latest ARM/receipt-consume
mismatch may still advance private state or release private core reset, but its
same-edge reason/epoch registers prevent an emitted start, configuration, input
read or publication. This is synchronous edge/post-settle evidence, not an
asynchronous glitch-free output claim.

Only unpublished private readiness/admission may differ from the prior raw
preflight-veto shadow. A prior descriptor certificate is still required, and
no source/product bank read occurs during VERIFY/ARM. Guard public outputs,
payloads when valid and full sticky reasons continue to match the shadow.
Mailbox ACK/reuse machinery is unchanged: no fault may consume or release the
still-owned source bank; forward/inverse completion retains its existing fully
validated ownership/actual terminal-read ACK contract.

## Executed receipts

Both default and registered actual175 runs pass the unchanged44-block/10-fault
suite,24,064forward/product words and22,658inverse words, including the original
130provisional prefix words. The11handoff faults and reset recovery pass too.
Registered mode also retains the prior8scheduling faults/4one-sided resets.

The new matrix passes84rows: six causes plus their simultaneous combination,
three VERIFY/admission-capture/receipt-consume boundaries, same-edge versus
next-edge matching status, and both forward/inverse phases. Exact same-edge
bit0/status reasons, next-edge orphan status, all six detailed reason bits,
no emitted start/read/configuration/publication, unchanged consume generations
and held bank ordinal0 are checked. Both one-sided fault-reset directions then
clear the epoch and recover with a healthy result.

Observed60private-ready differences,12invalid-preparation private admissions
(that counter excludes timeout-only admissions), and60samples with private
start asserted but emitted start masked. These are explicit private exceptions,
not broadened equivalence claims. Registered cadence is unchanged:4,548nominal
clocks and4,828maximum in the bounded reader-stall profile; default remains4,540.

An independent108-row reason-only guard matrix covers three phases and all
same/next-edge combinations of none/status/frame/output/input-beat/input-complete.
Omitting reason-only capture is rejected immediately with
`PREFLIGHT_REASON_MISMATCH ... reference=01 candidate=00`. Existing final-public
veto mutations remain rejected. Final regression: **247passed,8explicit older
physical-test skips,0failed**; Ruff and diff checks pass. No failed actual attempt
or RTL correction occurred in this step. Previous failures are not overwritten.

This source has no new resource or timing result. The previous−2.461ns route
belongs to different RTL and is not a measurement of this split. No timing
exception, clock relaxation, receiver build, deployment or radio evidence.
Stop here for root review before any further physical experiment.
