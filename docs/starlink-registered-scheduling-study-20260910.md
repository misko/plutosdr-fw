# Registered bank scheduling: numerical pass, 175MHz timing failure

The separately opt-in scheduling experiment passes the actual-core numerical,
fault and reset checks, but its single diagnostic route fails 175MHz setup by
2.461ns. It is unpromoted. No full receiver build, radio test or new constraint.

Tested pins: FW `a2208479497eab1669fc2ebab01cb8cf70906d81`, HDL
`5f2fa9e3c5ae4bf6920649f04e80ab9fc8c0912c`. Prior raw-readiness study remains
FW `82b2c7e9ff3ef516adfb53cd9f5a260b34556909`, HDL
`ff22dda924306ca0a72aaf4981815210ee1cbb97`. Frozen sources, original failures,
logs and reports are in
`hdl/library/starlink_pss_acquisition/evidence/registered-scheduling-v1/`.
Complete runs are `/tmp/starlink-completed-input.5EaJuD/registered-{actual-v3,default-v1,synth-v1,route-v1}`.

## Explicit boundary and ownership contract

`REGISTERED_SCHEDULING=0` retains the original controller body. Mode1 snapshots
the 70-bit descriptor, phase, input ownership lease and destination reservation
in WAIT_BANK; VERIFY_LEASE certifies the full descriptor/header/ordinal/TLAST,
ownership and reservation; ARM_JOB consumes a registered guard-admission receipt.
The selected phase remains held through the job. A 63-cycle preparation timeout
is a fault, not permission to proceed. Input read-ready remains closed during
preparation. Input retirement still requires the actual checked core handshake.

The one-bit consume generation is a LOCAL lease, not a globally unique ID:
there is one reader, no read during preparation, and it toggles only on the
actual terminal bank read. The certificate expires before active delivery;
another generation cannot be consumed and reused while it remains referenced.
Either one-sided reset purges the common epoch and the reference. Full metadata
is still compared; the token is not a hash or substitute for identity.

Completion captures a receipt only after full guard completion, validated
forward product-bank ownership (including identity/position/TLAST/current
external faults), or actual inverse slow terminal-read ACK. It additionally
rejects current input certificates, frame/status/output events and all full
wrapper faults. A registered receipt, not raw readiness, releases private phase
state on the next edge. Mailbox ownership/512th-read ACK machinery is unchanged.

Only PRIVATE scheduling decisions use registered quarantine. Full current fault
checks still drive public valid/commit vetoes and the original result reasons.
The input checker's exact three current reason bits additionally accumulate in
an epoch-owned ledger that survives private core reset. A fault on a receipt
consume edge can change private state, but cannot publish a result, acknowledge
an unvalidated bank or admit an inverse/new job before sticky quarantine.
Private-state cycle equivalence is deliberately not claimed.

## Executed tests and measured cadence

Mode0 actual175 passed unchanged. Mode1 actual-v3 passed the original 44 healthy
blocks/10 fault cases, 24,064 forward/product words and 22,658 inverse words
(including the original 130 provisional prefix words). It also passed the
11 handoff faults, 1,386 fault-vetoed raw/certified readiness differences,
four late-ACK boundaries and one handoff reset recovery, with 574,274 full
guard-shadow control/reason comparisons through that receipt.

Eight added faults cover snapshot metadata and lease corruption, certificate
admission reservation loss, admission-receipt metadata/status corruption,
completion capture vendor fault, and completion-consume orphan/duplicate start.
Four one-sided resets cover snapshot, certificate, admission receipt and
completion receipt, each followed by a successful healthy recovery. Assertions
check no preparation read, exact sticky input reasons, certified lease at every
admission and 106 validated completion-receipt consumptions.

Snapshot-to-guard-admission is two clocks. Three extra admission clocks plus one
completion clock per transform add eight clocks per forward/inverse pair:
nominal 4,540→4,548 (25.9886us at175MHz); bounded reader-stall maximum
4,820→4,828 (27.5886us). Against the 29.8us/5,215-clock budget these leave
667 and 387 clocks, respectively. These are executed slice profiles, not a proof
of sustained source conditioning, scanner capacity or whole-receiver timing.

Failed actual-v1/v2 are retained. The first test monitor incorrectly recaptured
the completion timestamp on the receipt-consume edge; only the monitor changed.
The second incorrectly expected a first matching status after guard admission
to fault; the original contract permits it. The stimulus was changed to invalid
reserved status bits `0x80`. No RTL change or numerical-gate relaxation followed
either failure. Thirteen focused tests passed/four old physical tests skipped.
An expanded run produced **239 passed, 8 skipped, 3 failed**: two old whole-source
adapters and one mutation anchor expected the pre-existing `!final_fault_now`
text rather than the completed-input `!final_public_fault` selection. The guard
and those test files were byte-unchanged from the prior packaged study. Original
test files and exact failure log are retained in `tests-before-adaptation/`.

## Single measured implementation

| Measurement | Synthesis | Route |
| --- | ---: | ---: |
| LUT / FF |1906 / 4461|1935 / 4540|
| Slices / unique control sets |not placed|1040 / 58|
| DSP48 / BRAM tiles |21 / 7.5|21 / 7.5|
|175MHz setup / hold,ns |not routed|−2.461 / +0.071|
|100MHz setup / hold,ns |not routed|+1.927 / +0.110|

Worst175 setup: `registered_scheduling.state_reg[2]/C` →
`result_guard/active_private_reg/D`,8.122ns (2.630logic/5.492route),14levels,
including6CARRY4. State-dependent input selection still feeds the wide
preparation identity comparison, preparation fault and full guard admission.
The next path ends at `registered_scheduling.admission_receipt_reg/D`,−2.439ns.
Registering the private scheduler alone did not remove the full admission cone.
This is better than prior raw readiness−3.144ns, but still fails; no second route.

Worst175 hold: FFT `input_muxes[2].write_data_re_mux/use_lut6_2.latency1.Q_reg[14]/C`
→ `memories[2]...SDP_RAMB18E1_36x512/DIADI[13]`,0.248ns
(0.141logic/0.107route). Full endpoints are preserved in `route/receipt.txt`.
Worst100 setup: `source_bank/metadata_in_hold_reg[5]/C` →
`source_bank/write_position_reg[0]/CE`,7.596ns (2.548logic/5.048route).
Worst100 hold: `fast_reset_slow_reg[0]/C` → `fast_reset_slow_reg[1]/D`,
0.206ns (0.141logic/0.065route).

All6,544 routable nets routed, zero routing errors. Inherited constraints differ
only in the generated output-path comment. The139CDC-15 warnings,114missing
input delays and124missing output delays remain explicitly unqualified.
Exact normalization/scoring, detector stages,2.5MS/s pilot export, whole-receiver
cost/timing and live results are omitted. No replacement eligibility is claimed.
