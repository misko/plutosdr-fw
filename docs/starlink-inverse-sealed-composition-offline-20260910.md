# Inverse-only sealed-bank composition: offline review cut

This is additive RTL and Icarus ownership evidence, not vendor FFT arithmetic,
service capacity, synthesis, routing, receiver or RF qualification. The frozen
fast-only prototype, original L1 top, arithmetic, result guard, source/product
mailboxes and original benches remain byte-unchanged. No default caller opts in.

New runtime files in `hdl/library/starlink_pss_acquisition/`:

- `starlink_pss_epoch_sealed_bank_cdc.v`: strict inverse to fast prototype
  d9c2382f; one512x36RAM, full75metadata, actual fast-write/slow-read clocks.
- `starlink_pss_inverse_sealed_issuer.v`: concrete producer/certificate/reader
  references, independent admission-time lease binding, actual consumption ACKs.
- `starlink_pss_fft_bank_owned_inverse_sealed_probe.v`: strict inverse to L1
  0cb54617; appended default-off `SEALED_INVERSE_OUTPUT=0`.

Four handshakes are deliberately different: nonfinal transport capacity, final
bank publication, synchronized final-read ACK, and tagged release/reusability.
The unchanged guard owns the held final and independent status. A certificate
is captured from `return_commit_valid`, never delayed `result_commit`. Loss of
that held certificate before publication vetoes immediately; its normal drop
after publication does not invalidate reader ownership. Metadata remains held
through ACK/release. Once-only private final consumption does not mistake
legacy held VALID for a new raw FFT output, which remains an orphan regardless
of bank READY.

Admission captures the lease before any return. Free admission capacity is not
the owned reservation retained during ARM_JOB and its next two receipt edges.
An arbitrary forged admission is diagnosed after one edge by `bad_admission_q`:
it is not claimed to veto an impossible same-edge publication. The actual guard
cannot admit while active/awaiting ACK. Registering only that diagnostic breaks
the structural job-ready/publication feedback; genuinely possible live vetoes
remain combinational. A separate graph regression is being prepared.

## Reset/CDC contract

Both local reset releases already include both raw resets, assert asynchronously
and release on their own clocks. Per-transform core reset never resets bank,
issuer or common-epoch reasons. A registered slow reader-idle receipt, produced
only on an actual slow edge, crosses two fast stages. Rearm requires core held
reset and actual local references/guard idle plus that receipt. It does not
require source VALID=0: a fresh full forward source before fast rejoin is legal.

Opt-in source-reader reset remains asserted until this remote purge receipt has
armed the inverse epoch. The source-fault synchronizer is held clear under the
same barrier, preventing a paused old sticky source fault from re-quarantining
the new epoch. The scheduler parks before VERIFY_LEASE, not inside its63-cycle
timeout. No raw fast publication or fault controls slow output VALID; the
existing two-stage slow sticky-fault visibility remains the boundary.

## Executed first review cut

The retained complete136-test run is
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/inverse-sealed-tests-v2.oAiFdODy`
(original98512, EXIT0,136PASS12.02s). After expanding Ruff-equivalent `re.M`
spelling, source-specific repeat original70165 is EXIT0,136PASS12.99s at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/inverse-sealed-tests-v3.VMsOb2jn`.
Ruff passes. Per-case sources/manifests and compile/simulation exit/log receipts
remain in each retained `cases/*/run`; no attempts are overwritten.

- All original16 smoke tests, including the unchanged11 fault/reset cases,
  strict three-file inverses and explicit default/enabled scheduling options.
- Nonzero512-word/all75metadata real-guard pair, two actual leases, status held
  300 clocks, real8191 watchdog on the new would-publish edge, current fault.
- Ten175/100MHz phase offsets, immediate/delayed status and two jobs. Publication
  is +2 fast clocks, actual ACK-to-release1, complete reusable observation is
  +4 to +6 fast clocks versus the concurrently driven original guard/mailbox.
  This is observed synthetic raw-result timing, not a guaranteed phase bound
  or actual FFT pair service measurement; the <=8 allocation remains planning.
- Paused slow clock after17/510 reads permits exact provisional prefixes19/512;
  after the first pre-edge fast-fault sample S1, S1/S2 may read, S3 cannot.
  ACK may arrive after512 provisional reads, but no release/reuse is allowed.
  Request not yet synchronized before pause yields zero outputs before fault.
- First/final slow stalls retain VALID and all output fields. Single metadata
  corruption at first/interior/final spans exponent, start, direction and all
  trailing25th-leaf bits72..74. Seven reset joins on both raw sides recover a
  fresh exact512-word block. Old raw stimulus remains untouched.
- Full derived top: eight naturally reachable paused-source cases, both raw
  sides, old healthy full request1/fault0 versus separate malformed empty
  request0/fault1, fresh fill after rejoin versus full512 fill while fast paused.
  All require80 fast clocks of closed preflight/core/reader before slow purge,
  then512 correctly indexed fresh source and512 output words. A subsequent NEW
  source fault must still cross and quarantine.
- Ten executed mutants reject missing certificate-loss veto, missing real ACK,
  repeated held-final offer, wrong second-job lease, lost owned reservation,
  stalled VALID withdrawal, and both source barrier mechanisms on both reset
  sides. The deadline mutant specifically fails with commit0/publication1 at
  age8191, not a conflated missing-stimulus assertion.

`tb_starlink_inverse_sealed_guard.sv` supplies independent nonzero raw results;
`tb_starlink_inverse_source_purge.sv` uses the frozen explicitly synthetic ZERO
FFT interface. Neither is an FFT golden. An independent event-receipt collector
and source-closure/mutation gates remain before final composition qualification.

## Logical state and remaining scope

Issuer declares9 control bits (including the registered invalid-admission cause),
below its24-bit planning target. CDC bank declares318 register bits:222 reused
payload-reader/metadata/cursor bits and96 control/check bits, plus one18432-bit
RAM. Combined327 versus223 elaborated old external-reset mailbox bits is +104
logical state bits. This is not mapped FF utilization. The original standalone
317-bit count included a local two-bit reset release removed in this variant;
three new remote-idle/CDC bits make the bank total318. No new payload RAM/DSP.

Before vendor evaluation: finish independent event/source/graph checks and
freeze exact runtime/test closure. Actual FFT numerical/current/late-fault
qualification, measured complete pair throughput and physical CDC/timing remain
separate approvals. Private pipelined cause timing is explicitly changed, not
cycle-identical legacy reason-counter ABI. Full original-source coarse/native
fine/pilot and source15/30/60 objectives remain unchanged.
