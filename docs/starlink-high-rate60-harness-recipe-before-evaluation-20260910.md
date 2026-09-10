# Frozen healthy60 common-source harness recipe — before evaluation

This additive recipe is frozen before combined harness evaluation. Parent
approved source/pipeline accounting after reading the accepted StageA60
public contract. It authorizes offline preparation only: no vendor actual
FFT, combined service execution, physical work, deployment or RF claim.

The exact machine-readable contract is
`tests/starlink_oracle/high_rate60_harness_recipe.py`. Numerical inputs remain
the existing69-file60 cohort (manifest6de2f364…); runtime is the reviewed
HDLf16dc564 StageA60 delta plus otherwise unchanged original runtime.

Clocks all start0. Source waits2.1ns then toggles each500/60ns (quantized
8333333fs half): first rise10433333fs, first fall18766666fs, period16666666fs.
FFT waits1.3ns then toggles each500/175ns: first rise4157143fs, first
fall7014286fs, half2857143fs, period5714286fs. Control is100MHz. Each origin,
edge and cadence must be witnessed within1fs; these ideal clocks are not a
generated-MMCM/physical-clock qualification.

The source sequence contains2 separately counted disabled-DDC prime beats
at34359735209/210 (CI16 words1/2), then all16423 unchanged original samples
in[34359735211,34359751634). Total16425; **no tail**. Pilot-only preroll
consumes3111 original raw samples, yielding1549 intermediate30 and768
canonical samples. A planned startup pause drains CDC/pipelines before
coarse enable. This pause is outside the measured continuous-source segment:
the entire16423-sample epoch is NOT claimed wall-clock uninterrupted.
The remaining13312 original samples in[34359738322,34359751634) must use
successive true60 clock edges with exact data/index/time correspondence,
including the complete native command/capture and source-off edge.

Each x2 ledger independently tracks14 inputs of history, absolute-index
phase and six pre-edge observer slots. RTL issue at edge0 reaches registered
output after edge5; an observer at the next posedge sees it at edge6. The
second ledger consumes predicted first-stage output, not DUT filter_issue,
history or output-valid as truth. Both roundings and all intermediate values
remain the existing independent cohort's values. Raw support radius21 and
center4*k are signal support, separate from control/CDC processing latency.

Conditioner enable must first match independent programmed coarse/pilot
state, validated at public configuration completion, actual STOP ticket/ACK
and the exact512th pilot admission. Only this checked independent enable
may drive ledger cancellation. On disable, any already-visible old output
is still checked; unpromised pending pipeline work is canceled according
to unchanged RTL semantics. Final admitted/delivered pilot count512 may
stop the conditioner before4096 canonical outputs or seven FFT jobs drain.

Last selected pilot newest index8589937416 is offset3608 from the first
canonical sample. It requires at least3609 canonical/mixed/accepted inputs,
1805 halfband outputs,602 total pilot outputs (90 unsupported +512 retained),
and4*3608+43=14475 original raw inputs including both filter halos. These
are **support-only lower bounds**, never a replacement for the exact per-edge
ledger. The canonical visible prefix must stay below4096 and enabled raw
below16423; every visible value/index remains exact.

Coarse geometry is447x2: exactly894 selected scores and447 map words. Allow
at most one numerically checked already-computed tail block (visible894..1341).
Every visible FFT input/forward/product/inverse word, BFP exponent, score
energy/numerator/denominator/value/index/phase is checked against unchanged
seven-block goldens. Two complete admitted blocks require at least1024 words
per transform stage; the full fixture bounds each stage at3584 words and
score preparation at3129. Public empty STOP ticket1 is distinct from actual
complete-map STOP ticket2, requested after200 visible scores.

Native center is static34359740384. All original standalone admission limits
remain: trigger34359738560, real handshake[34359738560,34359738720], signed
lead1535..1695,256 control-cycle command budget and exact readback witness
with2/31-sample capture/return lag and48-cycle read-pair bound. Capture520,
taps264,257 raw/241 qualified tuples, both26-word public reads, hold<=16,
publication/full-drain<=84000 and public release<=88000 after capture remain
unchanged. Free-result/direct-three-port-AXI and<=24-cycle transactions are
test assumptions; no shared-host-bus capacity is inferred.

Source-off requires full original support/capture and native computation
still ongoing. Source/control/FFT clocks continue afterward. Retained coarse
map ownership survives native packet publication/read/release; public map
release may precede the final native raw-tail drain. Finish only after both
releases, all257 raw tuples and native bridge/engine idle,512pilot delivery,
bank-only quiescence and256 additional no-stale control clocks. No global
reset may hide unfinished native work or stale bank output.

Overlap must be actual FFT-clock core transfers during native capture and
actual native compute while bank work/pilot are active, followed by compute
after coarse STOP. A static schedule or elapsed-cycle estimate cannot satisfy
these witnesses. Known center, startup pause, ideal clocks and direct AXI
limit this to bounded healthy numerical composition—not causal acquisition,
RF timing accuracy, full continuous capacity, DMA/IIO or production-map proof.
