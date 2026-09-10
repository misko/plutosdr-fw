# Bank-owned coarse engine: integration and deployment gates

This is the next experimental implementation, not a change to the target.
Preserve canonical15MS/s coarse PSS, source15/30/60 native fine PSS, independent
2.5MS/s CI16 IIO evidence, .18 qualification before Ethernet/PPU .17, and the
eight-target120ms-valid-visit/300s scanner. No main-branch firmware merge,
detector removal, timing waiver or replacement of fine evidence is authorized.

## 1. Integrate the local transform engine without changing score arithmetic

Checkpoint: the additive complete scorer passes the six 64-block/numeric
alternative runs and two independent primary-branch 175 MHz reruns. The frozen
alternative175 burst/stall4,096-block soak now passes:1,830,912 ordered scores,
2,097,152 words per transform stage,FIFO358/512,energy lookup age847/2048 and
no input stalls. Root independently reconstructed its full source/log/ordered
inventory receipt. Primary has a separate default-off idle-mailbox guard
extension, so this is not an exact primary-source4096 replay; it also does not
qualify the later control-path variants. The physical gates remain open. No receiver profile
selects this module yet.

The default-off phase-map selector now passes reduced 447-bin/three-frame
actual-core bank175/bank200 replay and existing shared200 regression, including
partial-tile vendor-fault abort and exact map reads. See
`experiments/20260910-bank-phase-map-replay.md`. Reduced 447-by-2 bank boundary
stop also passes at 175/200 MHz, including exact AXI map reads, actual later FFT
work in flight, source-tail shutdown and two negative stop cases; see
`experiments/20260910-bank-boundary-stop-replay.md`. Eight additional reduced-map
lifecycle cases now pass, including publication-boundary fault visibility,
retained completed evidence and independent FFT reset; see
`../docs/starlink-bank-map-lifecycle-20260910.md`. Paired digital-shell/canonical
PSS plus independent pilot replay also passes at bank175/bank200/shared200 for
447x2 and 343x2 maps; see `experiments/20260910-bank-paired-pilot-replay.md`.
These do not establish production map capacity, arbitrary reset/CDC races,
DMA/IIO receipt or concurrent native-fine support; qualify these before exposing
the selector through AXI/receiver packaging.

Root also refreshed the separate native tracker baseline: all15/30/60 public
AXI geometry cases and210 recorded15-rate windows pass on primary. See
`experiments/20260910-native-tracker-primary-baseline.md`. This is not a combined
bank/coarse/native/pilot test or a measured60MS/s timing/throughput claim.

Production-map prelaunch is frozen at FW `e2f3a582` / HDL `22aa00d4` on the
separate `-production-map` branch. Two343x2 maps match exactly:1,821 visible
scores,1,819 admitted and two checked excluded tails across those maps and a
fresh447-score partial abort. Root independently regenerated all14 oracle files,
passed151 policy tests and verified336 artifact receipts. The single full
20,000x64 actual-core simulation passed on reviewed source signature
`b10e4f2384084f7caff844d7508fff0a538e09caf8f3713d6fddcb7f2f39b75a`.
It checked1,280,000 admitted scores, all20,000 map words and a fresh447-score
classified partial abort. Original88186 exited0 at05:12:16UTC, with no restart.
Root independently verified all103 artifact hashes, archive integrity and strict
terminal replay;151 policy tests passed again. Additive harness/oracle/evidence
are now on primary FW205b7eb0b/HDLc8ad25a7, with352 combined policy tests passing
and no runtime RTL changes. Independent primary actual-core smoke also passes
two reduced maps and a fresh447 partial abort; all61 frozen inputs byte-match
the full-run freeze. See `experiments/20260910-bank-production-map-primary-review.md`
and `../docs/starlink-bank-production-map-full-20260910.md`.
This does not qualify a second full production map after recovery. The periodic
synthetic source tests arithmetic/geometry, not RF
acquisition or live120ms/750Hz performance. Native map fault is a separate output
from detector health; the failed partial terminal must remain explicit.

Keep the existing overlap scheduler,2048-entry energy cache, inverse output
register,447-candidate extraction,512-entry result FIFO and normalization.
Replace only the forward/inverse dispatch and intervening cross-domain copies
with the tested source/product/output bank engine in an explicit experiment.
Existing receiver profile selection and default implementation remain unchanged.

The source scheduler is clocked at100MHz and accepts canonical15MS/s samples
without upstream backpressure. The bank engine may backpressure scheduler block
reads, not the ADC. After block N's input is consumed, its source bank may capture
N+1 while N computes; no N+1 word may enter N's completed transform input epoch.
Output metadata carries the original block coordinate and both BFP exponents.
Service latency is not added to any sample timestamp.

Acceptance evidence:

- Actual generated-core1341-score replay matches unchanged forward, product,
  inverse and normalized-score fixtures, including positions and exponents.
  Forward/product observations must run on the fast clock, not accidentally
  sample fast handshakes from the100MHz bench monitor.
- Continuous canonical source:64 blocks, then4096 blocks, at200 and175MHz
  actual simulated service clocks. Nominal and declared burst/stall profiles
  must reconcile all447 scores/block in order, no source loss, scheduler expiry,
  energy miss or unbounded queue growth. Count/order tests do not establish
  numerical equality on their own.
- Source gap, index discontinuity, enable/flush, either clock-domain reset,
  output pressure and injected engine faults suppress invalid publication,
  quarantine retained work and recover only through the declared lifecycle.
  No silent weakening of old diagnostic semantics: if leaf fault categories
  aggregate into the shared-engine fault, document and test that convention.
- Provisional output before a late fault remains marked by failed terminal
  health; a valid prefix must not imply a complete healthy block/capture.

## 2. Measure the complete coarse composition

Checkpoint: passing alternative-source OOC synthesis has 3,868 LUTs, 6,499 FFs,
27 DSPs, 14 BRAM tiles and no black boxes. Complete source-specific evidence is
in `starlink-bank-owned-iq-to-score-resources-20260910.json`. This does not close
physical timing, external I/O or CDC gates.

Use frozen passing inputs and the unchanged generated FFT arithmetic. Measure
the complete scheduler, three banks, FFT/product, energy and score engine.
Include memories, control sets, clock/reset resources and queue high-water marks.
Do not sum overlapping hierarchy rows or subtract an isolated synthesis result
from a routed receiver and call the difference measured savings.

An isolated175MHz route of the existing bank-only synthesis checkpoint is a
diagnostic for internal paths. Its114 input and124 output external-delay gaps,
CDC and absent full receiver mean it cannot qualify a deployment clock. Keep
its constraints unchanged and report same-domain setup/hold separately from
cross-clock and external-interface findings. A source identity or clock mismatch
must stop the probe; preserve failed attempts rather than overwrite evidence.

## 3. Full receiver implementation, then hardware

Only a numerically correct, capacity-qualified complete composition is eligible
for a new full receiver experiment. Retain native fine, pilot decimation/DMA,
maps, IIO and their real clocks. If selecting a different transform clock, make
the clock-generation/profile choice explicit; do not alter the60MS/s ADC rate
or loosen its physical interface constraints to fit the detector.

The current FFT clock also supplies AD9361's200MHz delay reference. A175MHz
experiment needs a separate source, not a changed FCLK1. An actual candidate
MMCM configuration has been generated and simulated with the actual idle bank;
see `experiments/20260910-bank-island-clock-generation.md` and
`experiments/20260910-bank-clock-epoch.md`. Active complete-coarse traffic now
also passes five exact replays and four reset cases, independently repeated on
primary: 7,853 accepted scores and all accepted transform words checked, including
failed prefixes. See `experiments/20260910-bank-clock-traffic-primary-replay.md`.
The testbench's LOCKED/reset wiring is not yet a receiver connection. Input-clock
loss, arbitrary reset phases, physical recovery/removal and receiver integration
remain open; these finite functional tests do not close those gates.

The read-only complete-coarse checkpoint inventory now identifies all208
surviving held-metadata destinations, six ownership chains, two fault chains
and three RAMB18 payload banks; see `experiments/20260910-bank-cdc-inventory.md`.
The product bank is same-clock, not a CDC exception target. The inherited139
metadata CDC warnings and103/101 OOC input/output delay gaps remain open.
This audit did not apply or waive constraints.

The preceding isolated registered/held-preflight physical trial remains failing at
175MHz setup-1.614ns,hold+0.071ns,501 same-clock failing endpoints. This follows
the prior-1.596ns result; fewer LUTs did not improve worst timing. Current faults
feeding private product work and kernel metadata comparisons now dominate.
The next reviewed experiment is narrower than changing private retirement:
default-off bubble updates for only joiner I/Q and the four multiplier payload
registers, plus two exact balanced64-bit kernel identity comparisons. All
logical accepts, valid/metadata/overflow behavior, current/sticky faults, final
commit and bank ownership stay unchanged. The completed-input-fence worktree
has completed this opt-in experiment at FW `c62118a9` / HDL `97adf891`.
Both actual-core modes pass with byte-identical prior control traces; root
independently passed19 tests and verified416 artifact hashes. Its one unchanged
100/175 synthesis/diagnostic route completed:175 setup-1.559ns,hold+0.071ns,
TNS-518.092ns/553 failing endpoints.100 setup+1.851ns,hold+0.100ns.
All6668nets route, but the timing gate still fails. The worst path now runs
through output-bank current framing checks into forward kernel state enables.
The reviewed next step is an additive default-off forward-retirement output:
an inverse-only current framing fault is excluded only from the forward-only
expression, while sticky faults, original public return/commit/state and every
global same-edge reason remain literal. Prove exact forward retirement against
the frozen old guard under actual mailbox wiring, including raw corrupt tuples,
all other current faults, transitions, final/status edges and broken-contract
mutants. That implementation passed both original actual-core runs with identical
prior control CSVs; root reviewed all521 frozen artifact hashes and independently
passed49 focused tests with four existing physical skips. The corrected broad
sweep is769PASS/10 existing skips/7 known uninitialized-Linux source failures;
those seven separately pass on primary's initialized pinned Linux tree.
Its single approved unchanged100/175 physical trial is now terminal:175 setup
-1.907ns,hold+0.071ns,TNS-663.483ns/664 endpoints;100 setup+2.400ns.
The targeted output-bank current-framing/held-metadata fan-in is absent from
all64 kernel expected-next enables in both checkpoints. Nevertheless the new
worst path is held phase through input guard/current-fault aggregation into
fast_fault, and the next is kernel BRAM output directly into multiplier BREG0.
Kernel CE also remains failing through other fault/control dependencies.
No timing exception, runtime promotion or retry is authorized. Review a genuine
local-fault/quarantined-publication and multiplier-input pipeline before another
implementation trial. See
`experiments/20260910-payload-bubbles-parent-review.md` for scope and the separate
missing-Linux-source regression evidence.

An independent `-bank-native-paired` FW/HDL worktree is implementing the first
additive15MHz concurrent test, starting FW `9c6bee20c` / HDL `9759cf12`.
One true15MHz original CI16/index/timestamp source feeds native tracking and
the actual bank coarse/pilot shell; a100MHz sample clock with15/100 strobes is
not legal for the native scheduler's continuous-valid capture contract. Use
public native AXI, injection disabled, DSP reduction, independently calculated
26-word packets and positive observed compute/capture overlap. The static
smoke anchor is not causal acquisition. Existing runtime and old benches stay
unchanged;175/200 simulations follow new frozen expectations and policy tests.
The first175 actual run reaches exact native packet/coarse/map/pilot data but
fails the required positive capture/FFT overlap gate. Anchor447 appears too
early relative to real outer-bank fill. Preserve this failure and the strict
gate; diagnostic timestamps and a separately reviewed later supported capture
window must demonstrate concurrency, not merely correct sequential results.
The diagnosed gap is3.046826us between capture end and first actual FFT input.
An explicit520 later-window profile now passes at175/200:319/366 fast-clock
capture-overlap cycles,842compute/coarse/pilot observations, exact26-word
native packet read twice across stop,894scores/447map words/2048pilot bytes.
Its independently calculated winner-17 has normalized score about0.098; this
is concurrent arithmetic/ownership evidence, not the injected PSS start447 or
timing lock. True-PSS concurrent capture and causal acquisition remain gates.
These additive tests/helpers/evidence are now integrated on primary at
FW `aea211988` / HDL `8e2d11a8`, without changing runtime RTL. Independent
primary175replay also passes and freezes all ten project-local Python runtime
modules before simulation;201policy tests pass. See
`experiments/20260910-bank-native-paired-primary-replay.md` for exact source/
provenance distinctions. A new true-PSS520fixture now has independently
regenerated nonperiodic FFT/map/native/pilot goldens. Root read its complete
oracle/tests/runner delta, repeated244 tests, regenerated the complete cohort,
and verified all24 cohort files plus12 runtime dependencies in the archive.
The frozen source is FWc42ebde9/HDL5ad9ba4a on the separate native branch,
fixtureSHA aa4330480879e5f44abdfeb34b5ddeca098f1b22352715743f0db32e6672de81.
Both authorized actual175/200 runs pass (original53217/88546), including exact
zero-lag native packets, coarse/pilot bytes and positive concurrency. Parent
verified all108 frozen files/run,52 packet reads/run,512 ordered pilot words/run
and238 archive members/hashes. Additive tests/oracle/evidence are integrated at
FW72fa003a3/HDLb49553c1;415 combined primary tests pass. See
`experiments/20260910-true-pss-and-forward-retirement-parent-review.md`.
Next is an additive late-command negative test; implementation/offline tests
only are authorized before another reviewed actual run. This synthetic static
anchor does not establish causal acquisition, RF accuracy or high-rate support.

The30/60 extension cannot merely change a test parameter: current realtime and
boundary-stop wrapper/profile guards explicitly require15MS/s. Rate-conditioned
coarse kernels/energies and the original-rate/canonical/pilot source mappings
also differ. New high-rate raw fixtures must cover full pilot filter history,
not just the shorter existing three-FFT fixture. Keep those guards and expose
the missing high-rate interface scope in its own reviewed implementation; do
not claim high-rate paired support from this15MHz test.

Require complete route, setup/hold/recovery, reviewed CDC/reset paths, and actual
board-I/O constraints. A generated bitstream or isolated positive slack is not
permission to flash. Preserve current deployed reference and pinned rollback.
The saved full-receiver board-I/O audit now identifies the13 missing input
delays as all12 RX data pins plus RX frame, and the2 missing outputs as enable
and txnrx. RX port-to-IDDR setup/hold show infinite/unconstrained slack, not
positive margin; internal RX slack cannot qualify these board paths. The actual
AD9361 IDELAYCTRL reference remains200MHz. See
`experiments/20260910-receiver-io-inventory.md` for exact evidence and remaining
external timing/calibration contracts. No exception was applied.
Qualify .18 first with exact serial/ownership and reversible testing, including
actual RX calibration and source15/30/60 fine timing against independent evidence.
Then deploy the pinned qualified package to .17 through PPU over Ethernet only.
Do not touch .14, .20 or .21. No radio is allocated by the offline studies.

## 4. Complete causal handoff and short-visit verification

Existing PPU paired-capture tests cover a fixed-frequency shared15 qualification
contract with caller-supplied fine anchors. They do not implement automatic
coarse-to-native30/60 handoff or120ms hopping. Add those operations with explicit
visit/channel/coefficient identity, source-time units, CFO/phase uncertainty,
prediction age, command lead, full capture support and expiry receipts.

The current three-map lock policy needs256ms for one hypothesis. Exploratory
one-map evidence requires85.333ms nominal centers, and two sequential aliases
need at least170.667ms at current throughput. A120ms scanner therefore requires
an explicitly tested short-integration policy or justified cross-visit evidence,
plus a measured hypothesis schedule. Any proposed cross-visit analysis must
retain independent visit identities and the required hop fence/partial-map
abort; it is not permission to carry stale detector history through a retune.
Neither buffering nor a faster transform
alone resolves that statistical/causal requirement. Preserve competing aliases
until an independently evaluated rejection rule resolves them; no post-hoc GLRT
winner may seed an allegedly blind comparison.

Record2.5MS/s CI16 pilot evidence at10MB/s plus metadata/results, reconcile source
support with every valid visit, and compare FPGA outputs with independent replay
GLRT/PSS. Retain negative controls, gaps, missed/expired candidates and clean
stop/restart outcomes. Only actual end-to-end evidence closes the release gate.
