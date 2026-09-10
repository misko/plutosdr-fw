# Bank-owned coarse engine: integration and deployment gates

This is the next experimental implementation, not a change to the target.
Preserve canonical15MS/s coarse PSS, source15/30/60 native fine PSS, independent
2.5MS/s CI16 IIO evidence, .18 qualification before Ethernet/PPU .17, and the
eight-target120ms-valid-visit/300s scanner. No main-branch firmware merge,
detector removal, timing waiver or replacement of fine evidence is authorized.

## 1. Integrate the local transform engine without changing score arithmetic

Checkpoint: the additive complete scorer passes the six 64-block/numeric
alternative runs and two independent primary-branch 175 MHz reruns. The
4,096-block soak and physical gates below remain open. No receiver profile
selects this module yet.

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
MMCM configuration has been generated, but not integrated or physically tested;
see `experiments/20260910-bank-island-clock-generation.md`. Its lock/reset and
new exact bank-CDC endpoint contracts are additional full-integration gates.

Require complete route, setup/hold/recovery, reviewed CDC/reset paths, and actual
board-I/O constraints. A generated bitstream or isolated positive slack is not
permission to flash. Preserve current deployed reference and pinned rollback.
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
