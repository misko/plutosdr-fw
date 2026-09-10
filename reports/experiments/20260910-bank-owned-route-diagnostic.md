# Bank-owned175MHz isolated route: internal control path still fails

The three-bank actual-core slice is numerically tested, but this diagnostic
isolated route does not meet its saved clock constraints. It is not a receiver
build or a deployment candidate. No radio was accessed and no constraints were
changed, removed or waived.

Inputs: alternative HDL `169f9fb659bd98b4cb1e76163f4fdb8b853a7d1b`, frozen
`fft-bank-owned-synthesis-v2/fft_bank_owned_synth.dcp` SHA256
`f3afafdf684c80918b898ca7cb41f326392ece7f360627ad21bbbdce4e89aea3`.
Its hash was checked before and after the diagnostic and remained unchanged.
Vivado2022.2,xc7z010clg400-1,two threads. Completed00:57:54UTC,2026-09-10.

`open_checkpoint; opt_design; place_design; phys_opt_design; route_design`
used the inherited100MHz and nominal175MHz resource-probe clocks. The saved
175MHz period is actually5.714000225ns after Vivado quantization, not the
unrounded5.714285714ns Tcl argument. The first probe stopped on that identity
check before implementation; the second checks the saved5.714ns value without
recreating or relaxing either clock. Both attempts are retained.

| Scope | Setup WNS | Hold WHS | Failing setup endpoints |
| --- | ---: | ---: | ---: |
| Same-domain100MHz | +2.347ns | +.100ns | 0 |
| Same-domain175MHz | -2.557ns | +.070ns | 632 |
| 100->175 inherited cross-clock paths | -.657ns | +.148ns | 50 |
| 175->100 inherited cross-clock paths | -1.470ns | +.124ns | 78 |
| Complete diagnostic | -2.557ns | +.070ns | 760 |

Total negative slack is-1017.209ns; all6405 routable nets route, with zero
routing errors. Final inventory:1878LUT,4425FF,21DSP,7.5BRAM tiles. These are
isolated optimized/routed counts, not a net receiver area-saving measurement.

The worst same-domain path is
`product_bank/metadata_out_hold_reg[3]/C` ->
`joiner/kernel_rom/output_kernel_word_reg/ENARDEN`.
It has7.744ns data delay:2.444ns logic and5.300ns routing,13 levels including
six CARRY4 stages. It crosses the input guard's wide descriptor equality,
current input/result fault handling and the kernel-join acceptance enable.
The problem is not confined to an unconstrained external diagnostic output.
Splitting or specializing this control path needs RTL/protocol evidence;
overlapping capture and compute alone does not remove it.

Qualification limitations remain explicit:114 inputs and124 outputs have no
external delays; clock ports have no `HD.CLK_SRC` placement identity; CDC has
139 clock-enable warnings and six synchronizer information entries, and ports
without external delays are skipped. No blanket cross-clock qualification is
inferred. This diagnostic neither implements nor validates the full receiver's
clock generation, reset tree, CDC contracts, board interfaces or ADC calibration.

Reports and scripts are retained in
`20260910-bank-owned-route-diagnostic.tgz`, SHA256
`12f064a84a89b7a659281a9e5d5e4ba54c73cde10db5f012308b1922569e3bb3`.
The archive includes both attempt logs and source scripts, inherited constraints,
per-clock setup/hold reports, full summary, CDC, utilization and terminal receipt.
No DCP, bitstream or firmware is included. The locally retained routed DCP is
`/tmp/starlink-bank-route.I50MDJ/route-v2/bank_owned_diagnostic_routed.dcp`, SHA256
`c009360da3196f715e06a265999e6684742f34bdf69d2ec0bf7fcfd51381f299`.
The receipt hash is
`85aaaaef922f15d8bed7ac06105ba08a20d7c0b56343ae8313668e9223e7d652`.

Next: finish the unchanged-score composition's numerical/capacity checks and
review a small control-path refactor with current-fault/final-commit invariants.
Do not commission a full receiver build on this timing-failing slice merely
because its simulated175MHz service interval fits the coarse arrival budget.
