# Output metadata CDC contract — diagnostic, DO NOT MERGE

Branch: `codex/starlink-rx-only-do-not-merge-output-cdc-contract` (FW only).
Runtime parent FW `b1871495e36dfee3c45d2d2fa6a23a95b5a57179`, HDL
`7a2a271eaddcdaa95214b16fab0b89fbc414407a`. HDL remains unmodified at that pin.
This checkpoint adds tests, read-only routed inspections and a fail-closed
assessment. It does not change timing constraints, routing, firmware or radios.

## Why the reported path is not a one-edge transfer

The parent route reports -1.258 ns on output metadata crossing from the 175 MHz
writer to the 100 MHz reader, using a 0.002 ns edge relationship (39.998 ns to
40.000 ns). Its rounded 5.714 ns / 10 ns clocks also produce Vivado's warning
that no common period was found within 1000 cycles. The mailbox does not sample
this bus on an arbitrary adjacent edge: metadata is held from its first private
write, the complete block publishes an ownership toggle, and the reader waits
for the synchronized toggle before capturing the held metadata.

Source-derived digital bounds, assuming the two-stage control synchronizers
resolve without premature transitions and the clock/reset contract holds:

- Position advances at most once per writer clock. First metadata capture at
  position zero precedes earliest complete publication by at least 511 writer
  periods for this 512-word mailbox. Metadata cannot reload while the reader owns
  the bank, and private final rewrites do not change the first-word descriptor.
- A newly published request reaches the first destination stage, then the second;
  the sequential capture predicate sees the old second-stage value. Earliest
  metadata capture is at least two reader periods after publication.
- Only the real last read changes ACK. The writer sees ACK through two stages,
  and a new metadata write occurs on a subsequent writer edge: at least two
  writer periods after actual ACK.

These are protocol arguments and bounded digital tests, not a formal proof of
all traces, analog metastability/MTBF analysis or board-level signoff.

## Executed tests

**17 CDC contract tests pass in 1.48 s**. Twelve clock/phase runs use writer/
reader periods 5714/10000 ps, 5000/10000 ps and 10000/5714 ps with phases 0, 1,
1234 and 4999 ps. This includes the diagnostic output direction, a 200 MHz writer
variant, and reverse-rate stress; it does not constitute board clock integration.

Each run completes 13 full reader blocks and ten reset cases: both raw reset
inputs at an early private prefix, unpublished final, request pending with reader
clock stopped, reader ownership with writer clock stopped, and partial reading.
Every cancellation is followed by a fresh full block. Back-to-back generations,
reader stalls, queued/churning next input while unread, exact data/descriptor,
publication/capture timing, real final ACK and ACK-to-rewrite ordering are checked.
Total: **156 complete reader blocks and 120 reset cases**. The bench uses the
actual output mailbox, actual epoch barrier and source-matched outer reset
synchronizers, with other full-receiver idle inputs outside this isolated scope.

At 175-to-100 MHz, observed minimum publication-to-capture is **20.035 ns**;
the source-derived lower bound is 20 ns. Observed minimum ACK-to-rewrite is
17.420 ns, above its 11.428 ns bound. Held-final test delays make first-write
observations longer than the theoretical earliest publication; do not infer the
minimum theoretical bound from measured averages. Across all profiles the
asserted reader/writer-period bounds pass.

Four unsafe mutations fail on explicit invariants, not timeouts: shortened
request synchronization, early ACK, offered metadata overwriting the held bus,
and reader capture from the changing offered bus.

**12 assessment/evidence tests pass**, plus seven archive tests, in 0.08 s.
They reject missing/duplicate bus bits, wrong endpoints/clocks/delays, missing
second-stage connections, incomplete phase coverage, timing-bound violations,
skipped tests and failed vendor inspection. The first assessment counted pytest
convenience symlinks as duplicate runs; excluding symlink directories fixes that
inventory issue without changing simulation evidence.

## Routed evidence and a real qualification gate

The read-only inspection of pinned DCP
`ee65ba286ece8625b60af30490ee33960f28e3eb93be60ac78e759968d8afcb1`
finds all **37 same-bit Q-to-D paths**, with datapath delays **0.737–1.158 ns**.
Both request and ACK have two actual `ASYNC_REG` registers in the intended
destination domains. Capture-enable fan-in includes the second request stage,
reader state, ACK and coordinated reset release, not the first request stage.
The checkpoint and inspection sources are rehashed; no constraints are applied.

However, the CDC report still contains **four CDC-1 critical findings**, one for
each source/output mailbox request/ACK crossing, and **one CDC-10** on the
combinational slow-purge indication. A second routed inspection establishes that
all four first-stage request/ACK registers also feed both bits of the corresponding
epoch purge counter, in addition to the second synchronizer stage. Source RTL
explains why: reset-idle observations compare entire two-bit synchronizer vectors.

This is a structural qualification issue, not an observed data-corruption result.
The observations may be functionally contained within reset/purge phases, but
that is not sufficient reason to declare the crossing qualified or waive it.
The generated assessment explicitly sets `control_structure_qualified=false`,
`constraint_change_authorized=false` and `deployment_eligible=false` despite the
passing digital tests and short bus routes.

## Next implementation and eventual scoped constraints

1. Refactor reset-idle observations so first synchronizer stages feed only their
   second stages. Derive reset-applied/idle receipts locally from known reset
   activity and stable state, with sufficient purge clocks; do not merely delete
   the old checks or reduce required reset coverage. Preserve stopped-clock and
   both-raw-reset behavior, and verify full receiver startup/recovery invariants.
2. Register the monotonic slow-purge indication before crossing domains, then
   account explicitly for any added startup cycle. Re-run the actual FFT
   campaigns and routed CDC inspection; require the intended clean structures.
3. Only after that proof, derive a scoped output-bus datapath bound. **10 ns**
   (one 100 MHz destination period) is a conservative candidate relative to the
   two-period request-to-capture bound and long source hold, but is **not applied
   or approved here**. Check all 37 bits, control synchronization, reset hold,
   clock assumptions and exception precedence; avoid blanket clock groups or
   false paths. Source and auxiliary descriptor bundles require their own review.
4. Continue the independent same-domain output-validation timing work. This CDC
   audit does not fix the parent's -1.215 ns same-domain setup path or alter its
   -328.306 ns TNS / 692 failing endpoints.

AMD recommends path-specific `set_max_delay -datapath_only` where CDC latency
must be bounded, and warns that broader exceptions can override those bounds:
[UG949 individual CDC constraints](https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/Constraints-on-Individual-CDC-Paths),
[exception precedence](https://docs.amd.com/r/2024.2-English/ug949-vivado-design-methodology/Clock-Exceptions-Precedence-Over-set_max_delay).
The rule classifications are described in
[UG906 CDC rules](https://docs.amd.com/r/en-US/ug906-vivado-design-analysis/Understanding-the-Clock-Domain-Crossings-Report-Rules).
The actual evidence above comes from installed Vivado 2022.2, not a newer tool run.

## Preservation and deployment scope

RAM root: `/dev/shm/starlink-output-cdc.JIdEms`. Preserve both inspections, every
per-bit report, digital test sources/results and the assessment. The parent
archive is an explicit dependency, SHA256
`7b3909f3b4737d226741d9a5675eec6c6114ec81ec464d31c6dd91d993a8c6f4`.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO remain unchanged.
No radio, PPU/main or primary production HDL changes. Full receiver timing/CDC,
board clocks, actual native calibration and sustained Ethernet/IIO remain before
reversible `.18` canary and `.17` PPU Ethernet-only deployment with pinned rollback,
300-second scans, 120 ms valid dwells and blind host GLRT. The goal remains open.
