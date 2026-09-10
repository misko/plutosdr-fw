# Producer-final P1 synthesis — complete, not timing-qualified

Original owner handle75133 exited0 once, with before-audit/tool/after-audit/owner
statuses all0. Start2026-09-10T15:22:18.723278Z;
end15:24:26.615810Z; wall127.8924s. No retry, RTL change, or route occurred in this
measurement. The one-shot invocation and all original receipts are retained.

Tested source FW3bdaaf06440f969520acaa8828b6c39bc60dc820 /
HDL6923f5352951f8e03b9c29b6d4ef3c091a3cac90; physical-preparation manifest
b3c446578c0c35f8e0f199aa12f66d8635b6f7d21c9b97713a5ffed2ac2b0f06.
The passed actual50316 eight-RTL closure is unchanged. All seven experimental
R/D/S/C/K/M/P flags read back exactly1. No flag is silently inherited or added.

## Mapped result

| Synthesized slice | LUT | FF | RAMB18 | DSP |
| --- | ---: | ---: | ---: | ---: |
| Prior ROM K1/M1 | 2059 | 4607 | 15 | 21 |
| Producer-final P1 | 2064 | 4607 | 15 | 21 |

Both use zero black boxes, no latches, and no RAMB36. These are isolated mapped
resources, not full-receiver savings, placement utilization, or timing closure.
The five-LUT change does not establish the intended routed-cone removal.

DCP:2171713 bytes, SHA256
`41c756bdc45635b1107d73ad741826e5a8f8fa276dc159468ec2355c16203aa6`.
Original path:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-synthesis-v1/synthesis/fft_bank_owned_synth.dcp`.

Vivado2022.2, partxc7z010clg400-1, maxThreads2, unchanged synthesis recipe.
Actual clocks: `source_100` on`clk`, period10ns; `island_175` on`fft_clk`,
period5.71400022506713867ns. These are constraints, not achieved clocks.
All eight required nonempty products and15 scope hash rows (14 source/IP plus
actual log) rehashed independently. The frozen admission helper reran with the
copied13-file closure, returning eight RTL/P1 and the original qualified-status
counts953795+292463=1246258. Original before/after inventory audit remains0.
There is exactly one completion marker and no ERROR/FATAL in the original log.

CDC report:17 Info CDC-3,139 Warning CDC-15, zero reported Critical; those bundled
metadata crossings are not waived or physically qualified. Check timing reports
114 missing input delays and124 missing output delays, zero missing clocks or
unconstrained internal endpoints. Existing reset/paused-clock qualification
limits persist. No setup/hold or frequency-pass claim is made from synthesis.

## Separate bounded route

Prepared owner:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-route-v1/own_route.py`.
SHA256`5938ff6c7141676e3629547196e1d5aec57f5bd77c8df2fbe76edbc01e6873de`.
Complete inverse to old ROM ownere9b7ca13900d5b04e807bed408aab87022d05cab81c18cec33e79305f700c3b0
passes after exactly three substitutions: DCP relative path, Tcl relative path,
and DCP SHA. The unchanged Tcl remains0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a.
The owner derives its directory and non-/tmp temp from its own path; no fourth
code substitution, clock change, retry, or exception is introduced.

After separate source-specific approval, original63593 launched once at
2026-09-10T15:28:35.593055Z with this command; its result is recorded separately:

```
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-route-v1/own_route.py
```

No promotion follows an isolated result. The P1 cut is limited to sampled
producer-final publication; full result-completion/fault cones remain unchanged.

Original synthesis warnings are preserved in full, including IP generic-forwarding
warnings, unused ports/logic, thread-hook packaging notices, period rounding, and
missing OOC clock-source properties. Exact top generic readback, RTL/source hash
closure, and zero-black-box receipts were checked; warnings are not hidden.

Archive: `hdl/library/starlink_pss_acquisition/evidence/producer-final-synthesis-v1/`.
Originals and prior negative ROM route remain intact; post-audit46567 exited0.
