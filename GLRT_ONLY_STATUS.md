# Single-RX FPGA GLRT evidence

Experimental branch `codex/starlink-glrt-only-do-not-merge`. Persistent task
`01a0821a-7b4c-73f0-8b2c-47b4e95207f9`, gpt-6-astra / xhigh; goal active without
a token budget. See [the completion gate](GLRT_ONLY_GOAL.md).

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

## Architecture under implementation

One pilot-centered RX1 source, with a free-running absolute source counter,
feeds both native-rate FPGA GLRT and an independent continuous 2.5 MS/s IQ
exporter. The new GLRT core contains no coarse or fine PSS computation. Its dedicated
board profile, still pending, must exclude both PSS IPs entirely.
The exporter uses unity at 2.5, a final 5-to-2.5 FIR at higher rates, and an
additional 10/25/60-to-5 FIR where needed. Fixed pilot-centered tuning makes
the initial digital translation zero, explicitly recorded in the frequency plan.

Pilot-only FPGA acquisition proposes timing using known-pilot correlations;
a bounded native-rate sample ring supports 64-symbol exact/control GLRT.
The frequency search and score decision must run in fabric. CPU control cannot
provide acquired timing/CFO to the primary FPGA path. Numerical/resource work
will establish admission capacity and expose missed work before this design
is considered implemented. The proposed schedule is not yet a throughput proof.

## Qualification ladder

| Source MS/s | Numerical reference | RTL verified | Synthesized | Full route | Hardware | Live agreement |
|---|---|---|---|---|---|---|
| 2.5 | frozen arithmetic | blind core + export | combined core, timing fails | pending | pending | pending |
| 5 | frozen arithmetic | blind core + export | common acquisition/scorer | pending | pending | pending |
| 10 | frozen arithmetic | blind core + export | common acquisition/scorer | pending | pending | pending |
| 25 | frozen arithmetic | blind core + export | common acquisition/scorer | pending | pending | pending |
| 60 | frozen arithmetic | blind core + export | separate components | pending | pending | pending |

RTL entries now include blind fabric acquisition, native GLRT and continuous
IQ export together, with no candidate timing input. Synthetic positives pass
at all rates. A deployable GLRT-only board profile and real RF qualification
remain pending. These are engineering tests, not held-out sensitivity claims.

## Coordination

Coordinator and original FPGA owner notified of this task and source isolation.
The original FPGA task retains .18/.17 bench ownership. No device has been
opened, configured, or deployed by this task. Build/simulation work proceeds
without hardware; request a specific .18 window only after full design route.
Scanner task asked for saved positive and independent control/holdout locations.

## Current limits

Inherited pilot replay proves host GLRT after a 15-to-2.5 DDC. It contains no
FPGA GLRT and does not qualify any requested rate in this new profile.
No sensitivity, false-positive rate, full-receiver timing closure, transport
headroom, or live agreement is claimed yet. Component resource measurements
below do not establish whole-design fit. No production deployment or source
promotion is authorized.

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
