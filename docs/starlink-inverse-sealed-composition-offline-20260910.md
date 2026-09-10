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
  fresh exact512-word block. Metadata corruption is10 directed bits per token
  position, not75 separate individual-bit corruptions. Old raw stimulus remains
  untouched. Separate first/final-stall fixture reuse+3 is outside the
  immediate/delayed-status phase-sweep's4–6 range.
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
FFT interface. Neither is an FFT golden. Final qualification below adds
independent accepted-event/source/graph gates, without changing runtime RTL.

## Logical state and remaining scope

Issuer declares9 control bits (including the registered invalid-admission cause),
below its24-bit planning target. CDC bank declares318 register bits:222 reused
payload-reader/metadata/cursor bits and96 control/check bits, plus one18432-bit
RAM. Combined327 versus223 elaborated old external-reset mailbox bits is +104
logical state bits. This is not mapped FF utilization. The original standalone
317-bit count included a local two-bit reset release removed in this variant;
three new remote-idle/CDC bits make the bank total318. No new payload RAM/DSP.

Before vendor evaluation: source-specific actual preparation and reviewed
runtime/test closure are required. Actual FFT numerical/current/late-fault
qualification, measured complete pair throughput and physical CDC/timing remain
separate approvals. Private pipelined cause timing is explicitly changed, not
cycle-identical legacy reason-counter ABI. Full original-source coarse/native
fine/pilot and source15/30/60 objectives remain unchanged.

## Final bounded offline qualification

Original99908 EXIT0, **234PASS16.11s**, RuffPASS:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/inverse-sealed-final-v1.DFztazfI`.
Command is the same as above with both
`tests/starlink_oracle/test_inverse_sealed.py` and
`tests/starlink_oracle/test_inverse_sealed_receipts.py`.

The only HDL change after136 is additive CASE12 in the new nonzero bench:
after512 real slow reads and actual ACK, a current fault on the tagged-release
opportunity must inhibit release/reuse. Its missing-current-veto mutant fails
the explicit release-edge assertion. Runtime ea27c4e2/8ad9c2e7/2f988a16 remains
unchanged. Eight literal invalid/X/Z parameter tests exercise actual guards;
X/Z uses source literals, not unsupported Icarus command-line overrides.

`inverse_sealed_events.py` independently checks each accepted36-bit value,
all75 metadata bits, lease, epoch, ordinal, publication/ACK/release order,
S1/S3 fault timing and profile-specific stimulus/fault/reset inventories.
Terminal-only, truncated, missing cause/anchor, wrong identity/data, duplicate,
out-of-order and late-error receipts are rejected. This model does not copy
the RTL state machine or pretend slow provisional words can be revoked.
The new receipt fixture freezes the actual imported repository Python closure
before execution, including package/transitive imports, and checks exact names,
bytes and live source hashes afterward. Earlier17-file smoke snapshots did not
include that expanded Python package closure; their original inventories remain
unchanged and are not retrospectively relabeled.

The Icarus elaboration graph checker includes continuous `L` and intermediate
`LS` nodes plus net aliases; procedural state is a cut. The real-guard pair has
2690 continuous/net nodes, the complete synthetic top4412, both acyclic.
Restoring direct `bad_admission` feedback instead of its register produces a
detected actual graph cycle in both. This is not synthesis or physical timing;
whole-vector dependencies are conservative, and unresolved continuous nodes
are rejected. No combinational-loop waiver is used.

## Retained attempts

All paths are under the same recovery parent named above; no original is
overwritten. Per-case command/source manifests and logs are retained.

| Directory | Actual result / interpretation |
| --- | --- |
| `inverse-sealed-compile-v1.poLfTLr8` | Strict top inverse failed on extra final newline; subsequent shell reached missing-source compile. Not a compile pass. |
| `inverse-sealed-compile-v2.dn0CnCwi` | Standalone issuer compilation EXIT0 only; no simulation. |
| `inverse-sealed-tests-v1.OkYZuDcy` |16PASS4.97s, original49267. |
| `inverse-guard-tests-v1.usVmseQd` |7PASS0.51s, nonzero actual guards. |
| `inverse-guard-tests-v2.fp4ZxGdj` |50 phasePASS,8 compileFAIL: runner mistakenly treated kernel.mem as Verilog. |
| `inverse-purge-tests-v1.2dLEdiPC` |8 watchdogFAIL; new bench released initial raw resets before any clock edge. Corrected bench holds initial reset across5 slow edges, matching old fixture. No runtime edit. |
| `inverse-purge-tests-v2.L3YCM3uf` |8PASS1.33s, correct full-top reset stimulus. |
| `inverse-guard-tests-v3.9zbQSZkd` |52PASS2 test failures: missing-ACK mutant exposed a missing early-ACK assertion; held-final mutant was killed by watchdog rather than expected earlier assertion. Added exact ACK and healthy-held-final checks; runtime unchanged. |
| `inverse-sealed-tests-v2.oAiFdODy` |136PASS12.02s; Ruff identified two spelling-only aliases afterward. |
| `inverse-sealed-tests-v3.VMsOb2jn` |136PASS12.99s, RuffPASS. Parent independently136PASS11.96s at frozen fbfcd628/0e1f103c. |
| `inverse-receipts-tests-v1.mypGGP3C` |83PASS3 failures: model missed required S1 receipt, graph missed Icarus LS intermediate concat nodes. Both negative tests repaired the collector, not RTL. |
| `inverse-receipts-tests-v2.zvsCumww` |86PASS2.62s, complete graph/event mutations. |
| `inverse-receipts-tests-v3.MSPPC9Af` |93PASS4 failures: Icarus CLI X/Z defparam prints error but exits0 using the default. Test rejected the false premise; new runner rejects compile errors even at exit0 and guard tests use actual literal X/Z declarations. |
| `inverse-sealed-final-v1.DFztazfI` |234PASS16.11s, RuffPASS; all original and new checks together. |

The first compile failure's precheck/compile details include original tool output;
no absent raw stderr file is fabricated. Minor Ruff/apply-patch preparation
diagnostics remain tool-output observations, not invented archived logs.

Next authorized work is offline-only vendor-FFT preparation. The old L1v4
actual bench stays immutable. Its overloaded READY/bank hierarchy assertions
and inverse reservation injection require explicit strict-derived bindings to
transport/publication/ACK versus reusable/reserved signals. All old arithmetic,
sample identities, fault intents and absolute service budget must remain
independently checked; private latency changes are not whole-chain CSV identity.
