# Registered FFT handover and reader metadata — DO NOT MERGE

Baseline is the preceding staged-output candidate (FW `4fcc7b8d1`, HDL
`e55f6d543`), whose actual numerics passed but routed timing failed at -2.726 ns.
Its worst path crossed metadata validation/shared fault logic and raw completion
acceptance before reaching cutover/reset state. The previous frozen snapshots,
checkpoints and remote commits remain the reference; this work changes the
experimental candidate, not the production receiver HDL gitlink.

## Runtime changes

1. Cutover admission and producer-close inputs now consume the existing
   registered admission/completion receipts, not raw same-cycle accept signals.
   The scheduler applies the same receipt on that edge. The admitted phase is
   held explicitly; the core is still reset during admission and remains owned
   until the validated close. Common reset or registered quarantine fences the
   receipt inputs. Current faults still veto publication immediately; private
   state may advance on a new fault edge but cannot start a new public job after
   quarantine. No shared fault bit was simply delayed or disabled.
2. V4 validates the full descriptor in the writer domain at accepted completion,
   before staged COMMIT. It holds a 75-bit timestamp/phase/exponent tuple plus
   32-bit tag until the real bank is released. After observing publication, the
   reader captures these held registers, then checks the captured tag/exponent
   against the bank metadata on a separate reader edge. No read or public valid
   is allowed before this check. Failed writer or reader checks cause sticky
   quarantine. Reader faults have a dedicated two-register synchronizer; fault
   signals are combined only after synchronization.
3. The output bank's private payload mux follows registered publication ownership,
   not fault-gated replay-valid. Public authorization still observes the current
   fault fence. This prevents a fault signal from switching metadata and feeding
   back through the wide framing comparison into control.

The held descriptor remains a bundled multi-bit clock crossing that requires
physical qualification. Restoring reader-clock registers exposes real timing
endpoints; it is not a waiver, nor proof of physical CDC safety. Source/product
buffers, FFT arithmetic, full validators, output publication and actual reader
ACK ownership remain in place. Native 60 MS/s fine search and independent
2.5 MS/s IIO are unchanged release requirements, not newly qualified here.

## Actual generated-FFT tests

V1 and V2 actual runs pass without runtime correction between them. V2 adds stronger
full-width timestamp patterns and corresponding audit requirements; it does not
change V1 RTL. Their first metadata boundary used a live writer-domain lookup
feeding reader registers. V2 routing exposed this as a critical cross-domain path
and also exposed the fault-dependent payload mux loop. V3 corrected both in RTL
and passed preparation/lint only; it had no actual run. V4 retains V3 RTL and adds
a seventh actual fault test for writer-side descriptor validation. The V4 actual
run passes. Source snapshots and all execution logs are preserved.

Six healthy numerical/backpressure contexts use the real generated XFFT and
frozen forward/product/inverse reference vectors. Independent audit matches all
**64,512 numerical records** against the previous actual generated-FFT CSV.
Each context contains six transforms, 3072 physical inputs, 3072 raw outputs,
six statuses, three publications/releases and 1536 reader outputs. Every context
also observes 1024 forward inputs while an older inverse output remains retained.
The two added readiness patterns include delayed reader start and held final
read while subsequent forward processing proceeds.

V4 service intervals are 3655/3655/4927/11727/3655/3655 fast clocks. All contexts
except the deliberately 9000-clock-stalled reader pass the unchanged 5215-cycle
limit. The normal interval is unchanged from the preceding staged-output design.
Two contexts verify all output timestamp bits with bases
`a5a5a5a5a5a5a000` and `5a5a5a5a5a5a5000`; numerical payloads remain identical.

Two additional tests stop the reader clock with an unread 512-word result and
the next forward transform 65 inputs into its block, then assert either raw
reset independently. Neither can rearm while the reader clock is stopped.
After five reader-clock purge edges, stale source, output, descriptor and cached
metadata state are absent; a fresh block produces exactly 512 correct reads.

Seven V4 actual-RTL fault cases exercise:

- A raw output coincident with pending admission application.
- A duplicate status coincident with pending producer close.
- A vendor fault during staged inverse COMMIT validation.
- A vendor fault at the authorized final-word replay boundary.
- Corrupted held descriptor tag before reader capture/validation.
- A vendor fault before the final actual reader transfer/ACK returns.
- Corrupted writer-domain descriptor lookup at accepted inverse completion.

No case permits late publication or descriptor release after the fault anchor.
All except the final-ACK case have zero reader transfers; that case has exactly
512 real reads but no
post-fault descriptor release. Across healthy/reset/fault contexts, the bench
checks 58 registered admissions and 52 registered producer closes, with the
expected aborts accounting for the difference. These are bounded interface
faults, not an exhaustive formal proof or an RF/continuous-rate test.

## Evidence and regression

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Prepared folders: `staged-handover-prepared-v1` through `v4`; actual folders
exist for V1/V2/V4 only. Actual runs completed in 70.04/70.55/71.52 seconds.
V4 frozen inventory SHA256:
`e8a7f06591bf4ef518f3368b170123fefbf416dd2c498da505341bf0ba785eb8`.
V4 numerical CSV SHA256:
`d2db7ef34c61ed38685f6e30d03cc2296842260b4a828da313d2bca56d02a7ba`.
The V1/V2 CSV hash is `90f69b4268477277bfaf9e7394e36d5ac31603ccb1853d1922e9c49e1c64c63f`;
V4 changes transfer cycles, but every numerical data/exponent field still matches
the independently pinned prior actual reference.
Both before/after source checks pass; generated FFT wrapper identity is unchanged.

The V2 combined regression passes **278 tests in 38.77 seconds**. This includes the
prior component/runtime/policy tests, the previous nine numerical-audit controls,
and ten new handover-audit tests rejecting missing/short reset evidence, early
rearm, missing fault cases, post-fault release, missing final read, missing or
truncated timestamps and absent terminal handover proof. Parser tests are not
additional hardware executions.

The V4 combined regression passes **290 tests in 41.50 seconds**, including
both six- and seven-fault audit campaigns and rejection of mismatched campaign
counts. These parser controls complement, but do not replace, the seven actual
RTL fault executions above.
An additional **12 report-auditor tests pass in 0.05 seconds**: both routed
report sets are parsed, the V2 cross-domain global worst path is selected rather
than assuming a same-domain worst, and modified checkpoint, clock-pair slack,
route-error count, recipe and failed-execution receipts are rejected. These use
temporary report copies, not additional routing runs.

## Physical and deployment gate

V2 source-matched routing completed but **failed**: WNS -5.429 ns, TNS -2465.386 ns,
1673 failing setup endpoints. Worst was the live descriptor lookup feeding reader
metadata (-5.429 ns, 175→100 MHz); same-domain fast timing also failed at -4.026 ns
through the fault-dependent payload mux and framing comparison. Hold +0.058 ns
passed; 7972 nets fully routed; 2638 LUT / 5382 FF / 21 DSP / 15 RAMB18.
This failed attempt is retained and is not a deployment candidate.

V4 source-matched synthesis and routing complete in 105.62/66.17 seconds, but
timing still **fails**: WNS **-3.970 ns**, TNS **-2566.980 ns**, **2261 / 13432**
failing setup endpoints. Hold +0.065 ns and pulse +1.830 ns pass. All 8246 nets
are fully routed with zero routing errors. Routed resources are 2716 LUT,
5540 FF, 21 DSP and 15 RAMB18. This is not an accepted overall improvement:
although WNS improves from V2's -5.429 ns, total negative slack and endpoint
count worsen, and WNS remains worse than the staged-output -2.726 ns baseline.

The worst path is now same-domain `registered_scheduling.held_phase_reg` through
input identity/certified-input/cutover fault logic into `admission_receipt_reg`:
11 logic levels, 9.587 ns data delay, including 7.767 ns routing (81%). Other
top paths still terminate in writer descriptor validation and producer-transfer
receipt state. The live lookup crossing has been removed, but staging only the
consumer of a receipt does not pipeline the wide validation cone that creates it.

The next bounded design should capture bank-local admission/completion facts,
validate them in stages, and only then issue an ownership certificate. It must
hold or reserve each source bank during that check, prevent stale certificates
after reset/fault, and keep current-fault publication fences. This needs explicit
edge/fault tests before another actual-FFT and route run; simply delaying a
global fault flag, relaxing timing constraints, or removing more TX is not a fix.

V4 synthesis DCP SHA256:
`fc78905dde068b4ae4b4a82ed2daa3898416068dc6ef827844762c74b4f5b610`.
Routed DCP SHA256:
`818be35eaa91b228ac05d5c355d070efcfdd24ee65b23404be4a42b3f5e478db`.
The independent route audit checks checkpoints/source receipts, all four clock
pairs, report summary, utilization and complete routing. No exceptions were
added. V4 CDC still reports 5 critical, 208 warning and 4 informational findings;
114 input and 124 output ports lack board delays. A held bundled crossing still
requires real CDC/physical qualification even when the structural report improves.

The device, diagnostic 100/175 MHz clocks, FFT configuration and implementation
recipe are unchanged. Real clock-source placement, all new
reader-domain timing paths, CDC/reset and complete receiver integration remain
requirements. No radio or main branch is changed by this experiment.

Full deployment still requires sustained native 60 MS/s fine search together
with independent 2.5 MS/s IIO, actual RX calibration, `.18` reversible canary,
then `.17` PPU Ethernet deployment and the 300-second/120 ms valid-dwell blind
FPGA-versus-host GLRT comparison. Passing this subsystem is not that release.
