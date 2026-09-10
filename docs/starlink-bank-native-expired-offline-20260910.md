# Expired native command with independent coarse/pilot: offline gate

The additive`520-pss-expired` profile is implemented and offline-tested.
**No actual175/200 MHz simulation has run for this negative profile.** Its
expected result is one rejected native request, with coarse/map/pilot remaining
healthy—not a healthy native visit. This stage did not change product RTL,
source arithmetic, numerical vectors, passing healthy benches/helpers,
physical constraints, runtime profiles or public AXI implementation.

## Source and scope

Independent worktree:
`/tmp/starlink-coarse-alternatives.Y3JzOI/bank-native-paired`.
Starting pins: FW`45079550e8d5107ecf2876dddf623cb2f7663c64`,
HDL`5ad9ba4a2ae7f196cbd44066eec725090cd76cea`.
New test-only HDL commit:`3debb55e0f3f125640cb9e8a4e23e4d9d2c09a1b`.

New files are the expired-event Python oracle/policy tests, a separate Tcl
runner/adaptation/verifier, and a separate SV checks include. The existing
healthy native runner, helper, checks and all original447/520/520-PSS arithmetic
oracles remain byte-unchanged. The separate runner fail-closed adapts the
healthy composition, replacing only its native checks/verifier. It retains
the complete legacy coarse/pilot numerical, source-continuity, stop,
healthy-snapshot, late-invalid-map-release and FFT-quiescence gates. It never
edits the original bench or a generated passing-run snapshot.

The same approved24-file true-PSS cohort is required, with receipt SHA256
`aa4330480879e5f44abdfeb34b5ddeca098f1b22352715743f0db32e6672de81`.
All4096 shared source words,66 native coefficients, kernel, three-block C-model
vectors,1341 offline scores,447x2 map expectations and512 pilot words/2048 bytes
are unchanged. Preflight recomputes the entire original approved cohort before
accepting the new event contract. No RTL output or synthetic counter value is
used to fabricate an expected result packet.

## Exact late branch and ownership contract

Public request`15005202` uses center/timestamp`FIRST+520`, unchanged
coefficient generation`15000002` and timestamp=index. Its fields are staged
over public AXI afterFIRST+16. The **single submit write** is delayed until
aroundFIRST+620; the actual public wrapper write must occur within620..624.
The sample-domain command FIFO handshake, not the host's intended timing,
must occur within620..640 on an enabled consecutive valid sample.

`starlink_pss_candidate_scheduler.v` computes
`lead = unsigned64(command_start_index - (accepted_index + 1))` and tests
`lead[63] || lead < MINIMUM_LEAD_SAMPLES`. Here start isFIRST+488, already
in the past: the lead sign bit must actually be1. The first command must have
`last_admitted_valid=0`, duplicate0 and overlap0. This establishes the exact
ABI rejection branch because scheduler priority is duplicate, overlap, then
late. On that handshake, this RTL branch increments rejected and late only;
it does not admit, activate capture, complete or abort a window.

The new sample-domain monitor observes the actual handshake and then checks
the same edge's NBA result after1 ps. It requires rejected=late=1 and every
admission, completion, duplicate, overlap, abort, source-gap, index, timestamp,
capture publication/discard/overrun/protocol counter to remain0. Capture
valid/start/done/abort and pending/active ownership must never assert. Separate
100 MHz monitors require exactly one public submit, wrapper handshake and FIFO
accepted pulse, with matching request/center/timestamp. Engine/reducer/result
counters, correlator busy, result_available and IRQ must remain0 throughout.
There is no broad expected-fault mask and no injected result or hierarchy write.

This guards specifically against a false success where the command was never
submitted, was dropped or rejected for another reason, was admitted then
aborted, repeated later, or silently produced a packet.

## Public empty-result proof

Two fresh public atomic telemetry snapshots are required: generation1 after
rejection and generation2 after the healthy coarse boundary stop. Each checks
31 exact public registers,62 ordered register reads total. The independent
event oracle freezes their address/value pairs; only rejected0x8c and late0x90
are1 among the scheduler/engine/reducer/result counter registers. All other
work/fault counters remain0. Active coefficient generation/energy are also
rechecked, and public result status0x5c must equal`0x1a000000` (26-word packet
geometry, bank0, available0). Status0x14 bits7:6 and IRQ must remain0. No result
release is issued; no unavailable packet word is read.

That last distinction follows actual RTL: the result-store RAM read enable
and returned word-valid are gated by result_available. An unavailable0x54
read therefore has no **qualified tracker response**; common`up_axi` can
eventually return its timeout fallback`0xdeaddead`. It is not a defined zero
packet and is not necessarily an indefinitely hanging external AXI read.
The new test avoids both0x54 and0x58 rather than treating timeout data as proof
of empty storage.

## Required concurrent coarse/pilot observations

The bounded event window opens at the submit attempt and closes four100 MHz
cycles after the observed sample-domain rejection. It must include positive
actual`fft_clk` RUN_JOB/core-active/nonfault cycles and positive100 MHz pilot-DDC
accepted canonical input while coarse processing and pilot are enabled. The
first actual fast-clock edge after the sample handshake must itself observe
RUN_JOB. The postprocessor rejects zero or unbounded-window witnesses. These
are future required observations, not extrapolated measurements or proof of
all stages computing simultaneously.

Coarse must still accept exactly894 scores, expose447 exact public map words,
and stop with its existing ownership/coordinate contract. Pilot must deliver
the unchanged2048 exact bytes and continue beyond coarse stop. Native must be
empty at that same stop and through a second public snapshot while pilot is
still active. The original later invalid map-release check still deliberately
marks joint health failed after the healthy coarse/pilot drain; it does not
turn the rejected native request into a healthy whole visit.

## Frozen expected events and tests

Live event contract:
`hdl/library/starlink_pss_acquisition/build/bank-native-expired-contract-v1`.

| Artifact | SHA256 |
| --- | --- |
| `native_expired_contract.json` | `680cdbdd674809de536a3323f99d74aa803174af650447cd816bd4ec7b6dfef7` |
| `native_expired_registers.mem` | `e17ab5ada48e7fd3f40381a9ed53804a81b791a9044f87c85f2fa3ad4966dee1` |
| New event oracle | `42d2dcb491a2da1a00347aa0b0f23f0dbec7edbbe156b52b5e183e56596c9cd3` |
| New runner | `fd349ce3d32c8d9a2a45e86ce96e7b41fb9fcfa6cf0fad4a2cd867294e009947` |
| New adaptation/verifier | `bf2164ddf9c135be04c51349db58fa6cf18c0422c660de48943b9dceb18bd394` |
| New SV checks | `d602487da7963dfd3d460e8d3d25175877d2dab73a5d24dd372a491415f9933f` |

The runtime import closure is13 distinct project Python files: the previously
qualified12 plus the new event oracle. Package initializers and transitive
imports are included. The real Tcl admission test freezes115 files before
a stubbed`create_project` fence, including all24 cohort files, both event
contract files, runtime dependencies and new/old relevant policy/helper source.
Its complete source-name/hash inventory matches after offline checks.

Executed final policy command:

```text
python -m pytest -q tests/test_starlink_bank_native_expired.py \
  tests/test_starlink_bank_native_true_pss.py \
  tests/test_starlink_bank_native_paired.py \
  tests/test_starlink_paired_realtime_psma_stop_policy.py \
  --junitxml=reports/experiments/20260910-bank-native-expired-offline-policy.xml
```

Result:288 PASS in11.67s, including44 new expired-profile tests; Ruff PASS.
The new tests verify exact register ABI/late-branch priority, whole-cohort and
counter/packing mutations, no overwrite, both intended clocks' pre-project
admission, caller-relative paths, complete13-module freeze, structural anchor
fail-closed behavior, and exact negative terminal/ordered register receipts.
They reject healthy packet receipts, missing/duplicate passes, wrong counters,
request/clock/lead/handshake bounds, duplicate-predicate rejection, zero
concurrency and late FAIL/FAULT/Fatal/ERROR including false fault exemptions.

A separate Icarus syntax/elaboration-only check passed using the bank1/MAP447
selection and native body defaults520/1. **`-i` deliberately ignores the
missing generated FFT; no clocks were run, and this is not vendor-core or
behavioral qualification.** Two preceding command diagnostics are retained:
the first omitted bank1 and could not bind its hierarchy; the second attempted
Icarus-unsupported overrides of parameters declared in an ANSI module's body.
The final command uses the already-correct body defaults. No source edit or
acceptance relaxation occurred between these syntax attempts. All three
syntax JSON receipts are archived; the earlier failures are not relabelledPASS.

Archive:`reports/experiments/20260910-bank-native-expired-offline-frozen.tgz`,
SHA256`f294f69ec3584f741aff8ba5f5b60d7990457e408e6affef56f29474bbe216f5`.
It contains124 safe unique members,122 regular files:115 frozen inputs, scope,
the two original event-contract files, policy XML and three syntax receipts.
All122 archive files were hash-checked; the complete audit is
`reports/experiments/20260910-bank-native-expired-offline-audit.json`.
No actual175/200 run is present or claimed.

## Separate next epochs, not implemented

After review, the current negative profile can receive one actual175 and one
actual200 run against these frozen inputs. A source-gap case should be a new
additive epoch/profile with a real missing source-valid edge while native owns
its520 capture, exact accepted-prefix accounting, and joint failed/partial
coarse/pilot evidence. It must not reuse this profile's healthy894/447/2048
terminal or hide native-gap counters. A subsequent reset/recovery epoch must
show fresh indexed results, not just disappearance of old work.

An FFT-only-reset/vendor-event case should likewise be a separate additive
epoch while native capture is active, retaining the certified FFT fault fence
and showing independent native/pilot outcomes without labelling the whole
visit healthy. Neither new case may gain a blanket expected-fault exemption.
Their exact counter and output-prefix contracts require separate RTL review;
they are not authorized implementations in this stage.

The broad objective still requires causal coarse-to-native command delivery,
original15/30/60 native-rate samples and conditioned kernels/public high-rate
interfaces, independent2.5 MS/s pilot IIO, full receiver timing/CDC/IO evidence,
RF accuracy,`.18` before`.17`, eight targets/120 ms dwells/300s. No radios, PPU,
physical work, primary edits, pushes or runtime promotion occurred here.
