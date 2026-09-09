# Single-RX FPGA GLRT evidence

Experimental branch `codex/starlink-glrt-only-do-not-merge`. Persistent task
`01a0821a-7b4c-73f0-8b2c-47b4e95207f9`, gpt-6-astra / xhigh; unbudgeted objective
unfinished. See [the completion gate](GLRT_ONLY_GOAL.md).

Current HDL 0d67920c includes the reviewed CDC changes, 352-sample grouping and
physical timing adjustments. All five rate-specific images pass full-board
setup/hold, Gray-bus skew and the active netlist gate. Their corrected-model RAM
packages pass independent extraction and identity checks. The 60 MS/s image has
only +0.002 ns setup slack, a constrained pass with very little extra margin.
The earlier failed/narrow-margin attempts and ff42d5ab checkpoint remain intact.

A new fixed-seed, randomized-timing synthetic trial passes every strong-case
and control-case criterion. It recovers 32/45 complete strong frames; all 13
missed frames had truth-near candidates selected but busy rejected. All 32 strong
positives agree with independent host GLRT. Weak/short-signal and saved-RF
sensitivity limits remain. No hardware has been accessed: radio calibration,
real transport headroom, owner allocation and live agreement are outstanding.
See [current numerical evidence](reports/starlink-glrt-selector352-numerical-20260909.json),
[current board/package evidence](reports/starlink-glrt-current-board-packages-20260909.json)
and [the original numerical checkpoint](reports/starlink-glrt-numerical-checkpoint-20260909.json).

## Source isolation, 2026-09-08

Firmware fork `7e20f6e5c693e8aa1a92b2dd3f918feffff722ad` verified. Independent
local clones were initialized at these gitlinks, each on its own experimental
branch. They share read-only Git objects with the reference through alternates;
their source and build directories are independent, with no working-tree symlinks.

| Component | Initial commit |
|---|---|
| HDL | `edb0f7070ac4fe01a9a08f9d7d98bc70d03114d4` |
| Linux | `5d706586c591d4c9f5fc8a308b2b248693c0d279` |
| Buildroot | `41a2a806d97ec04a4d92f3f96c9d6d973dc3c8e6` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a` |

No applicable AGENTS.md files were found in this firmware worktree or its
initialized components. Scanner reference instructions were read; its sources
are read-only and will not become runtime dependencies.

## Current architecture

One pilot-centered RX1 source, with a free-running absolute source counter,
feeds both native-rate FPGA GLRT and an independent continuous 2.5 MS/s IQ
exporter. The new GLRT core contains no coarse or fine PSS computation. Its dedicated
board profile excludes both PSS IPs; the implemented-netlist audit has zero
PSS cells and one GLRT IQ DMA. Full timing/physical-boundary qualification is pending.
The exporter uses unity at 2.5, a final 5-to-2.5 FIR at higher rates, and an
additional 10/25/60-to-5 FIR where needed. Fixed pilot-centered tuning makes
the initial digital translation zero, explicitly recorded in the frequency plan.

Pilot-only FPGA acquisition proposes timing using known-pilot correlations;
a bounded native-rate sample ring supports 64-symbol exact/control GLRT.
Frequency search and score decisions run in fabric. CPU control provides no
acquired timing/CFO to the primary FPGA path. Proposal, grouping, admission,
busy rejection and result counters expose missed work. Simulated pacing and
positive internal slack still require actual DMA/transport qualification.

## Qualification ladder

| Source MS/s | Current numerical/RTL evidence | Full route, setup/hold ns | RAM package | Hardware/live |
|---|---|---|---|---|
| 2.5 | exact IQ/statistics; strong 4/9 frames; controls quiet | +0.112 / +0.019 | ram-2500000-v4 verified | pending |
| 5 | exact IQ/statistics; strong 4/9 frames; controls quiet | +0.200 / +0.021 | ram-5000000-v3 verified | pending |
| 10 | exact IQ/statistics; strong 8/9 frames; controls quiet | +0.075 / +0.014 | ram-10000000-v3 verified | pending |
| 25 | exact IQ/statistics; strong 8/9 frames; controls quiet | +0.041 / +0.024 | ram-25000000-v3 verified | pending |
| 60 | exact IQ/statistics; strong 8/9 frames; controls quiet | +0.002 / +0.013 | ram-60000000-v2 verified | pending |

RTL entries now include blind fabric acquisition, native GLRT and continuous
IQ export together, with no candidate timing input. The counts above describe
the new synthetic trial, with three CFO cases and nine complete strong frames
per rate. The four lower-rate boards identify a9a4ca9a; 60 identifies 0d67920c,
whose changes affect synthesis fanout and physical optimization without changing
arithmetic or cycle counts. The external I/O boundary, additional 60 MS/s timing
margin and real RF qualification remain open. These bounded synthetic
observations are not a measured RF sensitivity curve.

## Coordination

Coordinator and original FPGA owner notified of this task and source isolation.
The original FPGA task retains .18/.17 bench ownership. No device has been
opened, configured, or deployed by this task. Build/simulation work proceeds
without hardware; request a specific .18 window only after full design route.
Scanner task asked for saved positive and independent control/holdout locations.

## Current limits

Inherited pilot replay proves host GLRT after a 15-to-2.5 DDC. It contains no
FPGA GLRT and does not qualify any requested rate in this new profile.
No calibrated RF sensitivity, false-positive rate, transport headroom or live
agreement is claimed. Positive internal setup/hold does not close the external
receive interface. The sections below retain earlier implementation history;
their component/OOC results do not replace the current full-board evidence.
Production deployment is outside this task's experimental branch.

## First digital implementation checkpoint

The new `hdl/library/starlink_glrt` contains an independent unity/multirate
exporter and a native-rate 64-symbol exact/control correlator. These blocks have
no PSS dependencies. Coefficient and published pilot-state banks are frozen by
byte hashes. The correlator is one GLRT stage; it does not yet implement the
frequency maximization, autonomous acquisition or final decision.

The first aggregate suite passed 92 tests. Ten additional exporter tests passed
after explicit rejected-input accounting, counter-wrap refusal and clean-flush
coverage were added (39 exporter RTL tests total). The independent correlator
suite has 25 tests across all rates and both edges. The suite distinguishes
engineering fixtures from held-out detector qualification; thresholds are not
yet frozen and no measured false-positive rate is claimed.

An initial 60 MS/s standalone exporter failed placement because replicated
history needed 8448 LUT RAM sites (6000 available). The banked redesign's
`artifacts/ddc-60000000-v3` route used 4122 LUTs, 1093 registers, 24 DSPs and zero
BRAM, with internal setup/hold slack +0.158/+0.053 ns at 100 MHz. All 6626
routable nets routed without errors. Its unplaced boundary ports have 549
TIMING-15 hold warnings, explicitly outside that internal timing gate. This is
not a receiver timing pass. Subsequent accepted-counter/wrap changes require a
fresh route; the v3 result remains tied to the source hashes in its summary.

`NUMERICAL_SPEC.md` in the new HDL library documents the 64-symbol GLRT model,
the host normalization difference, CFO alias interval, resource budget and
native sample-ring admission. Native correlator synthesis is now running;
FPGA DFT/scoring, blind acquisition, CDC/control/DMA, kernel and host integration,
full receiver route and all hardware/live gates remain pending.

## FPGA GLRT scoring implementation checkpoint

The 512-bin exact/control frequency maximizer, independent power normalization,
73-cycle integer Q16 divider, and fabric threshold decision are now implemented.
Block scaling preserves low-amplitude numerical precision. Malformed symbol
order or mixed epochs poison the result. Zero energy and clamped scores are
explicit. Configuration is latched per vector. Gates remain provisional until
training/holdout qualification; there is no host or ARM FFT in this scoring path.

Connected native-IQ/correlator/scorer simulations pass at all five rates for
published-pilot positives, noise and rolled-control waveforms. Their candidate
epochs are intentionally testbench-supplied, so they do not prove blind FPGA
acquisition. The direct integer reference matches the fabric score and CFO bins.

The current 60 MS/s exporter (`ddc-60000000-v4`) uses 4143 LUTs, 1100 registers,
24 DSPs and no BRAM, with internal setup/hold +0.095/+0.056 ns. Native correlator
RAM inference first failed, then an isolated synchronous RAM boundary reduced
logic and a guarded address-collision check removed its remaining critical
path. Its `correlator-60000000-v3` route uses 672 LUTs, 684 registers, 8 DSPs and
24 BRAM tiles, with internal setup/hold +0.115/+0.147 ns. These are separate
OOC results; unplaced boundary timing and the complete receiver remain unqualified.

The scorer's first OOC implementation synthesized to 2211 LUTs, 1615 registers,
16 DSPs and half a BRAM tile, but failed internal setup by 0.697 ns between
rounding and magnitude squaring. An additional pipeline boundary retains exact
arithmetic and passes the score/integration tests. Registered fault fencing
then closed `score-common-v3`: 2281 LUTs, 1617 registers, 16 DSPs, half a BRAM,
and internal setup/hold +0.181/+0.069 ns. Its source is superseded by the
magnitude-mask simplification described below; retain its exact hash identity.


## Autonomous core and ingress checkpoint

Blind acquisition now checks 16 symbol correlations on every exported sample,
with exact 176-sample window energy, tagged arithmetic and explicit support.
The bank/power/energy/threshold chain passes 43 tests across both edges and all
source-index strides. `acquisition-v1` routes at 100 MHz using 4052 LUTs, 3498
registers, 24 DSPs and no BRAM; internal setup/hold are +0.357/+0.054 ns.
The six-lane pilot bank alone uses 18 DSPs after replacing a redundant multiply
and registering its address schedule.

The first connected blind fixture exposed a real scheduling miss: a weak
onset peak occupied the scorer before the stronger true peak arrived. A fixed
176-export-sample (70.4 us) selection window now retains the greatest eligible
raw numerator. Native rings doubled to 1024/2048/4096/8192/16384 CI16 words.
Counters distinguish raw/merged/selected proposals, admissions, busy rejections
and complete results. The default ring change supersedes the earlier standalone
correlator resource result; complete rate builds must remeasure it.

The autonomous receiver passes published-pilot synthetic positives at all five
rates with no candidate seed. Every exported IQ word, index, support flag and
clipping count matches direct convolution; every completed native GLRT event
matches the frozen integer score, raw powers, energies, CFO bins and flags.
Noise, tone and scrambled-symbol controls produce no detections in their five
2 ms fixtures each. This small development set does not establish an operational
false-positive rate. Thresholds remain provisional.

The rolled-pilot fixture is deliberately classified as an ambiguity experiment.
Blind acquisition finds the known code 17 symbols later. At least the 2.5 MS/s
fixture has an earlier unrelated candidate which occupies the scorer; the
shifted true proposal is then explicitly busy-rejected. The test preserves
this miss instead of counting it as a correctly rejected negative. The current
single-candidate schedule has no claim of complete recovery in overlapping or
busy windows; independent holdout and live comparisons must count those cases.

The combined 2.5 MS/s core fits provisionally but has **not closed timing**.
`receiver-2500000-v1` failed internal setup by 2.071 ns at the native-to-scorer
magnitude comparison. Replacing repeated maxima with a bitwise magnitude mask
preserves the exact common block scale. `receiver-2500000-v2` uses 7215 LUTs,
6119 registers, 48 DSPs and two BRAM tiles, with setup/hold -0.060/+0.051 ns.
Its remaining critical path is the selected epoch through native history
admission arithmetic. These OOC routes do not include ADC, CDC, AXI or DMA,
and their unplaced boundaries remain unqualified. No FPGA image was deployed.

A bounded pacing buffer now absorbs ingress jitter, with minimum 39 fabric
cycles across each 1/2/4/10/24 source-sample output group. Empty intervals do
not accumulate burst credits. Twenty tests prove bit-exact DDC output at 99%,
100% and 101% nominal pacing with bounded jitter, and explicit drop/gap
accounting under overload. A generic dual-clock FIFO adapted from the inherited
source carries CI16, full source index and phase; two tests cover independent
reset purges, overflow, recovery and data/phase integrity. Five additional tests connect the source counter, FIFO and pacer at all
native clocks, preserving absolute index and phase across radio resets. The
ingress has not yet been connected to the board or full autonomous core.

The aggregate autonomous-core regression passed **216 tests in 521.83 s**
(`artifacts/glrt-autonomous-tests-20260908.xml`). The later pacing suite passed
20 tests and the connected ingress/CDC suite passed seven tests
(`artifacts/glrt-ingress-tests-v2-20260908.xml`).

Next: close combined core admission timing, integrate ADC/CDC/control and the
continuous IQ DMA, then full 2.5 MS/s board placement/timing. Complete the
remaining full rate builds, kernel/host lifecycle and independent validation
before requesting the coordinated .18 canary window. The persistent goal remains
active and all hardware/live gates remain pending.

## GLR1 integration checkpoint, 2026-09-08 23:00 UTC

HDL `99e7e9ae` contains the complete GLR1 AXI register/snapshot/event ABI,
independent IQ/event FIFOs, ADC CDC/pacer, autonomous receiver, and the dedicated
no-PSS board profile. The combined 2.5 MS/s OOC core v5 passed internal setup/hold
at +0.212/+0.052 ns: 7220 LUTs, 6247 FFs, 48 DSPs, 2 BRAM. Before/after source
hashes match. OOC v4 is explicitly disqualified because its source changed during
execution; its apparent timing pass is diagnostic only.

The first full 2.5 MS/s board (HDL `4197f788`) placed/routed but failed setup at
-0.873 ns, hold +0.010 ns. It used 11088 LUTs and 12088 FFs at placement. Synthesis
also found a CLEAR/result-valid combinational loop. Registered core reset fixes
that loop in `99e7e9ae`; all **23 capture RTL tests pass** after this change.
A fresh isolated v2 board build is running. The full v1 audit reports zero PSS
cells, zero native RX DMA cells, one GLRT IP and one GLRT DMA, but is not eligible
for hardware. Complete timing, CDC, exceptions and I/O reports are retained in
`artifacts/board-2500000-v1/full-audit/`.

The new Linux `adi_starlink_glrt` driver compiles built-in with a dedicated
`zynq_pluto_glrt_defconfig` and `zynq-pluto-sdr-glrt.dts`; kernel zImage, modules
and DTB build completed in `artifacts/kernel-glrt-v1`. PSS kernel options are
explicitly off and PSS nodes are deleted from this DTB. RX1 RF setup remains
available, with one 2.5 MS/s IQ DMA consumer and a separate 16-word GLRT event
IIO kfifo. Actual clock checks, source-settle admission, promised-IQ drain,
stable final snapshot and explicit cumulative CPU event-loss counters are
implemented. Driver W=1 compilation has no driver warnings; inherited host
build-tool warnings remain. **No driver lifecycle or DMA hardware pass is claimed.**

The stdlib host GLR1 decoder rejects malformed headers, wrong rates/visits,
inconsistent source endpoints, missing host bytes, corrupt raw scores, event
sequence losses and CPU/fabric event loss. **44 adversarial metadata tests pass**;
**7 real RTL tests** also exercise decoder checks against all five IQ rates and
2.5/60 MS/s autonomous events. Their kernel header is constructed explicitly:
these tests do not execute Linux or IIO. Evidence:
`glrt-host-abi-tests-20260908.xml`, `glrt-host-rtl-decode-20260908.xml` and
`glrt-capture-tests-v3-20260909.xml` (the latter filename's date is a label error;
execution was 2026-09-08 UTC).

Next required integration work: review/fix the full routed I/O constraints and
CDC findings; expose AD9361 frame/valid discontinuities rather than relying only
on post-ADC accepted-word counters; qualify source-clock stoppage and clipping
visibility; finish the GLRT rootfs/image profile and host IIO capture lifecycle;
then all five full builds, independent blind host GLRT, holdouts and coordinated
.18/.17 hardware. The inherited CMOS receiver has no input-delay constraints;
these boundaries cannot be counted as a qualified board pass. The AD9361 Rev.G
1.8 V CMOS table gives data/frame delays 0..1.5/0..1.0 ns relative to DATA_CLK:
https://www.analog.com/media/en/technical-documentation/data-sheets/AD9361.pdf
Actual board skew, programmable interface delay and the runtime RF eye still
need explicit qualification. No radio has been accessed by this task.

## Source integrity, board and host checkpoint, 2026-09-08 23:42 UTC

HDL `ecfe49ca` exposes the AD9361 frame/valid status, retains discontinuities
that arrive without a sample, and refuses ARM or faults an active observation
after 4095 fabric clocks without paced source data. Counter coordinates count
valid source words; missing physical clock slots are not reconstructed.
Thirteen continuous-source board tests pass, including frame failure, missing
valid and stopped clock at 2.5/60 MS/s. Five ingress tests and the existing
23-test capture regression also pass after gap retention.

Full 2.5 MS/s board v3 routes at setup/hold **+0.059/+0.021 ns**, using
11140 LUTs, 12114 FFs, 48 DSPs and 4.5 BRAM tiles. Its audit confirms zero
PSS/native RX DMA cells, one GLRT IP and one IQ DMA. The routed design occupies
4110 of 4400 slices; timing margin is small. The three reset-related critical
CDC findings and inherited ADI control crossings still need documented review.
The ADI CMOS interface intentionally relies on runtime delay/eye calibration;
fixed input-delay exploration is not a measurement of that calibrated eye.
Hardware eligibility remains false until the internal review and coordinated
receive-interface qualification are complete.

Full 60 MS/s v1 failed placement: 76/80 DSPs, 35/60 BRAM, and 166 more slices
needed than available. HDL `4e428a90` bounds each FIR history by its tap window
plus all arrivals possible during scheduled reads, halving the two largest
buffers without changing arithmetic or coefficients. **84 DDC/pacing tests**
and **22 burst/wrap and integrated positive/rolled-pilot tests** pass. Full
60 MS/s v2 now passes placement and is routing; 5 and 10 MS/s builds are running.
Evidence is in `glrt-fir-history-ddc-tests-20260908.xml` and
`glrt-fir-history-receiver-tests-v2-20260908.xml`. The earlier receiver test run
had a testbench substitution typo; its failed log is retained and superseded
by v2, not counted as a pass.

Linux GLR1 kernel/DTB and the dedicated Buildroot root filesystem build.
Buildroot `5f9767e0c` selects the GLRT profile and fixes pinned host-m4 compilation
with GCC 15 by using GNU C11. The rootfs contains GLRT verification init and
iiod/libiio, with no PSS tool, init or modules. The exploratory rootfs still has
an old dirty VERSIONS stamp and must be rebuilt with final component identities
before packaging. The firmware Makefile selects the dedicated kernel/rootfs/FIT
profile, requires an explicit board XSA, and refreshes it between rate builds.
No FIT has been deployed or hardware opened.

`tools/starlink_glrt_host.py` performs blind acquisition and scalar GLRT-64
for every retained candidate in overlapping 20 ms windows, preserving short
tails as insufficient when necessary. It accepts CI16, edge and explicit
engineering gates; it has no FPGA-event input. The independent reference is
clean Leo commit `5f25fc57cca3ea564ac42debe3561139592c82b0`, with native extension,
source/input hashes and before/after integrity checks. Search is +/-100 kHz;
integer timing has a 0.4 us grid. Its multi-frame coherent-ceiling score is not
numerically identical to the FPGA's single-frame energy-normalized statistic.
**Eight tests pass** in 4.28 s, including upper/lower pilot edges at +/-90 kHz,
noise, tone, short support and truncated CI16. Evidence:
`artifacts/glrt-blind-host-tests-20260908.xml`.

All 48 records in the frozen 2.5 MS/s saved worker pack are being evaluated
without prior timing/CFO seeds. This previously examined corpus is development
data, not a fresh holdout or GLR1 transport qualification. The explicit .175
exact/.025 margin gates remain engineering settings. Host IIO collection,
full-rate ladder routing, numerical limitations/holdouts, actual transport
headroom and coordinated .18/.17 hardware/live qualification remain required.
Coordinator messaging currently fails because its local MCP transport is down;
independent work continues and no bench window has been assumed.

## Routing pressure and host lifecycle, 2026-09-09 00:07 UTC

The full 10 MS/s board at HDL `4e428a90` routes at **+0.004/+0.019 ns** setup/hold,
using 13277 LUTs, 64 DSPs and 9 BRAM tiles. The 5 MS/s board misses setup by
0.086 ns (hold +0.014). The 60 MS/s reduced-depth board v2 misses setup by
0.440 ns (hold +0.008) and violates a Gray-bus skew constraint by 0.750 ns.
All three implemented-netlist audits are saved; no failure is hardware eligible.
Ten MS/s has very small internal margin and still needs CDC/I/O qualification.

HDL `72e94f19` pipelines FIR history reads through synchronous BRAM. **96**
FIR/DDC/pacing tests and **10** integrated positive/rolled-pilot cases pass.
The standalone 60 MS/s DDC uses 2586 LUTs, 1120 FFs, 24 DSPs and 18 BRAM,
with setup/hold +0.445/+0.111 ns and unchanged before/after source hashes.
Full-board v3 still packs tightly and is completing routing; a 25 MS/s build
from this source is also running. The first BRAM OOC attempt lacked the RAM
wrapper in its source list and failed synthesis; v6 includes it and is the pass.

HDL `1d78e87e` additionally expresses each acquisition lane's 33 reachable
coefficients directly, eliminating general 891-word per-lane ROMs. **43**
bank/acquisition arithmetic tests pass. The standalone bank drops from about
3000 to 1612 LUTs (1228 FFs, 18 DSPs) and routes internally at +0.492/+0.102 ns.
Fresh full 5/60 MS/s builds and the full 25-case receiver regression are running.

Linux `f2a39d854e5e` builds the cached pre-ARM snapshot needed for exact event
counter baselines. Kernel v2, modules and GLRT DTB build with the task's own
toolchain. **44** strict metadata tests and **7** real RTL-to-host decoder cases
pass with explicit constructed kernel baselines; Linux execution is not claimed.
The new libiio collector preserves whole finite continuous IQ independently of
event failures, checks identity/rate/RF/TX mute, retains partial data and final
snapshots on error, and drains short event tails before closing contexts.
**65** host binding/lifecycle/ABI tests pass with fake IIO in 3.06 seconds.
The actual host libiio 0.26 loads; no IIO context or radio has been opened.
Usage and limits are in `tools/GLRT_HOST.md`.

All **48** saved development records completed independent host acquisition in
96 overlapping windows. Twelve records crossed the .175 exact/.025 margin gates
in at least one window (20 windows total). This is a count of engineering score
crossings, not a true-positive rate. Some final GLRT tracking CFOs lie outside
the +/-100 kHz acquisition/comparison range; the host now labels that explicitly
and counts in-band crossings separately. Eight host tests pass after adding the
label. The original v1 saved analysis remains unchanged and records its source
hashes. All holdout, same-observation FPGA comparison, transport headroom,
physical interface and live RF qualification gates remain pending.

## Five-rate board timing and saved RF, 2026-09-09

Every requested rate now has a full-board placement/routing pass. These are
internal timing results, with ADC input timing still dependent on measured
radio/FPGA delay calibration. No radio has been opened or image deployed.

| MS/s | HDL | Board artifact | Setup/hold ns | LUTs | Slices / 4400 | DSPs | BRAM tiles |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2.5 | ff42d5ab | board-2500000-v4 | +0.065/+0.024 | 9706 | 3909 | 48 | 4.5 |
| 5 | ff42d5ab | board-5000000-v3 | +0.091/+0.015 | 10589 | 4000 | 56 | 12 |
| 10 | ff42d5ab | board-10000000-v2 | +0.184/+0.011 | 11387 | 4156 | 64 | 19.5 |
| 25 | ff42d5ab | board-25000000-v2 | +0.043/+0.026 | 11416 | 4171 | 64 | 31 |
| 60 | ff42d5ab | board-60000000-v5 | +0.067/+0.016 | 12960 | 4333 | 72 | 46.5 |

All five implemented audits contain zero PSS cells, zero native-rate RX DMA
cells, exactly one GLRT core and one GLRT IQ DMA, and no bus-skew violation.
Margins are small. All five rows now use the same ff42d5ab source. Earlier
failing routes remain retained and disqualified, including
60 MS/s v4 at -0.286 ns and 5 MS/s v2 at -0.043 ns.

The ff42d5ab command-path change prevents AXI illegal-command decoding from
driving every internal FIR history write enable. A coincident input can enter
the internal DDC on the fault edge; IQ admission is fenced on that edge and the
core is flushed next cycle. **36** capture tests and **80** command/input phase
cases across 2.5/60 MS/s pass. The compact-ROM receiver regression passes all
**25** rate/control cases. XML evidence is under `artifacts/` with names
`glrt-command-fence-capture-tests`, `glrt-illegal-command-phase-tests`, and
`glrt-compact-rom-receiver-tests`, dated 20260909.

Buildroot `35d87ae5b` builds the GLRT rootfs and FIT-capable host tools. Its
inherited IIOD metadata/AIO dependencies are now explicitly selected in Kconfig;
the earlier missing-dependency failure is preserved. Package
`artifacts/ram-2500000-v2` contains a complete FIT and DFU with firmware label
`glrt-ram-r2500000-v2`, HDL ff42d5ab, Linux f2a39d854e5e and Buildroot 35d87ae5b.
Independent U-Boot extraction verifies all four embedded blobs byte-for-byte;
GNU cpio verifies the 783-member rootfs, exact VERSIONS and absence of PSS paths.
Device nodes were excluded from the second host extraction because the initial
unprivileged extraction could not create them. Three packaging tests pass.
The manifest remains `ready_for_deployment: false`: CDC/I/O review, calibrated
receive interface, allocated owner window and real hardware qualification remain.

Saved upper-edge record 31 is a previously examined development positive, not
a holdout. Autonomous RTL replay at the default acquisition gate 15729/65536
(.24) tests all 49825 windows but makes **zero proposals**. Its highest integer
acquisition score is .22913945. All 50000 CI16 samples are exported exactly,
SHA256 `3bf1603ceeba1b3a17888c4b9b87e215641879dc59ed71a81f15cd6650cbed25`.
The unchanged default miss is preserved in `artifacts/saved-record031-rtl-v1`.

Explicit experimental gate .20 yields seven completed GLRT scores, one positive
at replay epoch 36593, exact/control .540207/.093262 and CFO -63032.67 Hz.
It agrees with independent host acquisition within one 0.4 us sample and
191 Hz. Gate .16 yields 350 proposals, 146 selections, 113 busy rejections,
33 completed scores and zero positives; one selector remains pending at the
finite tail. Both studies preserve all IQ and integer-exact native statistics.
These are sensitivity/capacity observations, not calibrated detection rates.
Artifacts `saved-record031-rtl-v2-gate20` and `saved-record031-rtl-v3-gate16`
retain all proposals, selections, busy rejects, scores and source hashes.

The host now also scores each complete 704-sample frame individually using
only its own blind acquisition coordinates. A multi-frame crossing does not
label every constituent frame positive. On record 31, only eight of the fourteen
first-window frame supports cross the engineering gates; the other six remain
negative. **Nine** host tests pass, including alternating pilot/noise frames.
Original multi-frame analyses remain unchanged; new replay comparisons identify
legacy aggregate support explicitly or use the separate frame scores when
present. A broader all-upper-record development study is the next step; the
default gates have not been changed. Hardware coordination MCP still fails at
its local transport endpoint, so no bench ownership has been assumed.

## Bounded numerical trials and reset review, 2026-09-09

The all-upper saved-development study finished all 24 records at gate .20:
1.2 million exported CI16 words match exactly, with 122 proposals, eight busy
rejections and one positive (record 31). Record 29 ended with an incomplete
native frame and partially filled scorer. The original checker rejected that
combination; its failed artifact remains intact. Recheck
`artifacts/saved-record029-terminal-v2` records the native next/newest indexes,
required support end, scorer COLLECT state and collected-symbol count, proving
the pending work requires future input. It passes IQ and completed-score checks.
This is a finite-tail classification correction, not a repaired detector fault.

The frozen synthetic matrix contains 50 new seeded 4 ms cases across all five
rates at gate .20. All cases underwent autonomous RTL replay and independent
blind host analysis of the exact exported bytes. Four original runs encountered
the same checker limitation; only those were rerun, in
`artifacts/synthetic-glrt-terminal-rechecks-v2`. The 46 original completed cases
and four corrected rechecks retain their source/input hashes. Original aggregate
summaries stay disqualified and are not rewritten into passes.

Fourteen of fifteen strong cases at CFO -100/0/+100 kHz recover a truth-aligned
event. The 60 MS/s, zero-CFO case is an actual miss: all three true proposals
were selected but rejected while the scorer was busy. Six unrelated candidates
were scored, with no positive result, while independent host GLRT scored .989.
No positives occur in the 15 noise/tone/scrambled-control cases (only 60 ms total
control observation; not a qualified false-alarm rate). The nominal -10.97 dB
weak cases produce no detections at 2.5/5/10/25 and one at 60 MS/s. Repeated
32-symbol bursts produce detections at every rate; 8-symbol bursts do not.
Rolled-code ambiguity is rediscovered at 2.5/10, with busy/acquisition misses at
the other rates. These generated cases are not fresh saved/live RF holdouts.

All five rates have assembled RAM FIT/DFU packages under `artifacts/ram-*`.
Their manifests remain ineligible for deployment. The routed reset topology
still produces CDC-10/11 and RAM asynchronous-control warnings. Sixteen new
occupied-FIFO/stopped-ADC tests pass on ff42d5ab, preserving source-index reset
versus radio-reset behavior and requiring source-clock acknowledgement.

An independent owned HDL clone, `artifacts/cdc-development-v1/hdl`, contains
prototype commit `1a0bafdc`: each raw reset's source-clock release is separately
acknowledged in the CPU domain; no AND of readiness levels drives a FIFO async
clear. RAM write enable/address/payload are registered without async resets,
and the Gray write pointer is published at the actual delayed write edge.
Twenty-three FIFO/ingress/reset tests pass in 4.05 s. An intermediate cleanup
mistakenly removed a wire still used for the full comparison and failed compile;
the passing v3 restores it. A full 60 MS/s board build is running in
`artifacts/board-60000000-cdc-v1`. This prototype has not replaced the main HDL
or been declared physically qualified. Real hardware transport, calibration,
bench ownership and live RF agreement remain outstanding.

The 1a0bafdc route subsequently passed at +0.094/+0.013 ns and removed the
combinational-reset warning; its downstream RAM warnings identified a second
path through the external source-health indication. Commit 82173e4d fences
that indication through two CPU stages. All **61** ingress/capture tests pass
in 206.03 s. Its full 60 MS/s route passes at +0.029/+0.025 ns and now has no
CDC-10, LUTAR-1, REQP-1839 or REQP-1840 warning. Two reset-fanout CDC-11 patterns
and inherited ADI handshakes remain for the documented protocol review. The main
HDL checkout has advanced to 82173e4d; the 2.5 MS/s route is being audited.
See [the CDC review](reports/GLRT_CDC_REVIEW.md).

Separate prototype a9a4ca9a extends candidate grouping from 176 to 352 output
samples, without a host seed or gate change. It recovers a correct event in the
previously missed 60 MS/s zero-CFO case, reducing busy rejects from 18 to 9.
The saved record-31 positive at gate .20 is preserved; at gate .16 it now also
recovers one frame, with busy rejects reduced from 113 to 65. Original misses
remain retained. Full receiver tests and the already examined 50-case matrix
are running as development regressions, together with 5/25/60 board builds.
The regression protocol preserves a corrected provenance statement and the
original generated document: the copied generator initially inherited its
first-run seed-description sentence. No case, gate, source hash or outcome
was changed by that metadata correction. Future runs do not infer holdout status
from fixed seeds. No hardware or fresh saved/live RF holdout is claimed.

## Wider grouping and independent synthetic trial, 2026-09-09

All 29 selector/receiver tests pass in 386.92 seconds, including lookahead 352
and five-rate positive/noise/tone/scrambled/rolled cases. Main HDL is a9a4ca9a.
The complete 50-case development regression passes its 15 strong and 15 control
criteria, recovering 37/45 strong frames. Eight strong frames remain missed.

The separately fixed trial uses seed offset 764930281 and randomized integer
native epochs, including fractional positions on the output grid. All 50 cases
complete with unchanged source hashes and no checker rechecks. Its 15 strong
cases recover 32/45 complete frames; each of the 13 missed frames had a proposal
within two output samples of truth, selected but rejected while busy. All 32
strong detections agree with independently acquired, individually scored host
frames. Noise/tone/scrambled cases produce zero positives in 60 ms nominal
observation (59.4984 ms supported IQ); this is not a false-alarm-rate qualification.

The new weak case detects one frame at 2.5 MS/s and none at the other rates.
Repeated 32-symbol bursts yield 3/1/3/3/3 detections across the five rates; 8-symbol
bursts yield none. The 5 MS/s short-burst detection and all three at 60 MS/s lack
a matching host positive. The latter host run has an unrelated in-band engineering
crossing instead, retained in its comparison evidence. Rolled-code shifted
ambiguity remains at every rate. Across all cases, 495820 supported CI16 words
match exactly and 177 completed native results match the fixed-point oracle.
Three incomplete native/scorer tails and 14 pending selectors remain explicit.
See the [frozen numerical report](reports/starlink-glrt-selector352-numerical-20260909.json).

Current 2.5/5/10/25 MS/s builds pass full setup/hold, Gray-bus skew and the active
netlist gate. Their reports contain no CDC-10, LUTAR-1, REQP-1839 or REQP-1840.
Their new RAM packages pass U-Boot extraction, exact embedded-byte comparisons,
GNU cpio listing/VERSIONS extraction and DFU-suffix validation. The reusable
local verifier is `scripts/verify_glrt_ram.py`; it never accesses a radio and
does not grant deployment approval. All four archives contain 783 members with
exact component identities and no PSS paths.

The a9a4ca9a 60 MS/s attempt is retained in
`artifacts/board-60000000-selector352-v1`, setup/hold -0.056/+0.025 ns. Its critical
path is acquisition-history address through distributed RAM/bank selection to
a DSP input. Isolated commit 25c9b1d1 changes only the 60 MS/s pre/post-route
physical-optimization directives to AggressiveExplore; all RTL and XDC bounds
are identical. Its full build is in progress. Hardware coordination messaging
still fails at the local MCP transport endpoint, and no ownership window has
been assumed.

## Current RAM candidates and deployment-tool compatibility, 2026-09-09

Physical-only 60 MS/s attempt 25c9b1d1 passed at +0.001/+0.038 ns. Its successor
0d67920c limits acquisition history-address fanout to 32 and passes the full
audit at +0.002/+0.013 ns, 12887 LUTs, 13378 FFs, 4355/4400 slices, 72 DSPs and
46.5 BRAM tiles. The worst path moves to the native reader's 64-bit availability
comparison. No clock, jitter or CDC constraint was relaxed. This remains a very
narrow setup margin. All 23 pilot-bank cadence/arithmetic tests pass; the first
test invocation named a file not yet copied into the prototype and ran no tests.
All 38 main AXI/IQ/event capture tests pass in 197.33 seconds on a9a4ca9a.

Deployment preparation found that the GLRT device tree replaced physical board
identity with a firmware-description string. Linux 2ca294936430 preserves the
inherited Rev.C model and uses a separate `misko,glrt-fpga` marker. The new kernel
build is `artifacts/kernel-glrt-v3`, release 5.15.0-00009-g2ca294936430. Compiled
device-tree checks prove both markers, the exact GLRT DMA binding and no ADC
DMA property. Earlier packages retain the experimental model and are superseded
for the current device-tool workflow.

The independent owned tool checkout `artifacts/device-tool-glrt-v1`, based on
PPU 5e3d6b91 and committed at fa2f6e1, adds literal `rx-glrt-stream-v1`. The old
native-IQ and detector-without-IQ policies retain their requirements. The new
policy verifies the exact custom CI16/event formats, 2.5 MS/s export, GLR1 ABI,
GLRT marker/DMA binding, no native ADC DMA, and no PSS or TX datapath. Existing
board/setup/serial/boot/QSPI/TX-quiesce/recovery checks remain binding. **91**
contract/backend/lifecycle tests and **13** CLI tests pass; lint and the two
changed modules' type checks pass. One intermediate receipt fixture used the
internal schema field instead of its JSON alias; its failed run is retained,
and the corrected tests also match each intended rejection reason.

All five new packages and candidate-plan hashes are in the
[current board/package report](reports/starlink-glrt-current-board-packages-20260909.json).
Plans live in owned mode-0700 `contracts/` directories and name the intended
ad9361-1r1t setup, not an observed current radio state. No USB inventory or live
operation has run. Owner messaging continues to fail at the local MCP endpoint.
