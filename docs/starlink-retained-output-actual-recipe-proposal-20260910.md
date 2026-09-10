# Retained output: proposed first actual-FFT gate

Proposal only. No vendor tool has been launched and no runtime, test-source,
clock, vector or acceptance limit has been changed. This document follows the
parent-reviewed 415-test prototype, not an inverse-sealed/P1/K/M/C1 union.

## Frozen source premises

- Tested FW `464e9bf34309501dd37089521288b81ccdbe5b4d`, HDL
  `2e8a7de221889084ea58cc6c44dd9a8407c56c9f`; portable evidence FW
  `2936070530809dfffaf9031a110ffb347dceae51`. The latter two source/evidence
  pins were subsequently pushed, by explicit authorization, to the existing
  high-rate60-paired DNM branches; no primary publication.
- The final 46-file source manifest SHA is
  `a4dfa8d603d1d7782b51106c6224a3dc6dfbc67d07e241abac8d7c390f83aeb8`.
  Preserve that entire closure byte-for-byte. New actual helpers/bench/runner
  form a separately reviewed additive closure; do not patch the offline files.
- Accepted original L1 source root:
  `/tmp/starlink-coarse-alternatives.Y3JzOI/bank-arithmetic/hdl/library/starlink_pss_acquisition/build/local-admission-actual-R1B1O1-L1-175-prepared-v4/frozen_sources`.
  Its actual bench SHA is
  `a347cd6ec4bb3e888f0ce171aedb7c4a85cebea4932bc880f348a75ada5ae238`.
- Reuse unchanged `create_shared_realtime_xfft_ip.tcl`, SHA
  `0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d`.
  Preserve its Vivado 2022.2/version/generic/entity checks, real-time 512-point
  18-bit BFP/convergent/natural-order core and actual reset/configuration ports.
  Its IP-generator target frequency remains 200; this is not the simulation
  clock. Do not retarget the factory to 175 or change its implementation recipe.
- Keep all 17 baseline source/vector pins in `retained_output_prototype.py`,
  including all eight `.mem` files. The 1,406 CI16 samples define three 512-word
  windows at stride 447. Metadata starts remain `1000 + fixture*447`.
  No C-model regeneration, fixture substitution or use of the unrelated 60 MS/s
  native cohort. This bank-island gate does not instantiate the score engine.

## First bounded actual scope recommended for preparation

Use one actual FFT instance, one retained-output DUT, the same three payload
banks and one fixed pair of clocks. Run seven sequential, explicit fresh-common-
epoch contexts, all at the accepted original 1.3 ns slow-clock phase:

| Context | Source | Reader / reset obligation |
|---|---|---|
| H0 | Three original windows | Continuously READY |
| H1 | Three original windows | READY on 13/17 slow edges |
| H2 | Three original windows | Retained-read park through the next F; original STALL2 condition |
| H4 | Three original windows | Real ACK during next-F raw output; original STALL4 condition |
| H5 | Three original windows | Hold actual final prefetch until F handoff; original STALL5 condition |
| R1 | Three original windows | Old I unread, next-F input prefix >=64; pause slow clock, raw slow reset, fresh purge and exact third-window replay |
| R2 | Three original windows | Same, but raw fast reset |

Use the literal conditions from the frozen composition bench
`465ce7c6547e0c3ca9bed11ca352998924e23aab4b7c7b826e66bddd31b22e0d`.
Do not tune a release time after observing vendor results. Scope derivation:
21 forward admissions, 19 inverse admissions, two deliberately aborted forward
input prefixes, 19 complete F/I pairs and 38 complete statuses. Every context
writes 1,536 bank input words: total 10,752. Exact complete F/product/private-I
inventories are 9,728 each; actual slow reads are 8,704, with 1,024 old unread
inverse words discarded only by the two explicit common resets. Every visible
aborted input prefix is checked separately; it is not omitted from the input
ledger. The public result guard does not publish a partial transform.

This initial proposal omits injected vendor faults, extra slow phases, long-
reader and stopped-reader actual cases. Their 415-test scripted/standalone
evidence remains separate. Actual raw-event cutover mutants and further phase
coverage need a subsequent frozen case recipe; no claim that seven contexts
replace the original L1 adversarial campaign or qualify all 415 tests with FFT.

## Minimal additive harness changes

1. New actual bench/adapter derives the entire checked composition source, not
   a manually copied numeric subset. Its strict inverse restores the original
   bench plus the exact two baseline-guard shadow blocks. Explicitly account
   for sequential context orchestration and actual-only receipts; no regex
   deletion of assertions or broad `expected_fault` numerical bypass.
2. Exclude `scripted_fft_ports.sv` from the compiled source list. Bind the
   unchanged generated module to the existing `shared_xfft` instance. The
   actual admission helper rejects the script module, duplicate module names,
   altered runtime sources, alternative factory or profile parameters.
3. The script currently contains the actual core-input numerical checker.
   Removing it therefore requires a new independent read-only input witness:
   latch phase/descriptor at real admission, count each actual valid/READY
   handshake, check all 48 packed bits (zero padding around each 18-bit payload),
   LAST, ordinal, complete-input count and source/product word. This check must
   run on every visible healthy or aborted prefix, not merely on the selected
   mailbox input. Independently require certification/physical handshake equality.
4. Replace the two references to script-only `input_count` with that independent
   accepted-input counter, and remove the unexecuted script fault-stimulus block
   only via exact whole-block identity/inverse. No actual `force`, no invented
   raw-valid signal or hidden vendor-state read is needed for these seven cases.
5. Keep both original result-guard shadow instances unconditionally comparing
   all original state and outputs, including invalid cycles. Reuse the accepted
   L1 input observer and full arithmetic shadow through strictly scoped binding
   adapters; the test references are never DUT feedback or added datapath.
   Preserve all product output/overflow/private arithmetic comparisons and the
   original documented join invalid-payload distinction, not a new waiver.
6. Bind independent current-core and retained-reader identities. A new F
   descriptor must never retag the old I read payload. Verify actual request,
   synchronized ACK, guard ACK, persistent transfer consumption and registered
   reusable admission separately; neither producer closure nor real ACK is
   synthesized by the bench. Healthy real-ACK controls remain known `000`.

The accepted arithmetic shadow is `c58e50c6...` (full SHA below), L1 input
observer `a8057de4...`, forward-retirement shadow `8ed19931...`. Their original
dependencies must be included and hash-pinned, with literal binding-only inverses.
No runtime file from a later arithmetic or sealed-bank candidate is imported.

## Clock, reset and service acceptance

Keep 1 fs precision, fast half 2,857,143 fs and slow half 5,000,000 fs, slow
origin 1.3 ns, asserted first edges and cadence. Paused slow clocks retain their
original edge grid. No MMCM, generated hardware clock, alternative clock rate,
constraint change or physical timing claim.

For every actual transform log absolute fast edge/time, actual admission,
configuration VALID/READY, reset assertion/deassertion, each physical input,
frame, status, raw output, private final, qualified publication, transfer and
real ACK. Sample events before NBA and verify settled state separately. Keep
actual slow final-read edges/timestamps; never mix them with fast-cycle deltas.

Preserve the old 1,500,000-fast whole-bench ceiling, 25,000-fast drain deadline
and exact 8,192 active-guard watchdog. Keep the frozen composition's 20-fast
healthy post-drain observation. The older actual fault task separately checks
quarantine after 24 fast clocks, then observes another 32 clocks; those bounds
must remain separate in any subsequent injected-fault case, not be replaced by
the healthy 20-clock interval. No limit is increased on a failure.

Per-transform comparison is event-indexed, not a global CSV shift. The original
L1 numerical service observations were admission→config 3, input span 513,
last input→first raw output 781, admission→raw last 1,809 and qualified final 1,810;
one status occurs with raw ordinal 2. Freeze those actual-core expectations before
launch, and preserve an unexpected result rather than fitting a new latency.
Each independent guard still joins its own complete input/frame/status/output.
The vendor's at-least-two-sampled-cycle reset flush premise is checked at every
cutover; the additional quiet released edge is not a substitute for that premise.
No direct raw diagnostics are masked during no-owner/reset/configuration periods.

For ready/13-of-17/STALL2 profiles retain the absolute 5,215-fast service bound.
Record source publication/full visibility, pending-source identity, core closure,
I publication, real ACK and actual next admission. Assert 8-clock next-F dispatch
only when the next source is already fully visible at the declared eligibility
boundary; 3,645 recurrence is likewise a conditional eligible-source hypothesis.
H4/H5 independently require their real ACK phase and complete read inventory.
If they produce an unexpected recurrence, retain it; do not hide it under a
nominal-only average. Parked-reader ranges are phase-sensitive measurements,
not a blanket+8 transformation of old timestamps.

The bank test offers already-formed overlapping windows at the slow bank port;
it does not simulate a continuously arriving native or canonical sample stream.
Actual stride 447 at 15 MS/s supplies each next window every 29.8 us, potentially
making the scheduler source-bound even if core capacity improves. A future
arrival-qualified test must charge the 512-word support endpoint and retained 65-
sample overlap without pretending that 512 fresh samples arrive every 29.8 us.
It must not infer source eligibility from scheduler state. Long parked-reader
cases remain protocol-only, and constant-cycle clock conversions are not actual
lower-clock replays. No lower-clock promotion follows from this proposal.

## Frozen bundle and one-shot owner to prepare, not launch

The preparer should materialize a new absent non-`/tmp` bundle with all 46 original
sources, all added checker dependencies, the exact eight vectors, recipe,
expanded bench, parser/tests, fixed factory and runner. Bind every source and
import to SHA/length and external manifest digest; check originals/copied files
before and after preparation and execution. Mutants must reject omitted input
checks/shadows, duplicate/missing epochs or words, wrong clock/phase/kernel/packing,
fake ACK, stale descriptor, missing reset/quiet/config handshake, changed budgets,
altered source/factory and wrong terminal context. Parser-only specimens must be
labeled as such; they cannot establish actual FFT success.

Proposed eventual owner follows the already reviewed one-shot pattern: exclusive
new recovery output, owner, temporary directory, external log and journal; all
absent before launch. Vivado 2022.2 with explicit SuSE library environment,
`general.maxThreads=2`, explicit repository Python with subprocess-only sanitized
PYTHONHOME/PYTHONPATH/LD_LIBRARY_PATH. Record original terminal/exit and preserve
failures. Always compare generated IP and source hashes after early failure too.
Retain bounded event/numerical ledgers, not a large waveform recording.

No executable actual bundle or command is supplied by this proposal. The next
request is approval to implement/offline-test that exact additive preparation,
followed by parent complete-source/bundle review before any vendor launch.

Full inspected checker pins:

```text
c58e50c6853cd0519f018b4c362e70aabcf6d157a414f6b6748b49496aec01ad  starlink_pss_bank_arithmetic_shadow.sv
a8057de409efcbf19680595c20ce5c2cc7ae7213ff459f7dd7ed162dc7b46551  starlink_pss_local_admission_actual_observer.sv
8ed19931be00db932b52d5bf57015168a185e31987db1af8924ba1c93774702b  starlink_pss_forward_retirement_shadow.sv
```
