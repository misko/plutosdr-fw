# Staged inverse-output integration — experimental, DO NOT MERGE

This candidate integrates the staged descriptor controller with the real
generated FFT, kernel multiplication, source/product RAM and inverse-result
dual-clock RAM. It is a first replacement of inverse-output ownership, not a
replacement of all forward/cutover control and not a receiver release.

## Interface and ownership

`starlink_pss_staged_mailbox_control.v` serializes typed ALLOCATE, COMMIT and
RELEASE commands. Its separate allocation-return register can remain held while
an older payload commits/releases. A full table cannot put an impossible third
allocation ahead of the required release. The descriptor table still has two
entries; the output mailbox still has one physical payload bank.

The adapter's completion input requires an independently validated, fully
privately written block and its exact final word. In the FFT candidate it is
driven by the existing result guard's qualified commit, never raw FFT TLAST.
The adapter saves/replays that final word after the staged COMMIT response.
Only the actual bank request transition creates a publication receipt. The
reader must consume all 512 words and its ACK must synchronize back before the
adapter issues RELEASE. The inverse result guard sees READY low in between;
an idle bank's request/ACK equality cannot fake a reader acknowledgement.

Allocation is requested before inverse admission. During the command latency,
the scheduler retains its private reservation of the physically empty bank.
That pending reservation does not admit the FFT: admission separately requires
the successful allocation response. The output bank carries a 32-bit tag plus
the new five-bit exponent instead of 75 bits per beat. The immutable original
70-bit descriptor remains in the ledger, so the public 75-bit metadata format
and full timestamp are preserved through the actual final reader transfer.

The metadata lookup into the slow reader is a stable bundled crossing, not a
physically qualified CDC interface. Both reset domains and every tag holder
must be purged together; the inherited epoch barrier remains. Immediate current
faults still veto publication, while a private final-word rewrite can occur on
a fault edge. This deliberately avoids putting the same-edge framing comparator
back into the private write-valid path.

The source/product path, input validator, two result/status validators, kernel
join, multiplier arithmetic and core cutover are retained. Their timing paths
may still fail. Native 60 MS/s fine search and independent 2.5 MS/s IIO remain
release requirements; neither has been removed or newly qualified here.

## Tests and evidence

The focused logical suite passes 67 tests: 41 staged-ledger checks, 12 real-bank
testbench composition cases, and 14 synthesizable-adapter composition cases.
The latter exercises three jobs with two occupied descriptors, a held allocation
return, pending third allocation, output stalls, four cancellation boundaries,
reset recovery and four rejected unsafe RTL mutants. Logical dual-clock
simulation is not physical CDC qualification.

The actual-FFT harness uses the pinned original generated XFFT (not an FFT
stub). It checks exact original forward, product and inverse vectors; full
timestamps/exponents; input/raw/status/frame inventories; output backpressure;
forward processing while an older inverse result remains reader-owned; and
the existing 5215-cycle service limit for its qualifying contexts. An independent
Python audit compares every recorded numerical word with the prior actual
generated-FFT CSV. The new scheduler's control cycles need not equal the old
controller's cycles. This four-context harness is not the complete earlier
seven-context reset/fault campaign or sustained 60 MS/s qualification.

First attempts are preserved under the recovery root:

- `staged-output-actual-v1`: XSim internal exception in a testbench string task;
  rejected by the audit despite the enclosing Vivado command returning zero.
- `staged-output-actual-v2`: genuine integration failure at cycle 2753, inverse
  preflight destination reservation dropped during pending allocation. Fixed by
  retaining that private reservation, not by bypassing the check or early FFT
  admission.
- `staged-output-actual-v3/v4`: unknown admission caused by an implicit local
  readiness wire inside the generated result-guard scope. Explicit early
  declarations plus `default_nettype none` fix it. V4 retains the diagnostic
  edge trace. An added lint test rejects a deliberate readiness-signal typo.
- `staged-output-actual-v5`: PASS, 46.18 seconds, source-before/after equality.
  All 43,008 records match the corresponding prior actual-FFT numerical fields.
  Four contexts each contain 3072 real FFT inputs, 3072 raw outputs, six statuses,
  three publications/releases and 1536 final reads. Every context witnesses
  1024 forward inputs while an older inverse result remains retained. The first
  two also witness 1022 concurrent reader transfers.

V5 service intervals are 3655/3655/4927/11727 fast clocks. The first three pass
the unchanged 5215-cycle qualifying limit; the fourth intentionally stalls the
reader for 9000 clocks and is not a real-time capacity claim. The prior healthy
interval was 3645, so staged ownership costs ten clocks in this harness. The
new numerical CSV SHA256 is
`c35159d51b2ebdda97287ac9557a096da1931c0ced38911f8f142ec67d7a4f8b`.
Frozen input SHA256SUMS digest:
`ebbbf355df97b09b174bd2d96aa09693b52b84e1e320114aea0a1bcb007dfd11`.

The combined regression passes 259 tests in 38.36 seconds. A separate nine-test
audit suite checks the real recorded result and rejects a fatal log, missing
context, missed deadline, missing/duplicate numerical word, changed payload or
exponent, and an unknown context. These parser tests are not additional RF runs.

Frozen inputs, SHA256SUMS, exact command, process identity, stdout, simulation
logs and before/after source checks are retained. No radio, production HDL
gitlink, PPU or main branch is changed by these experiments.

## Physical result: timing FAIL, do not promote

Source-matched synthesis completed in 164.15 seconds: 2576 LUT, 5303 FF,
21 DSP and 15 RAMB18. The unchanged routing recipe then completed in 55.46
seconds. Independent audit joins source hashes, checkpoint, route status,
utilization, timing summary and every reported clock-pair worst path:

- Setup WNS **-2.726 ns**, TNS **-1156.969 ns**, 1110/12757 failing endpoints.
- Hold +0.061 ns and pulse +1.830 ns, zero failures.
- 7967 routable nets fully routed, zero routing errors.
- Routed resources: 2625 LUT / 5310 FF / 21 DSP / 15 RAMB18.
- Worst path: expected product metadata bit 8 → preflight/shared fault summary
  → completion acceptance → `cutover/reset_flushed_reg/D`. Ten logic levels,
  8.387 ns data delay (1.895 ns logic, 6.492 ns routing).

This removes the old retained-owner endpoint but does not close the subsystem.
It is better in worst slack than the last destination candidate (-3.106 ns),
but worse than the offered-summary reference (-2.504 ns), and has more failing
endpoints than either. There is no net resource saving yet: the forward and
cutover controls still retain their old wide metadata checks.

Synthesized DCP SHA256:
`3ad36c8e47b498e8ede39ccf2c4db7d0e9999a9bc221bd6eaf969d8bb148e769`.
Routed DCP SHA256:
`fed1e302410c65e7d00fff133499190ee3094190b4663b2584c9391dd23b7ba7`.
Evidence: `staged-output-synth-v5`, `staged-output-route-v5` under the recovery
root. All execution handles are terminal; original/copied sources are unchanged.

Five critical CDC findings and 114 input/124 output delay constraints remain
open. In particular, the new descriptor lookup ends at unqualified output ports
instead of the old slow-clock descriptor registers. Fewer reported metadata CDC
warnings are **not** proof those crossings disappeared or became safe. Restore
an explicit reader-clock descriptor capture/valid boundary and qualify it before
claiming full interface timing. Board clocks and clock-source placement remain
unqualified, and no timing exception was added.

## Next implementation gate

Stage the remaining FFT handover controls: wide completion/admission validation
must terminate at registered certificates before changing cutover ownership and
reset state. Preserve the current-fault publication fence and cancel queued
certificates on quarantine/reset. The existing scheduler already has admission
and completion receipts, but cutover still consumes the raw same-cycle accepts;
their relative reset/configuration timing must be proved when that changes.
Do not merely delay a shared fault bit or waive the same-domain failures.

Add the reader-clock descriptor boundary, then rerun actual FFT numerics and
restore the full reset/fault/paused-clock campaign before another source-matched
route. Remaining release gates are full native-60-MS/s receiver integration,
independent 2.5 MS/s IIO, board timing/CDC/reset, actual RX calibration, `.18`
canary and `.17` PPU Ethernet deployment with the 300-second blind comparison.
