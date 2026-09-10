# Idle-admission full receiver: failed physical qualification

Source HDL `d1b3107b56c869d59724df2a8d695112a1f6ac3c`, original100/200MHz
clocks, paired-pilot15, both PSS stages and pilot DMA. Full build completed
2026-09-10T00:20:46Z with exit1. It is not eligible for deployment.

Archive `20260910-idle-admission-failed-route.tgz` SHA256:
`e5598f9d4049a58c81b2198fcec04b257b070f6fadcd9d6988593f477f6ea54a`.
It retains the full build log, final postroute timing, route status, explicitly
placed utilization report and incomplete read-only endpoint audit. No DCP,
bitstream or firmware is included. The input DCP SHA256 was checked unchanged
after the audit: `f7c337695f06dbe95e8659569f4cb7ce9f56c681efb0fc473dc58c70bd121e8e`.

Setup WNS is-1.269ns, TNS-125.326ns,355 failing endpoints. There are351
200MHz setup failures and four asynchronous recovery failures.100MHz passes
at+.009ns; overall hold passes at+.002ns. All34008 nets route without errors.
The13 RX input and two output external-delay gaps are not resolved. A generated
bitstream and `bad_timing.xsa` do not override these failed/open release gates.

The read-only audit verifies the expected core, both detectors/pilot DMA and
initial endpoint inventories, then fails closed because the old targeted
metadata-to-job-start path is no longer returned by the timing engine. All75
metadata flops, the destination flop and5ns clocks were found. This is not proof
of path removal or a timing/CDC pass: the remaining reports were not executed.
A future audit must distinguish structural absence from excluded constraints
without waiving either. The first audit command failed its argument count
before opening the checkpoint; its corrected second attempt is retained here.

Full numerical/regression evidence and exact source hashes are recorded in
`reports/starlink-idle-mailbox-admission-20260910.json`. Best18c remains the
retained physical reference, itself unqualified; this trial regresses from it.
No radios were accessed, configured or flashed.
