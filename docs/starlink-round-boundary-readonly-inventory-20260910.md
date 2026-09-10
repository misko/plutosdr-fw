# Boundary rounding: read-only routed-checkpoint audit

The first A/B routed checkpoints were reopened without constraint, placement,
routing or checkpoint writes. Original processes45993(option0) and24407(option1)
completed exit0 at06:23:06/07 UTC on2026-09-10. Both checkpoint SHA256 values
were checked before and after inspection and still match the original route
archive. No physical run was repeated.

| Measured property | Original option0 | Boundary option1 |
|---|---:|---:|
| Internal register-to-register setup slack | -1.577ns | +0.964ns |
| Internal register-to-register hold slack | +0.084ns | +0.103ns |
| Negative hold endpoints |176|176|
| Negative hold endpoints starting at top-level ports |176|176|
| sum_real / sum_imag DSP PREG |0 /0|1 /1|
| product_ii / product_iq DSP PREG |1 /1|1 /1|
| All four DSP AREG / BREG |0 /0|0 /0|

The new internal setup limiter is sum_real DSP P17 to output_i[16], with
4.464ns data delay and five carry cells plus three LUTs. This is distinct from
the removed overflow carry-to-comparison chain. Overall setup remains+0.207ns
because reset input paths are included in the original complete report.

Every one of the176 negative hold endpoints in each isolated route launches
at a top-level port. The helper enumerates up to10000 endpoints, one worst path
per endpoint; the176 count agrees with the original timing summaries. This
explains the standalone failure classification, but does not waive those
failures or qualify integrated bank/receiver timing. The explicit OOC input
budgets remain unchanged; actual upstream paths must be measured in integration.

The old physical log, lines490–492, explicitly records37 registers pushed out
of each sum DSP and74 created fabric cells. Both optimized designs had278
fabric FFs; after physical optimization/routing the old design had352 and the
new design278. The new mapping retains both sum registers in DSP PREGs. This
accounts for the74 fabric-FF difference without deleting logical state. Both
isolated designs retain four DSPs and zero BRAMs.

The isolated AREG0/BREG0 inventory is not the bank operand inventory: the
previous full-bank design has AREG1/BREG0. The bank's measured BRAM-to-DSP path,
raw fault fanout and overall -1.907ns setup failure remain open. A genuine
registered operand boundary needs separate latency, ownership, reset and
physical qualification; these local measurements do not prove that change.

Evidence archive:
`reports/experiments/20260910-round-boundary-readonly-inventory.tgz`

SHA256:`e86f7ca743bbc004bd3d57b5da08390752e7381f1f90b81cf985468bdd5af3e8`.
It contains the read-only helper, both inventories, all endpoint tables,
internal setup/hold reports and original outer logs/journals. The earlier
route/test archive remains unchanged at
`7f3e9282f000d9c0c0c1606fb9b934d031086b0a34a552cb5e005ae9e258a5c0`.

No runtime RTL, timing constraint, radio, PPU or primary branch changed in
this audit. Neither isolated checkpoint is a qualified deployment image.
